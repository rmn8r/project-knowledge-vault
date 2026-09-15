#!/usr/bin/env python3
"""
rag_index.py — Build a LOCAL, hybrid retrieval index over a project-knowledge vault.

Part of the `project-knowledge-vault` skill. Turns the vault's Markdown notes
(and, optionally, extracted source-document text) into a chunked, on-disk index
that `rag_query.py` searches with hybrid lexical + semantic retrieval.

Design goals (see references/rag-retrieval.md):
  * LOCAL ONLY. Embeddings are computed with a local sentence-transformers model.
    Text and vectors never leave the machine — required for confidential
    (e.g. Owner-Proprietary) project data. No cloud embedding API is ever called.
  * DEGRADES GRACEFULLY. If numpy / sentence-transformers are not installed, the
    index still builds (chunks + metadata) and `rag_query.py` runs lexical-only
    (BM25). Semantic recall is added transparently once the deps are present.
  * ON-DISK, PORTABLE. The index is a `.rag/` folder written inside the vault, so
    it persists in the (cloud-synced) project folder and needs no running service.
    Fits the ephemeral-sandbox model: query just memory-maps files.
  * INCREMENTAL. Re-embeds only changed/added files (content hash); drops removed.
  * STRUCTURE-AWARE. Markdown chunked by heading path; extracted spec/contract text
    chunked with overlap while preserving section-like IDs (e.g. "26 08 01 §3.1.A",
    "DPE Part 3 item 41") in metadata so retrieved passages stay citable.

Usage:
  python rag_index.py <vault_dir> [options]

Options:
  --source <dir>       Also index a folder of *extracted* source text (.txt/.md),
                       e.g. the scratch output of extract_text.py. Repeatable.
  --model <name>       sentence-transformers model (default: BAAI/bge-small-en-v1.5;
                       falls back to sentence-transformers/all-MiniLM-L6-v2).
  --index <dir>        Where to write the index (default: <vault_dir>/.rag).
  --chunk-chars <n>    Target chunk size for non-heading text (default 1200).
  --overlap <n>        Overlap chars between size-based chunks (default 200).
  --no-embed           Skip embeddings (lexical-only index). Useful for a fast
                       first pass or when the model isn't available.
  --rebuild            Ignore the manifest and rebuild everything from scratch.

Outputs (in <index>/):
  chunks.jsonl    one JSON object per chunk (id, path, title, headings, section,
                  text, tags, mtime, hash)
  embeddings.npy  float32 [N, D] aligned to chunks.jsonl order (only if embedded)
  manifest.json   {relpath: {hash, mtime, n_chunks}} for incremental rebuilds
  meta.json       model, dim, counts, built_at, config

This file writes NOTHING outside <index>/. It only reads the vault/source dirs.
"""
import os, sys, re, json, hashlib, argparse, time, glob, collections

# Force UTF-8 on stdout/stderr so non-ASCII vault text (e.g. "→", "§") doesn't
# crash on a Windows console's default codepage. (Matches the GitHub fix.)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
FALLBACK_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ---------------------------------------------------------------- optional deps
def _try_numpy():
    try:
        import numpy as np
        return np
    except Exception:
        return None

def _pick_device(requested):
    """'cuda' when a GPU is actually usable, else 'cpu'. Honours an explicit
    --device. Embedding is the long pole of a full build and a mid-range laptop
    GPU runs it roughly an order of magnitude faster than the CPU, so this is
    worth detecting rather than leaving to chance."""
    if requested:
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"

