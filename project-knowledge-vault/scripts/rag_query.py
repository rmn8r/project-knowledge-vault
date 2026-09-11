#!/usr/bin/env python3
"""
rag_query.py — Hybrid retrieval over the local index built by rag_index.py.

Part of the `project-knowledge-vault` skill. Combines:
  * LEXICAL (BM25, pure-Python) — nails exact identifiers that matter in technical
    docs (E565, XMS1, MCBU, "26 08 01", "Part 3 item 41", X-61). ID-aware tokenizer.
  * SEMANTIC (dense cosine over local embeddings) — catches the concept when the
    caller doesn't know the exact tag ("who owns the wire to the annunciator").
The two ranked lists are merged with Reciprocal Rank Fusion (RRF). If the index has
no embeddings (deps absent at index time), it runs lexical-only automatically.

Everything is local; no network calls. The query is embedded with the same local
model recorded in meta.json.

Usage:
  python rag_query.py <vault_or_index_dir> "<question>" [options]

Options:
  -k <n>            number of passages to return (default 8)
  --path <substr>   only chunks whose path contains <substr> (repeatable; OR)
  --tag <tag>       only chunks carrying <tag> in frontmatter tags (repeatable; OR)
  --kind <k>        restrict to 'note' or 'source'
  --lexical         force lexical-only (ignore embeddings)
  --json            emit JSON (for programmatic use) instead of formatted text
  --show-chars <n>  characters of each passage to print (default 600)

Exit code 2 if no index is found.
"""
import os, sys, re, json, math, argparse
from collections import Counter, defaultdict

# Vault text (and the arrows/dashes used below) can contain characters outside a
# Windows console's default codepage; force UTF-8 so printing never crashes.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- load index
def find_index(path):
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "chunks.jsonl")):
        return path
    cand = os.path.join(path, ".rag")
    if os.path.exists(os.path.join(cand, "chunks.jsonl")):
        return cand
    return None

