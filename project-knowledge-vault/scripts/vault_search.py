#!/usr/bin/env python3
"""
vault_search.py — Model-free, in-vault relevance search over an Obsidian vault.

Part of the `project-knowledge-vault` skill. This is the lightweight alternative
to a neural RAG index: it ranks the vault's own Markdown notes with **BM25**
(classic term-vector IR) — no embedding model, no GPU, no big index, no external
deps. It runs anywhere, including a locked-down agent sandbox, and it is **always
fresh** because by default it reads the notes live at query time.

Why this instead of neural RAG:
  * A project vault is a few hundred small notes — BM25 over them is instant.
  * Exact identifiers (E565, MCBU, 26 08 01 §3.1.A, X-61) are what these docs turn
    on, and BM25 nails those. An ID-aware tokenizer keeps them intact.
  * Frontmatter `aliases:` and `tags:` are treated as **boosted** tokens, so the
    "meaning" you encode into a note (MEDS -> USB, camboard -> camlock, glossary
    synonyms) makes a plain keyword query behave semantically. This is the
    "manual vectorization within the vault": meaning lives in the notes, not in a
    separate model. Enrich the notes and search gets smarter, for free.

Usage:
  # search live (default — no index file, always current):
  python vault_search.py "<Vault>" "who owns the annunciator wiring" [-k N] [--path P] [--tag T] [--json]

  # optional: cache a small index for a large vault (rarely needed):
  python vault_search.py build "<Vault>"        # writes <Vault>/.vaultidx.json
  #   query then reuses the cache if it is newer than every note; else falls back live.

Options:
  -k N            number of passages (default 8)
  --path SUBSTR   only chunks whose note path contains SUBSTR (repeatable; OR)
  --tag TAG       only chunks whose note carries TAG in frontmatter tags (repeatable)
  --alias-boost F multiplier for alias/tag/title tokens (default 2.5)
  --json          machine-readable output
  --show-chars N  chars of each passage to print (default 600)

Everything is local; nothing leaves the machine. `.vaultidx.json` (if you build it)
is a rebuildable cache — add it to your ignore lists.
"""
import os, sys, re, json, math, argparse, glob, time
from collections import Counter, defaultdict

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------- tokenizer
# Keep alphanumerics AND dotted section IDs so "e565", "xms1", "mcbu",
# "26.08.01", "3.1.a" survive; also index the dotted parts. Lowercased.
_TOKRE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*")
def tokenize(text):
    toks = []
    for m in _TOKRE.findall(text.lower()):
        toks.append(m)
        if "." in m:
            toks.extend(p for p in m.split(".") if p)
    return toks

# ---------------------------------------------------------------- read + chunk
def read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None

def frontmatter(text):
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

def boost_terms(path, meta):
    """Tokens that describe what a note IS — title, aliases, tags, discipline —
    indexed with extra weight so encoded meaning drives relevance."""
    parts = [os.path.splitext(os.path.basename(path))[0]]
    for key in ("aliases", "tags", "discipline", "category", "title"):
        v = meta.get(key) if isinstance(meta, dict) else None
        if isinstance(v, list):
            parts += [str(x) for x in v]
        elif v:
            parts.append(str(v))
    return parts

SECRE = re.compile(
    r"\b\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?\b|§\s?[0-9A-Z][0-9A-Z.\-]*"
    r"|\b(?:Part|Item|Section|Note|Sheet)\s+\d+[A-Za-z.\-]*"
    r"|\b[EMAPSGCVF]\d{3}(?:\.\d+)?[A-Z]?\b|\b[XGCS]-\d+\b")
def sections_in(text):
    seen, out = set(), []
    for m in SECRE.finditer(text):
        s = m.group(0).strip()
        if s not in seen:
            seen.add(s); out.append(s)
    return out[:10]

def chunk_note(path, text, alias_boost):
    """One record per heading block: {path,title,headings,section,tags,text,boost[]}."""
    meta, body = frontmatter(text)
    title = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"^#\s+(.+)$", body, re.M)
    if m:
        title = m.group(1).strip()
    tags = [str(t) for t in (meta.get("tags") or [])] if isinstance(meta, dict) else []
    boost = boost_terms(path, meta)
    recs, stack, buf = [], [], []
    def flush():
        if buf and any(l.strip() for l in buf):
            recs.append((" > ".join(stack), "\n".join(buf).strip()))
    for ln in body.splitlines():
        hm = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if hm:
            flush(); buf = []
            lvl = len(hm.group(1)); stack = stack[:lvl-1] + [hm.group(2).strip()]
        else:
            buf.append(ln)
    flush()
    if not recs:
        recs = [("", body.strip())]
    out = []
    for head, ctext in recs:
        if not ctext.strip():
            continue
        out.append(dict(path=path, title=title, headings=head,
                        section=sections_in(head + " " + ctext),
                        tags=tags, text=ctext, boost=boost, alias_boost=alias_boost))
    return out

def iter_notes(vault):
    for f in glob.glob(os.path.join(vault, "**", "*.md"), recursive=True):
        # skip caches / conflict copies noise is fine to include, but skip our own
        if re.search(r"[\\/]\.(rag|vaultidx)", f):
            continue
        yield f

