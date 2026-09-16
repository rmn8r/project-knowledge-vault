#!/usr/bin/env python3
"""
rag_lexical.py — Precomputed BM25 for the project-knowledge-vault RAG layer.

Part of the `project-knowledge-vault` skill. Shared by rag_index.py (build) and
rag_query.py (search), so the tokenizer and the scoring formula can't drift apart.

WHY THIS EXISTS
rag_query.py used to build its BM25 index in memory on every single query:
read all of chunks.jsonl, tokenize every chunk, and construct one Counter per
chunk. On a few hundred notes that is instant. On a real project corpus it is
not survivable — measured on a 3.93M-chunk vault it needed ~27 GB of RAM and
many minutes *per question*, which defeats the point of having retrieval.

So the work moves to build time, once, into flat files the query memory-maps:

  lex_terms.txt    every term, one per line, sorted (UTF-8)
  lex_termoff.npy  int64[T+1]  byte offset of each term's line -> binary search
  lex_start.npy    int64[T]    where this term's postings begin
  lex_count.npy    int32[T]    how many postings it has (its df)
  lex_idf.npy      float32[T]  precomputed idf
  lex_docs.npy     int32[P]    chunk row ids, grouped by term
  lex_tf.npy       uint8[P]    term frequency in that chunk (saturating)
  lex_doclen.npy   int32[N]    token count per chunk
  lex_meta.json    counts, avgdl, k1/b, tokenizer version

A query touches only the postings slices of its own handful of terms, so cost
scales with the query, not the corpus. The vocabulary is never loaded: terms are
found by binary search over lex_termoff.npy, ~20 seeks per term.

No term is dropped — not even near-stopwords — so scores match the previous
in-memory implementation exactly rather than approximately.
"""
import os, re, json, math

TOKENIZER_VERSION = 1
K1, B = 1.5, 0.75

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


def chunk_tokens(c):
    """The text a chunk is searchable by. Must match on both sides."""
    return tokenize(c.get("text", "") + " " + c.get("headings", "") + " "
                    + c.get("title", ""))


def _paths(index_dir):
    j = lambda n: os.path.join(index_dir, n)
    return dict(
        terms=j("lex_terms.txt"), termoff=j("lex_termoff.npy"),
        start=j("lex_start.npy"), count=j("lex_count.npy"), idf=j("lex_idf.npy"),
        docs=j("lex_docs.npy"), tf=j("lex_tf.npy"), doclen=j("lex_doclen.npy"),
        meta=j("lex_meta.json"),
    )


# ------------------------------------------------------------------ build
def _flushing_print(*a, **k):
    k.setdefault("flush", True)   # a redirected nightly log must show stages live
    print(*a, **k)

def build(index_dir, chunks_path, log=_flushing_print):
    """Build the postings files from an already-written chunks.jsonl.

    Two passes over the file. The first counts document frequency per term and
    each chunk's length; that gives every term a fixed slot range, so the second
    pass can write postings straight into preallocated memmaps at
    start[term] + fill[term] with no sorting and no per-term Python lists.
    Streaming from the file (rather than an in-memory chunk list) keeps this
    independent of how much RAM the caller is already holding.
    """
    import numpy as np
    P = _paths(index_dir)

    # ---- pass 1: df, doclen, n_chunks
    log("  [lex] pass 1/2: document frequencies")
    df = {}
    doclens = []
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            try:
                c = json.loads(line)
            except Exception:
                doclens.append(0)
                continue
            ts = chunk_tokens(c)
            doclens.append(len(ts))
            for t in set(ts):
                df[t] = df.get(t, 0) + 1
    n_chunks = len(doclens)
    if not n_chunks:
        log("  [lex] no chunks; skipping lexical index")
        return False

    doclen = np.asarray(doclens, dtype="int32")
    del doclens
    np.save(P["doclen"], doclen)
    avgdl = float(doclen.sum()) / n_chunks if n_chunks else 0.0

    terms = sorted(df)
    T = len(terms)
    counts = np.empty(T, dtype="int32")
    idf = np.empty(T, dtype="float32")
    for i, t in enumerate(terms):
        n = df[t]
        counts[i] = n
        # BM25+ style idf, always positive (same formula as the old in-memory path)
        idf[i] = math.log(1 + (n_chunks - n + 0.5) / (n + 0.5))
    start = np.zeros(T, dtype="int64")
    if T > 1:
        np.cumsum(counts[:-1].astype("int64"), out=start[1:])
    total = int(counts.sum())
    log(f"  [lex] {T:,} terms, {total:,} postings, avgdl={avgdl:.1f}")

    # term -> id, reusing the df dict's memory rather than holding both
    for i, t in enumerate(terms):
        df[t] = i
    tid = df

    # sorted term file + offsets for binary search
    with open(P["terms"], "w", encoding="utf-8", newline="\n") as f:
        offs = np.empty(T + 1, dtype="int64")
        pos = 0
        for i, t in enumerate(terms):
            offs[i] = pos
            b = t.encode("utf-8")
            f.write(t + "\n")
            pos += len(b) + 1
        offs[T] = pos
    np.save(P["termoff"], offs)
    np.save(P["start"], start)
    np.save(P["count"], counts)
    np.save(P["idf"], idf)
    del terms, counts, idf, offs

    # ---- pass 2: fill postings
    log("  [lex] pass 2/2: writing postings")
    docs = np.lib.format.open_memmap(P["docs"], mode="w+", dtype="int32", shape=(total,))
    tfs = np.lib.format.open_memmap(P["tf"], mode="w+", dtype="uint8", shape=(total,))
    fill = np.zeros(T, dtype="int64")
    row = 0
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            try:
                c = json.loads(line)
            except Exception:
                row += 1
                continue
            tf_local = {}
            for t in chunk_tokens(c):
                tf_local[t] = tf_local.get(t, 0) + 1
            for t, n in tf_local.items():
                i = tid[t]
                p = start[i] + fill[i]
                docs[p] = row
                tfs[p] = 255 if n > 255 else n      # saturate; tf that high is noise
                fill[i] += 1
            row += 1
    docs.flush(); tfs.flush()
    del docs, tfs

    json.dump(dict(n_chunks=n_chunks, n_terms=T, n_postings=total, avgdl=avgdl,
                   k1=K1, b=B, tokenizer=TOKENIZER_VERSION),
              open(P["meta"], "w"), indent=2)
    log(f"  [lex] done ({total:,} postings)")
    return True