def load_chunks(index_dir):
    chunks = []
    with open(os.path.join(index_dir, "chunks.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                chunks.append(json.loads(line))
            except Exception:
                pass
    return chunks

def load_meta(index_dir):
    try:
        return json.load(open(os.path.join(index_dir, "meta.json")))
    except Exception:
        return {}

# ---------------------------------------------------------------- tokenizer
# Keep alphanumerics AND dotted section numbers so "e565", "xms1", "mcbu",
# "26.08.01" survive; also split "260801" style. Lowercased.
_TOKRE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*")
def tokenize(text):
    toks = []
    for m in _TOKRE.findall(text.lower()):
        toks.append(m)
        if "." in m:                      # also index the dotted parts
            toks.extend(p for p in m.split(".") if p)
    return toks

# ---------------------------------------------------------------- BM25
class BM25:
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.N = len(docs_tokens)
        self.docs = docs_tokens
        self.len = [len(d) for d in docs_tokens]
        self.avgdl = (sum(self.len) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in docs_tokens]
        df = Counter()
        for d in docs_tokens:
            for t in set(d):
                df[t] += 1
        self.idf = {}
        for t, n in df.items():
            # BM25+ style idf, always positive
            self.idf[t] = math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def scores(self, q_tokens):
        scores = [0.0] * self.N
        q = [t for t in q_tokens if t in self.idf]
        for i in range(self.N):
            if not self.len[i]:
                continue
            tf = self.tf[i]; dl = self.len[i]
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = self.idf[t]
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores[i] = s
        return scores

# ---------------------------------------------------------------- dense
def dense_scores(index_dir, meta, query, idx_map):
    """Return dict {chunk_row_index: cosine} or None if unavailable."""
    if not meta.get("embedded"):
        return None
    try:
        import numpy as np
    except Exception:
        return None
    emb_path = os.path.join(index_dir, "embeddings.npy")
    if not os.path.exists(emb_path):
        return None
    try:
        mat = np.load(emb_path)  # already L2-normalized at index time
    except Exception:
        return None
    if mat.shape[0] != len(idx_map):
        # index drifted from chunks; skip dense rather than mis-align
        return None
    model_name = meta.get("model")
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name)
    except Exception as e:
        print(f"  [dense] model '{model_name}' unavailable ({e.__class__.__name__}); "
              f"lexical-only.", file=sys.stderr)
        return None
    prefix = "Represent this sentence for searching relevant passages: " \
             if "bge" in (model_name or "").lower() else ""
    qv = m.encode([prefix + query], normalize_embeddings=True)[0].astype("float32")
    sims = mat @ qv
    return {i: float(sims[i]) for i in range(len(sims))}

# ---------------------------------------------------------------- fusion
def rrf(rank_lists, k=60):
    """Reciprocal Rank Fusion over {row_idx: rank(0-based)} lists."""
    fused = defaultdict(float)
    for rl in rank_lists:
        for row, rank in rl.items():
            fused[row] += 1.0 / (k + rank + 1)
    return fused

def ranks_from_scores(scores, keep):
    """scores: dict row->score. Return {row: rank} for the top-`keep` positives."""
    items = [(r, s) for r, s in scores.items() if s > 0]
    items.sort(key=lambda x: x[1], reverse=True)
    return {row: i for i, (row, _s) in enumerate(items[:keep])}

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
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--show-chars", type=int, default=600, dest="show_chars")
    args = ap.parse_args()

    index_dir = find_index(args.target)
    if not index_dir:
        print(f"No index found under {args.target} (run rag_index.py first).", file=sys.stderr)
        sys.exit(2)

    chunks = load_chunks(index_dir)
    meta = load_meta(index_dir)
    if not chunks:
        print("Index is empty.", file=sys.stderr); sys.exit(2)

    # optional filtering (applied to candidate pool)
    def keep(c):
        if args.kind and c.get("kind") != args.kind:
            return False
        if args.path and not any(p.lower() in c["path"].lower() for p in args.path):
            return False
        if args.tag:
            ctags = [t.lower() for t in c.get("tags", [])]
            if not any(t.lower() in ctags for t in args.tag):
                return False
        return True

    idx_map = list(range(len(chunks)))          # row -> chunk index (identity)
    allowed = [i for i in idx_map if keep(chunks[i])]
    allowed_set = set(allowed)

    q_tokens = tokenize(args.query)

    # lexical
    bm = BM25([tokenize(c["text"] + " " + c.get("headings", "") + " " + c.get("title", ""))
               for c in chunks])
    lex = bm.scores(q_tokens)
    lex_scores = {i: lex[i] for i in allowed_set}

    # dense
    den_scores = None
    if not args.lexical:
        den = dense_scores(index_dir, meta, args.query, idx_map)
        if den is not None:
            den_scores = {i: den[i] for i in allowed_set}

    pool = max(50, args.k * 6)
    rank_lists = [ranks_from_scores(lex_scores, pool)]
    mode = "lexical-only"
    if den_scores is not None:
        rank_lists.append(ranks_from_scores(den_scores, pool))
        mode = f"hybrid (BM25 + {meta.get('model')})"

    fused = rrf(rank_lists)
    if not fused:
        # nothing matched lexically or densely: back off to raw dense/lex top
        base = den_scores or lex_scores
        fused = {r: s for r, s in base.items()}
    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:args.k]

    results = []
    for row, score in ranked:
        c = chunks[row]
        results.append(dict(
            score=round(float(score), 5),
            path=c["path"], title=c["title"], headings=c.get("headings", ""),
            section=c.get("section", []), tags=c.get("tags", []),
            kind=c.get("kind"), text=c["text"],
        ))

    if args.as_json:
        print(json.dumps(dict(query=args.query, mode=mode,
                              index=index_dir, results=results), ensure_ascii=False, indent=2))
        return

    print(f"# Retrieval: {args.query}")
    print(f"# mode: {mode} | pool: {len(allowed)}/{len(chunks)} chunks "
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