def build_chunks(vault, alias_boost):
    chunks, unreadable = [], 0
    for f in iter_notes(vault):
        t = read(f)
        if t is None:
            unreadable += 1; continue
        chunks.extend(chunk_note(os.path.relpath(f, vault), t, alias_boost))
    return chunks, unreadable

# ---------------------------------------------------------------- BM25
class BM25:
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.N = len(docs_tokens)
        self.len = [sum(tf.values()) for tf in docs_tokens]
        self.avgdl = (sum(self.len) / self.N) if self.N else 0.0
        self.tf = docs_tokens
        df = Counter()
        for tf in docs_tokens:
            for t in tf:
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, q_tokens):
        q = [t for t in q_tokens if t in self.idf]
        out = [0.0] * self.N
        for i in range(self.N):
            dl = self.len[i]
            if not dl:
                continue
            tf = self.tf[i]; s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out[i] = s
        return out

def chunk_tf(c):
    """Token multiset for a chunk: body tokens + boosted title/alias/tag tokens."""
    tf = Counter(tokenize(c["text"] + " " + c.get("headings", "")))
    bt = tokenize(" ".join(c.get("boost", [])))
    if bt:
        w = max(1, int(round(c.get("alias_boost", 2.5))))
        for t in bt:
            tf[t] += w
    return tf

# ---------------------------------------------------------------- cache
def cache_path(vault):
    return os.path.join(vault, ".vaultidx.json")

def cache_fresh(vault):
    cp = cache_path(vault)
    if not os.path.exists(cp):
        return False
    try:
        cm = os.path.getmtime(cp)
        for f in iter_notes(vault):
            if os.path.getmtime(f) > cm:
                return False
        return True
    except OSError:
        return False

def do_build(vault, alias_boost):
    chunks, unreadable = build_chunks(vault, alias_boost)
    json.dump({"built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "alias_boost": alias_boost, "chunks": chunks},
              open(cache_path(vault), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  built {cache_path(vault)}  ({len(chunks)} chunks, "
          f"{unreadable} unreadable/cloud-only)  — model-free, no vectors")

def load_chunks(vault, alias_boost):
    if cache_fresh(vault):
        try:
            return json.load(open(cache_path(vault), encoding="utf-8"))["chunks"], "cache"
        except Exception:
            pass
    chunks, _ = build_chunks(vault, alias_boost)
    return chunks, "live"

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Model-free BM25 search over an Obsidian vault.")
    ap.add_argument("vault_or_cmd")
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("vault2", nargs="?", default=None)   # for: build "<vault>"
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--alias-boost", type=float, default=2.5, dest="alias_boost")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--show-chars", type=int, default=600, dest="show_chars")
    args = ap.parse_args()

    if args.vault_or_cmd == "build":
        vault = args.query or args.vault2
        if not vault or not os.path.isdir(vault):
            print("usage: vault_search.py build \"<vault>\"", file=sys.stderr); sys.exit(2)
        do_build(vault, args.alias_boost); return

    vault, query = args.vault_or_cmd, args.query
    if not query or not os.path.isdir(vault):
        print("usage: vault_search.py \"<vault>\" \"<query>\"", file=sys.stderr); sys.exit(2)

    chunks, mode = load_chunks(vault, args.alias_boost)
    if not chunks:
        print("no notes found", file=sys.stderr); sys.exit(2)

    def keep(c):
        if args.path and not any(p.lower() in c["path"].lower() for p in args.path):
            return False
        if args.tag:
            ctags = [str(t).lower() for t in c.get("tags", [])]
            if not any(t.lower() in ctags for t in args.tag):
                return False
        return True
    idx = [i for i, c in enumerate(chunks) if keep(c)]

    bm = BM25([chunk_tf(chunks[i]) for i in idx])
    scores = bm.scores(tokenize(query))
    ranked = sorted(range(len(idx)), key=lambda j: scores[j], reverse=True)[:args.k]
    results = []
    for j in ranked:
        if scores[j] <= 0:
            continue
        c = chunks[idx[j]]
        results.append(dict(score=round(scores[j], 4), path=c["path"], title=c["title"],
                            headings=c.get("headings", ""), section=c.get("section", []),
                            tags=c.get("tags", []), text=c["text"]))

    if args.as_json:
        print(json.dumps(dict(query=query, mode=mode, results=results), ensure_ascii=False, indent=2))
        return
    print(f"# vault search: {query}")
    print(f"# model-free BM25 | {mode} | {len(idx)} chunks\n")
    if not results:
        print("  (no matches — try different terms, or enrich the target note's aliases/tags)")
    for n, r in enumerate(results, 1):
        loc = r["path"] + (f"  ›  {r['headings']}" if r["headings"] else "")
        sec = f"  [{', '.join(r['section'])}]" if r["section"] else ""
        print(f"[{n}] {loc}{sec}   (score {r['score']})")
        body = re.sub(r"\s+", " ", r["text"]).strip()
        print("    " + body[:args.show_chars] + ("…" if len(body) > args.show_chars else ""))
        print()

if __name__ == "__main__":
    main()