def _load_model(name, device="cpu", fp16=False):
    """Return (encoder_callable, dim, model_name) or (None, None, None)."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        print(f"  [embed] sentence-transformers not available ({e.__class__.__name__}); "
              f"building lexical-only index.")
        return None, None, None
    for cand in [name, FALLBACK_MODEL]:
        try:
            m = SentenceTransformer(cand, device=device)
            if fp16 and device == "cuda":
                # ~3x faster on this class of GPU; the retrieval quality
                # difference for a small bi-encoder is not measurable here, and
                # vectors are stored back as float32 either way.
                m = m.half()
            # get_sentence_embedding_dimension() is deprecated in newer
            # sentence-transformers; prefer get_embedding_dimension(). (Matches GitHub fix.)
            try:
                dim = m.get_embedding_dimension()
            except Exception:
                dim = m.get_sentence_embedding_dimension()
            print(f"  [embed] loaded local model: {cand} (dim={dim}, "
                  f"device={device}{', fp16' if fp16 and device == 'cuda' else ''})")
            return m, dim, cand
        except Exception as e:
            print(f"  [embed] could not load {cand}: {e.__class__.__name__}: {e}")
    return None, None, None

# ---------------------------------------------------------------- file helpers
def sha(text):
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()

def read_text(path):
    """Read a file; tolerate cloud-only/dehydrated files (return None, don't crash)."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None

def parse_frontmatter(text):
    """Return (meta_dict, body) for a Markdown note with YAML frontmatter."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text
    block, body = m.group(1), text[m.end():]
    meta = {}
    try:
        import yaml
        meta = yaml.safe_load(block) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        # light fallback parser: key: value and key: [a, b]
        for line in block.splitlines():
            mm = re.match(r"\s*([A-Za-z0-9_\-]+):\s*(.*)$", line)
            if not mm:
                continue
            k, v = mm.group(1), mm.group(2).strip()
            if v.startswith("[") and v.endswith("]"):
                meta[k] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
            else:
                meta[k] = v.strip("\"'")
    return meta, body

def title_of(path, meta, body):
    m = re.search(r"^#\s+(.+)$", body, re.M)
    if m:
        return m.group(1).strip()
    if isinstance(meta, dict) and meta.get("title"):
        return str(meta["title"])
    return os.path.splitext(os.path.basename(path))[0]

def tags_of(meta):
    out = []
    for key in ("tags", "discipline", "category", "type"):
        v = meta.get(key) if isinstance(meta, dict) else None
        if isinstance(v, list):
            out += [str(x) for x in v]
        elif v:
            out.append(str(v))
    return sorted(set(t.strip() for t in out if str(t).strip()))

# section-like identifiers that make a chunk citable
SECTION_PATTERNS = [
    r"\b\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?\b",         # spec 26 08 01 / 260801.03
    r"§\s?[0-9A-Z][0-9A-Z.\-]*",                     # §3.1.A
    r"\b(?:Part|Item|Section|Note|Sheet)\s+\d+[A-Za-z.\-]*", # Part 3 / Item 41 / Note 2
    r"\b[EMAPSGCVF]\d{3}(?:\.\d+)?[A-Z]?\b",        # drawing sheet tags E565, E801.3
    r"\b[XGCS]-\d+\b",                               # register IDs X-61, G-37, C-10
]
_SECRE = re.compile("|".join(SECTION_PATTERNS))

def sections_in(text):
    found = _SECRE.findall(text)
    # findall on an alternation returns tuples when groups exist; normalize
    flat = []
    for f in _SECRE.finditer(text):
        flat.append(f.group(0).strip())
    seen, out = set(), []
    for s in flat:
        if s not in seen:
            seen.add(s); out.append(s)
    return out[:12]

# ---------------------------------------------------------------- chunking
def chunk_markdown(body, chunk_chars, overlap):
    """
    Split a note into chunks along headings, preserving the heading path.
    Returns list of (heading_path:str, text:str). Long sections are further
    split by size with overlap.
    """
    lines = body.splitlines()
    sections, cur_head_stack, buf = [], [], []
    def flush():
        if buf and any(l.strip() for l in buf):
            head = " > ".join(cur_head_stack)
            sections.append((head, "\n".join(buf).strip()))
    for ln in lines:
        hm = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if hm:
            flush(); buf = []
            level = len(hm.group(1)); title = hm.group(2).strip()
            cur_head_stack = cur_head_stack[:level-1]
            while len(cur_head_stack) < level-1:
                cur_head_stack.append("")
            cur_head_stack = cur_head_stack[:level-1] + [title]
        else:
            buf.append(ln)
    flush()
    out = []
    for head, text in sections:
        for piece in split_by_size(text, chunk_chars, overlap):
            out.append((head, piece))
    return out

def split_by_size(text, chunk_chars, overlap):
    text = text.strip()
    if len(text) <= chunk_chars:
        return [text] if text else []
    # prefer paragraph boundaries
    paras = re.split(r"\n\s*\n", text)
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= chunk_chars:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            if len(p) <= chunk_chars:
                cur = p
            else:
                # hard-split an overlong paragraph
                i = 0
                while i < len(p):
                    chunks.append(p[i:i+chunk_chars])
                    i += chunk_chars - overlap
                cur = ""
    if cur:
        chunks.append(cur)
    # add overlap between adjacent chunks for context continuity
    if overlap > 0 and len(chunks) > 1:
        out = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i-1][-overlap:]
            out.append((prev_tail + " " + chunks[i]).strip())
        return out
    return chunks

# ---------------------------------------------------------------- discovery
def iter_files(vault_dir, source_dirs):
    """Yield (abs_path, relpath, kind). kind in {'note','source'}."""
    for f in glob.glob(os.path.join(vault_dir, "**", "*.md"), recursive=True):
        # skip our own caches inside the vault: .rag/ (index) and .rag_source/ (scratch text)
        if re.search(r"[\\/]\.rag(_source)?[\\/]", f):
            continue
        yield f, os.path.relpath(f, vault_dir), "note"
    for sd in source_dirs or []:
        # A --source that resolves to nothing must be loud. Silently indexing
        # the notes alone produces a plausible-looking index that is missing the
        # entire document corpus, and nothing downstream can tell the difference.
        # (Seen for real: %LOCALAPPDATA% paths are redirected away under the
        # Microsoft Store build of Python, so the scratch dir vanished.)
        if not os.path.isdir(sd):
            print(f"  [source] WARNING: not a directory, indexing nothing from it: {sd}")
            continue
        n = 0
        for ext in ("*.txt", "*.md"):
            for f in glob.glob(os.path.join(sd, "**", ext), recursive=True):
                n += 1
                yield f, os.path.join("[source]", os.path.relpath(f, sd)), "source"
        if n == 0:
            print(f"  [source] WARNING: no .txt/.md found under {sd}")
        else:
            print(f"  [source] {n} files from {sd}")

# ---------------------------------------------------------------- main build
def build(args):
    index_dir = args.index or os.path.join(args.vault, ".rag")
    os.makedirs(index_dir, exist_ok=True)
    chunks_path = os.path.join(index_dir, "chunks.jsonl")
    emb_path = os.path.join(index_dir, "embeddings.npy")
    manifest_path = os.path.join(index_dir, "manifest.json")
    meta_path = os.path.join(index_dir, "meta.json")

    old_manifest = {}
    if not args.rebuild and os.path.exists(manifest_path):
        old_manifest = json.load(open(manifest_path)) or {}

    # 1) discover + hash; decide which files changed
    files = list(iter_files(args.vault, args.source))
    seen_rel = set()
    changed, unchanged, unreadable = [], [], []
    file_meta = {}
    for abs_path, rel, kind in files:
        seen_rel.add(rel)
        text = read_text(abs_path)
        if text is None:
            unreadable.append(rel); continue
        h = sha(text)
        try:
            mtime = os.path.getmtime(abs_path)
        except Exception:
            mtime = 0
        file_meta[rel] = dict(abs=abs_path, kind=kind, text=text, hash=h, mtime=mtime)
        if old_manifest.get(rel, {}).get("hash") == h:
            unchanged.append(rel)
        else:
            changed.append(rel)
    removed = [rel for rel in old_manifest if rel not in seen_rel]

    print(f"  files: {len(files)}  changed/new: {len(changed)}  "
          f"unchanged: {len(unchanged)}  removed: {len(removed)}  "
          f"unreadable(cloud-only?): {len(unreadable)}")
    for rel in unreadable:
        print(f"    ! could not read (hydrate then re-index): {rel}")

    # 2) load prior chunks for unchanged files (so we don't re-chunk them)
    prior_chunks = {}
    if os.path.exists(chunks_path) and not args.rebuild:
        for line in open(chunks_path, encoding="utf-8"):
            try:
                c = json.loads(line)
            except Exception:
                continue
            prior_chunks.setdefault(c["path"], []).append(c)

    # 3) (re)chunk changed files
    def make_chunks(rel, fm):
        out = []
        if fm["kind"] == "note":
            meta, body = parse_frontmatter(fm["text"])
            ttl = title_of(rel, meta, body)
            tgs = tags_of(meta)
            pieces = chunk_markdown(body, args.chunk_chars, args.overlap)
        else:
            meta, tgs = {}, ["source"]
            ttl = os.path.basename(rel)
            pieces = [("", p) for p in split_by_size(fm["text"], args.chunk_chars, args.overlap)]
        for i, (head, text) in enumerate(pieces):
            if not text.strip():
                continue
            cid = f"{rel}::{i}"
            out.append(dict(
                id=cid, path=rel, kind=fm["kind"], title=ttl,
                headings=head, section=sections_in((head + " " + text)),
                tags=tgs, text=text, hash=fm["hash"], mtime=fm["mtime"],
            ))
        return out

    all_chunks = []
    for rel in unchanged:
        all_chunks.extend(prior_chunks.get(rel, []))
    for rel in changed:
        all_chunks.extend(make_chunks(rel, file_meta[rel]))
    # (removed files simply drop out)

    # stable order: notes first, then source; then by path
    all_chunks.sort(key=lambda c: (c["kind"] != "note", c["path"], c["id"]))
    print(f"  chunks: {len(all_chunks)}")

    # 4) embeddings (local, optional)
    np = _try_numpy()
    emb_matrix = None
    model_name = None
    dim = None
    if not args.no_embed and np is not None:
        _device = _pick_device(args.device)
        _fp16 = (_device == "cuda") and not args.no_fp16
        model, dim, model_name = _load_model(args.model, _device, _fp16)
        if model is not None:
            # reuse prior vectors for unchanged chunks when possible
            prior_vecs = {}
            if os.path.exists(emb_path) and os.path.exists(chunks_path) and not args.rebuild:
                try:
                    prev = np.load(emb_path)
                    prev_ids = [json.loads(l)["id"] for l in open(chunks_path, encoding="utf-8")]
                    if len(prev_ids) == prev.shape[0]:
                        prior_vecs = {cid: prev[i] for i, cid in enumerate(prev_ids)}
                except Exception:
                    prior_vecs = {}
            need = [c for c in all_chunks if c["id"] not in prior_vecs]
            print(f"  embedding {len(need)} new/changed chunks "
                  f"(reused {len(all_chunks)-len(need)})...", flush=True)

            # Stream straight into a memory-mapped .npy. Encoding every chunk in
            # one model.encode() call and then np.vstack-ing the per-row arrays
            # needs the whole float32 matrix in RAM twice over plus the full list
            # of prefixed texts; on a real project corpus (millions of chunks,
            # ~6 GB of vectors) that exhausts memory long before it finishes.
            # A memmap keeps peak RAM flat at one batch regardless of corpus size.
            os.makedirs(os.path.dirname(emb_path) or ".", exist_ok=True)
            emb_matrix = np.lib.format.open_memmap(
                emb_path, mode="w+", dtype="float32", shape=(len(all_chunks), dim))
            row_of = {c["id"]: i for i, c in enumerate(all_chunks)}
            for cid, v in prior_vecs.items():
                i = row_of.get(cid)
                if i is not None:
                    emb_matrix[i] = v
            prior_vecs = None
            if need:
                # bge models benefit from a passage prefix; harmless for MiniLM
                prefix = "Represent this passage for retrieval: " if "bge" in (model_name or "").lower() else ""
                batch = max(1, args.embed_batch)
                t0 = time.time()
                for s in range(0, len(need), batch):
                    part = need[s:s + batch]
                    arr = model.encode([prefix + c["text"] for c in part],
                                       batch_size=min(batch, args.encode_batch),
                                       show_progress_bar=False,
                                       normalize_embeddings=True)
                    for c, v in zip(part, arr):
                        emb_matrix[row_of[c["id"]]] = v
                    done = s + len(part)
                    rate = done / max(time.time() - t0, 1e-6)
                    print(f"    {done}/{len(need)} chunks  ({rate:.0f}/s, "
                          f"eta {(len(need)-done)/max(rate,1e-6)/60:.0f} min)", flush=True)
            emb_matrix.flush()
    elif args.no_embed:
        print("  [embed] skipped (--no-embed): lexical-only index")
    else:
        print("  [embed] numpy not available: lexical-only index")

    # 5) write index
    with open(chunks_path, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    if emb_matrix is not None:
        # already written in place by the memmap above
        del emb_matrix
        emb_matrix = True
    elif os.path.exists(emb_path) and (args.no_embed or args.rebuild):
        # Drop stale vectors for a lexical-only/rebuild pass. On cloud-synced
        # folders the file may be locked (OneDrive) and un-deletable — in that
        # case empty it so np.load() fails and queries fall back to lexical,
        # rather than crashing the whole build.
        try:
            os.remove(emb_path)
        except OSError:
            try:
                open(emb_path, "wb").close()
            except OSError:
                print(f"  [embed] note: could not clear stale {emb_path} "
                      f"(locked?); marked index as not-embedded.")

    # Count per file in one pass. Scanning all_chunks once per file is
    # O(files x chunks) - at project scale (thousands of files, millions of
    # chunks) that is tens of billions of comparisons and never finishes.
    per_file = collections.Counter(c["path"] for c in all_chunks)
    manifest = {}
    for rel, fm in file_meta.items():
        manifest[rel] = dict(hash=fm["hash"], mtime=fm["mtime"],
                             n_chunks=per_file.get(rel, 0))
    json.dump(manifest, open(manifest_path, "w"), indent=0)

    meta = dict(
        built_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        vault=os.path.abspath(args.vault),
        model=model_name, dim=dim,
        embedded=emb_matrix is not None,
        n_files=len(file_meta), n_chunks=len(all_chunks),
        n_source_dirs=len(args.source or []),
        chunk_chars=args.chunk_chars, overlap=args.overlap,
        note="LOCAL index. No content or vectors leave this machine.",
    )
    json.dump(meta, open(meta_path, "w"), indent=2)

    print(f"  wrote {index_dir}/  (embedded={meta['embedded']}, "
          f"model={model_name or 'none — lexical only'})")
    print("  done.")

def main():
    ap = argparse.ArgumentParser(description="Build a local hybrid RAG index over a vault.")
    ap.add_argument("vault")
    ap.add_argument("--source", action="append", default=[],
                    help="extra folder of extracted source text (repeatable)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--index", default=None)
    ap.add_argument("--chunk-chars", type=int, default=1200, dest="chunk_chars")
    ap.add_argument("--overlap", type=int, default=200)
    ap.add_argument("--embed-batch", type=int, default=2048, dest="embed_batch",
                    help="chunks encoded per streamed batch (memory/throughput knob)")
    ap.add_argument("--encode-batch", type=int, default=128, dest="encode_batch",
                    help="model.encode batch size (128 suits an 8GB GPU)")
    ap.add_argument("--device", default=None,
                    help="force 'cuda' or 'cpu' (default: cuda when available)")
    ap.add_argument("--no-fp16", action="store_true", dest="no_fp16",
                    help="keep full precision on GPU (slower)")
    ap.add_argument("--no-embed", action="store_true", dest="no_embed")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    if not os.path.isdir(args.vault):
        print("vault dir not found:", args.vault); sys.exit(1)
    print(f"Indexing vault: {args.vault}")
    build(args)

if __name__ == "__main__":
    main()