def clear(index_dir):
    """Remove lexical files so a stale set can never be read as current."""
    for p in _paths(index_dir).values():
        try:
            os.remove(p)
        except OSError:
            pass


# ------------------------------------------------------------------ query
class Lexical:
    """Memory-mapped BM25 scorer. Nothing is loaded eagerly except small arrays."""

    def __init__(self, index_dir):
        import numpy as np
        self.np = np
        P = _paths(index_dir)
        self.meta = json.load(open(P["meta"]))
        self.n = int(self.meta["n_chunks"])
        self.avgdl = float(self.meta["avgdl"]) or 1.0
        self.k1 = float(self.meta.get("k1", K1))
        self.b = float(self.meta.get("b", B))
        self.termoff = np.load(P["termoff"], mmap_mode="r")
        self.start = np.load(P["start"], mmap_mode="r")
        self.count = np.load(P["count"], mmap_mode="r")
        self.idf = np.load(P["idf"], mmap_mode="r")
        self.docs = np.load(P["docs"], mmap_mode="r")
        self.tf = np.load(P["tf"], mmap_mode="r")
        self.doclen = np.load(P["doclen"], mmap_mode="r")
        self.T = len(self.count)
        self._tf_file = open(P["terms"], "rb")

    @staticmethod
    def available(index_dir):
        P = _paths(index_dir)
        return all(os.path.exists(p) for p in P.values())

    def usable_for(self, n_chunks):
        """Guard against an index whose chunks were rewritten without a lexical
        rebuild — scoring against drifted row ids would be silently wrong."""
        return (self.n == n_chunks
                and self.meta.get("tokenizer") == TOKENIZER_VERSION
                and len(self.doclen) == n_chunks)

    def _term_at(self, i):
        a, b = int(self.termoff[i]), int(self.termoff[i + 1])
        self._tf_file.seek(a)
        return self._tf_file.read(b - a - 1).decode("utf-8", "replace")

    def term_id(self, term):
        lo, hi = 0, self.T - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            t = self._term_at(mid)
            if t == term:
                return mid
            if t < term:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def scores(self, q_tokens):
        """float32[n_chunks] of BM25 scores; zero where a chunk matched nothing."""
        np = self.np
        out = np.zeros(self.n, dtype="float32")
        dl = np.asarray(self.doclen, dtype="float32")
        norm_cache = None
        # Weight by query-term multiplicity. The previous in-memory scorer looped
        # over the raw token list, so a term repeated in the question contributed
        # once per occurrence; keep that exactly rather than quietly re-ranking
        # every query as part of a performance change.
        qtf = {}
        for t in q_tokens:
            qtf[t] = qtf.get(t, 0) + 1
        for t, w in qtf.items():
            i = self.term_id(t)
            if i is None:
                continue
            s, n = int(self.start[i]), int(self.count[i])
            if n <= 0:
                continue
            d = np.asarray(self.docs[s:s + n], dtype="int64")
            f = np.asarray(self.tf[s:s + n], dtype="float32")
            if norm_cache is None:
                norm_cache = self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            out[d] += w * float(self.idf[i]) * (f * (self.k1 + 1)) / (f + norm_cache[d])
        return out

    def close(self):
        try:
            self._tf_file.close()
        except Exception:
            pass
