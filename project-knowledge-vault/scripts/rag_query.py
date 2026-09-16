#!/usr/bin/env python3
"""
rag_query.py — Hybrid retrieval over the local index built by rag_index.py.

Part of the `project-knowledge-vault` skill. Combines:
  * LEXICAL (BM25) — nails exact identifiers that matter in technical docs
    (E565, XMS1, MCBU, "26 08 01", "Part 3 item 41", X-61). ID-aware tokenizer.
  * SEMANTIC (dense cosine over local embeddings) — catches the concept when the
    caller doesn't know the exact tag ("who owns the wire to the annunciator").
The two ranked lists are merged with Reciprocal Rank Fusion (RRF). If the index has
no embeddings (deps absent at index time), it runs lexical-only automatically.

Everything is local; no network calls. The query is embedded with the same local
model recorded in meta.json.

SCALE
Nothing here loads the corpus. The BM25 index is precomputed by rag_index.py (see
rag_lexical.py) and memory-mapped, so a query reads only the postings of its own
terms. The dense pass streams embeddings.npy in blocks rather than loading it, and
result text is fetched by byte offset — only the passages actually shown are
parsed. Peak memory is a few hundred MB regardless of corpus size.

An index built before the precomputed BM25 existed still works: the lexical leg
falls back to scanning chunks.jsonl, which is correct but slow and memory-hungry
on a large vault. Re-run rag_index.py to get the fast path.

Usage:
  python rag_query.py <vault_or_index_dir> "<question>" [options]

Options:
  -k <n>            number of passages to return (default 8)
  --path <substr>   only chunks whose path contains <substr> (repeatable; OR)
  --tag <tag>       only chunks carrying <tag> in frontmatter tags (repeatable; OR)
  --kind <k>        restrict to 'note' or 'source'
  --lexical         force lexical-only (ignore embeddings)
  --dense-pool <n>  score dense only over the top-<n> lexical candidates instead
                    of the whole corpus (much faster; loses pure-semantic recall
                    for passages with no lexical overlap). 0 = full scan (default)
  --block <n>       rows per block in the dense scan (default 200000)
  --json            emit JSON (for programmatic use) instead of formatted text
  --show-chars <n>  characters of each passage to print (default 600)
  --timing          print per-stage timings to stderr
  --encode-device   device used to embed the question (default cpu)

COST NOTE
A hybrid query spends ~12s importing torch before it can embed the question;
that is fixed per process and unrelated to corpus size. `--lexical` skips the
import entirely and answers in well under a second, which is what you want for
exact-identifier lookups (E565, MCBU, "26 08 01").

Exit code 2 if no index is found.
"""
import os, sys, re, json, math, argparse, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_lexical
from rag_lexical import tokenize, chunk_tokens

# Force UTF-8 on stdout/stderr so non-ASCII passages don't crash a Windows
# console's default codepage.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- load index
def find_index(path):
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "chunks.jsonl")):
        return path
    cand = os.path.join(path, ".rag")
    if os.path.exists(os.path.join(cand, "chunks.jsonl")):
        return cand
    return None


def load_meta(index_dir):
    try:
        return json.load(open(os.path.join(index_dir, "meta.json")))
    except Exception:
        return {}


def _try_numpy():
    try:
        import numpy as np
        return np
    except Exception:
        return None


class ChunkStore:
    """Random access to chunks.jsonl by row, via the offsets rag_index.py wrote."""

    def __init__(self, index_dir, np):
        self.path = os.path.join(index_dir, "chunks.jsonl")
        off = os.path.join(index_dir, "chunk_offsets.npy")
        self.offsets = np.load(off, mmap_mode="r") if (np and os.path.exists(off)) else None
        self._f = None

    @property
    def n(self):
        return len(self.offsets) if self.offsets is not None else None

    def get(self, rows):
        """Return {row: chunk_dict} for the given rows."""
        out = {}
        if self.offsets is not None:
            if self._f is None:
                self._f = open(self.path, "rb")
            for r in rows:
                self._f.seek(int(self.offsets[r]))
                try:
                    out[r] = json.loads(self._f.readline().decode("utf-8", "replace"))
                except Exception:
                    pass
            return out
        # no offsets (pre-existing index): one sequential pass
        want = set(rows)
        with open(self.path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i in want:
                    try:
                        out[i] = json.loads(line)
                    except Exception:
                        pass
                    if len(out) == len(want):
                        break
        return out


# ---------------------------------------------------------------- filters
def build_mask(index_dir, np, n, args):
    """bool[n] of chunks allowed by --kind/--path/--tag, from the small columns."""
    if not (args.kind or args.path or args.tag):
        return None
    pid_p = os.path.join(index_dir, "chunk_pathid.npy")
    kind_p = os.path.join(index_dir, "chunk_kind.npy")
    paths_p = os.path.join(index_dir, "paths.txt")
    if not (os.path.exists(pid_p) and os.path.exists(paths_p)):
        return "no-columns"
    mask = np.ones(n, dtype=bool)
    if args.kind and os.path.exists(kind_p):
        kinds = np.load(kind_p, mmap_mode="r")
        mask &= (np.asarray(kinds) == (0 if args.kind == "note" else 1))
    if args.path or args.tag:
        with open(paths_p, encoding="utf-8") as f:
            paths = [l.rstrip("\n") for l in f]
        keep_pids = set()
        if args.path:
            low = [p.lower() for p in args.path]
            keep_pids |= {i for i, p in enumerate(paths)
                          if any(s in p.lower() for s in low)}
        if args.tag:
            try:
                ptags = json.load(open(os.path.join(index_dir, "path_tags.json"),
                                      encoding="utf-8"))
            except Exception:
                ptags = {}
            want = {t.lower() for t in args.tag}
            tagged = {p for p, ts in ptags.items()
                      if want & {str(t).lower() for t in ts}}
            keep_pids |= {i for i, p in enumerate(paths) if p in tagged}
        pids = np.load(pid_p, mmap_mode="r")
        sel = np.zeros(len(paths) + 1, dtype=bool)
        for i in keep_pids:
            sel[i] = True
        mask &= sel[np.asarray(pids)]
    return mask


# ---------------------------------------------------------------- lexical
def lexical_scores(index_dir, np, n_chunks, q_tokens, log):
    """Precomputed BM25 if present, else the old in-memory scan."""
    if np is not None and rag_lexical.Lexical.available(index_dir):
        lx = rag_lexical.Lexical(index_dir)
        if lx.usable_for(n_chunks):
            s = lx.scores(q_tokens)
            lx.close()
            return s, "precomputed"
        lx.close()
        log("  [lex] precomputed index is stale for this chunks.jsonl "
            "(re-run rag_index.py); falling back to a full scan.")
    return _lexical_scan(index_dir, np, n_chunks, q_tokens), "scan"


def _lexical_scan(index_dir, np, n_chunks, q_tokens):
    """Fallback for indexes built before the precomputed BM25 existed. Single
    streaming pass: accumulate df and per-chunk tf for the query terms only, so
    this is far lighter than the original all-chunks-in-RAM approach, though
    still O(corpus) per query."""
    qset = set(q_tokens)
    if not qset:
        return [0.0] * n_chunks
    tfs = []
    lens = []
    df = {t: 0 for t in qset}
    with open(os.path.join(index_dir, "chunks.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                c = json.loads(line)
            except Exception:
                tfs.append({}); lens.append(0); continue
            ts = chunk_tokens(c)
            lens.append(len(ts))
            local = {}
            for t in ts:
                if t in qset:
                    local[t] = local.get(t, 0) + 1
            for t in local:
                df[t] += 1
            tfs.append(local)
    N = len(lens)
    avgdl = (sum(lens) / N) if N else 0.0
    k1, b = rag_lexical.K1, rag_lexical.B
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    out = [0.0] * N
    for i, local in enumerate(tfs):
        if not local:
            continue
        dl = lens[i]
        s = 0.0
        for t, fq in local.items():
            s += idf[t] * (fq * (k1 + 1)) / (fq + k1 * (1 - b + b * dl / avgdl))
        out[i] = s
    return out


# ---------------------------------------------------------------- dense
def dense_scores(index_dir, meta, query, np, n_chunks, mask, args, log):
    """float32[n_chunks] cosine scores, or None. Streams embeddings.npy in
    blocks: the matrix is gigabytes on a real corpus and must never be loaded."""
    if not meta.get("embedded") or np is None:
        return None
    emb_path = os.path.join(index_dir, "embeddings.npy")
    if not os.path.exists(emb_path):
        return None
    try:
        mat = np.load(emb_path, mmap_mode="r")
    except Exception:
        return None
    if mat.shape[0] != n_chunks:
        log("  [dense] embeddings.npy does not match chunks.jsonl; skipping dense.")
        return None
    model_name = meta.get("model")
    try:
        from sentence_transformers import SentenceTransformer
        # CPU on purpose: this encodes one short question. Measured on this box a
        # single sentence is ~70ms on CPU vs ~190ms once CUDA has initialised, and
        # CPU avoids reserving GPU memory for a process that exits immediately.
        # (The dominant cost either way is ~12s of importing torch.)
        m = SentenceTransformer(model_name, device=args.encode_device)
    except Exception as e:
        log(f"  [dense] model '{model_name}' unavailable ({e.__class__.__name__}); "
            f"lexical-only.")
        return None
    prefix = "Represent this sentence for searching relevant passages: " \
             if "bge" in (model_name or "").lower() else ""
    qv = m.encode([prefix + query], normalize_embeddings=True)[0].astype("float32")

    sims = np.zeros(n_chunks, dtype="float32")
    if args.dense_rows is not None:
        rows = args.dense_rows
        if len(rows):
            # Random-access only the candidate rows.
            sims[rows] = np.asarray(mat[rows], dtype="float32") @ qv
        return sims
    blk = max(1, args.block)
    for s in range(0, n_chunks, blk):
        e = min(s + blk, n_chunks)
        if mask is not None and not mask[s:e].any():
            continue
        sims[s:e] = np.asarray(mat[s:e], dtype="float32") @ qv
    return sims


# ---------------------------------------------------------------- fusion
def rrf(rank_lists, k=60):
    """Reciprocal Rank Fusion over {row: rank(0-based)} lists."""
    fused = defaultdict(float)
    for rl in rank_lists:
        for row, rank in rl.items():
            fused[row] += 1.0 / (k + rank + 1)
    return fused


def top_rows(scores, keep, mask, np):
    """{row: rank} for the top-`keep` strictly-positive scores."""
    if np is not None and hasattr(scores, "dtype"):
        s = scores
        if mask is not None:
            s = np.where(mask, s, np.float32(0))
        nz = int((s > 0).sum())
        if not nz:
            return {}
        keep = min(keep, nz)
        idx = np.argpartition(-s, keep - 1)[:keep]
        idx = idx[np.argsort(-s[idx])]
        return {int(r): i for i, r in enumerate(idx)}
    items = [(r, v) for r, v in enumerate(scores)
             if v > 0 and (mask is None or mask[r])]
    items.sort(key=lambda x: x[1], reverse=True)
    return {r: i for i, (r, _v) in enumerate(items[:keep])}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Hybrid retrieval over a local vault index.")
    ap.add_argument("target", help="vault dir, or the .rag index dir")
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--kind", default=None, choices=[None, "note", "source"])
    ap.add_argument("--lexical", action="store_true")
    ap.add_argument("--dense-pool", type=int, default=0, dest="dense_pool")
    ap.add_argument("--block", type=int, default=200000)
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--show-chars", type=int, default=600, dest="show_chars")
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--encode-device", default="cpu", dest="encode_device",
                    help="device for embedding the question (default cpu)")
    args = ap.parse_args()
    args.dense_rows = None

    def log(msg):
        print(msg, file=sys.stderr)

    t0 = time.time()
    def tick(label):
        if args.timing:
            log(f"  [t] {label}: {time.time()-t0:.2f}s")

    index_dir = find_index(args.target)
    if not index_dir:
        print(f"No index found under {args.target} (run rag_index.py first).", file=sys.stderr)
        sys.exit(2)

    np = _try_numpy()
    meta = load_meta(index_dir)
    store = ChunkStore(index_dir, np)

    n_chunks = store.n
    if n_chunks is None:
        n_chunks = int(meta.get("n_chunks") or 0)
        if not n_chunks:
            with open(os.path.join(index_dir, "chunks.jsonl"), encoding="utf-8") as f:
                n_chunks = sum(1 for _ in f)
    if not n_chunks:
        print("Index is empty.", file=sys.stderr); sys.exit(2)

    mask = build_mask(index_dir, np, n_chunks, args) if np is not None else None
    if isinstance(mask, str):           # columns missing on an older index
        log("  [filter] this index has no filter columns; re-run rag_index.py. "
            "Filters ignored.")
        mask = None
    n_pool = int(mask.sum()) if mask is not None else n_chunks
    tick("open")

    q_tokens = tokenize(args.query)
    lex, lex_how = lexical_scores(index_dir, np, n_chunks, q_tokens, log)
    tick(f"lexical ({lex_how})")

    pool = max(50, args.k * 6)
    rank_lists = [top_rows(lex, pool, mask, np)]
    mode = "lexical-only"

    if not args.lexical:
        if args.dense_pool and np is not None:
            cand = top_rows(lex, args.dense_pool, mask, np)
            args.dense_rows = np.asarray(sorted(cand), dtype="int64")
        den = dense_scores(index_dir, meta, args.query, np, n_chunks, mask, args, log)
        if den is not None:
            rank_lists.append(top_rows(den, pool, mask, np))
            mode = f"hybrid (BM25 + {meta.get('model')})"
            if args.dense_pool:
                mode += f", dense over top-{args.dense_pool} lexical"
        tick("dense")

    fused = rrf(rank_lists)
    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:args.k]
    rows = [r for r, _ in ranked]
    chunks = store.get(rows)
    tick("fetch")

    results = []
    for row, score in ranked:
        c = chunks.get(row)
        if not c:
            continue
        results.append(dict(
            score=round(float(score), 5),
            path=c["path"], title=c.get("title", ""), headings=c.get("headings", ""),
            section=c.get("section", []), tags=c.get("tags", []),
            kind=c.get("kind"), text=c.get("text", ""),
        ))

    if args.as_json:
        print(json.dumps(dict(query=args.query, mode=mode,
                              index=index_dir, results=results), ensure_ascii=False, indent=2))
        return

    print(f"# Retrieval: {args.query}")
    print(f"# mode: {mode} | pool: {n_pool}/{n_chunks} chunks "
          f"| model: {meta.get('model') or 'none'}\n")
    for i, r in enumerate(results, 1):
        loc = r["path"] + (f"  ›  {r['headings']}" if r["headings"] else "")
        sec = f"  [{', '.join(r['section'])}]" if r["section"] else ""
        print(f"[{i}] {loc}{sec}   (score {r['score']})")
        body = re.sub(r"\s+", " ", r["text"]).strip()
        print("    " + body[:args.show_chars] + ("…" if len(body) > args.show_chars else ""))
        print()


if __name__ == "__main__":
    main()
