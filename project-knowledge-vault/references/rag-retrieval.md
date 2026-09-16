# RAG Retrieval (local, hybrid) — reference

Optional retrieval layer for a built vault. Adds **semantic recall** on top of the
vault's `[[wikilinks]]` and plain text search, without giving up the exact-identifier
precision that technical documents live and die by. Two small scripts, one on-disk
index, no running service, no cloud.

> **When to add it.** For a single project, agentic keyword search (ripgrep + read the
> right note) already answers most questions. RAG earns its keep when (a) callers ask
> in concepts, not tags ("who owns the wire to the annunciator" vs. knowing it's spec
> `26 32 13 §K`), and (b) the corpus grows past what you want to grep every time, or
> spans several projects. Treat it as an **upgrade to a maintained vault**, not part of
> the first build.

## Why hybrid, not pure vectors
AEC/engineering content is full of exact identifiers — `E565`, `XMS1`, `MCBU`,
`26 08 01 §3.1.A`, `DPE Part 3 item 41`, register IDs `X-61`/`G-37`. Pure embedding
search *loses* those (it returns "something about breakers" when you asked for MCBU).
So retrieval runs two legs and fuses them:

| Leg | What it is | Catches |
|---|---|---|
| **Lexical** | BM25, pure-Python, ID-aware tokenizer | exact tags, spec/section numbers, part-item refs |
| **Semantic** | dense cosine over local embeddings | the concept when the caller doesn't know the tag |

Merge is **Reciprocal Rank Fusion** (RRF) — a passage that ranks well in *either* leg
surfaces; one that ranks well in *both* wins. A cross-encoder rerank is an easy future
add (rerank the fused top-N), left as a hook.

## Hard constraints this design honors
- **Local only.** Embeddings use a local `sentence-transformers` model. Text and vectors
  never leave the machine — mandatory for Owner-Proprietary / confidential project data.
  No hosted vector DB, no embedding API, ever.
- **Degrades gracefully.** No numpy or no sentence-transformers → the index still builds
  (chunks + metadata) and queries run **lexical-only**. Semantic recall switches on
  automatically once the deps are present. Nothing crashes on a missing model.
- **On-disk & portable.** The index is a `.rag/` folder *inside the vault*, so it rides
  along in the (cloud-synced) project folder and needs no service. A query just
  memory-maps the files — fits an ephemeral sandbox.
- **Incremental.** Re-embeds only changed/added files (content hash); drops removed ones.
- **Citable.** Chunks carry `path`, heading path, and any section-like IDs found in the
  text, so retrieved passages point back to a note + section — same traceability standard
  as the rest of the vault.

## Where the compute runs (important)
A locked-down agent sandbox usually **cannot reach PyPI or a model hub**, so the *first*
embedding build must run where the model can be fetched/cached — the **user's machine**
(the one that syncs the vault) or CI:

```bash
pip install "sentence-transformers>=2.6"          # pulls torch; one-time
python scripts/rag_index.py "<Project> Vault"      # writes <vault>/.rag/
```

After that, the on-disk index syncs with the vault and any environment can **query** it.
Queries are cheap and flat in memory at any corpus size (see "What a query actually
costs"), because the lexical index is precomputed and the dense matrix is streamed.
If the model isn't available at query time, queries fall back to lexical-only
automatically. Good cadence: a **scheduled task** on the user's machine re-runs
`rag_index.py` after docs are added (ties into the skill's Update/Sync modes).

## Corpus & chunking choices
- **Index the vault notes first** — they're the curated, high-signal layer. Add source
  text with `--source <extracted_dir>` (the scratch output of `extract_text.py`) when you
  want raw spec/contract/submittal passages too.
- **Drawings:** their extracted text is thin and the real content is graphical. Prefer the
  per-sheet **metadata notes** the vault already keeps over embedding raw drawing text;
  OCR only if a specific sheet's text is needed.
- **Chunking:** Markdown splits along **heading path** (kept as metadata); long sections
  and source text split by size with overlap. Section-like IDs (`26 08 01`, `§3.1.A`,
  `Part 3 item 41`, `E565`, `X-61`) are extracted into each chunk's `section` field so a
  hit is immediately citable.

## Usage
```bash
# build / refresh (incremental)
python scripts/rag_index.py "<Project> Vault"
python scripts/rag_index.py "<Project> Vault" --source ./_scratch/extracted   # + source text
python scripts/rag_index.py "<Project> Vault" --no-embed                       # fast lexical pass
python scripts/rag_index.py "<Project> Vault" --rebuild                        # ignore manifest

# query
python scripts/rag_query.py "<Project> Vault" "who owns the annunciator wiring"
python scripts/rag_query.py "<Project> Vault" "MCBU" --path Equipment          # filter by path
python scripts/rag_query.py "<Project> Vault" "battery cabinets" --tag equipment --json
python scripts/rag_query.py "<Project> Vault" "…" --lexical                     # force lexical
```
`rag_query.py` prints each passage with its **note path + heading + section IDs + score**,
so the agent quotes and cites the source note, then answers — same "answer first, cite the
source" habit as manual vault Q&A. Use `--json` to feed results into another step.

## Full refresh & nightly cadence
Two helpers turn the "notes-only" index into a full-coverage, self-maintaining one:
- **`ocr_drawings.py`** — exports drawing text for indexing: native text (`pdftotext`)
  first, then `pdftoppm`→`tesseract` OCR for stamped/image-only sheets. Incremental;
  tolerant of cloud-only files. Output goes to a scratch dir you feed to `--source`.
- **`reindex_all.py`** — one command that runs *extract source docs → OCR drawings →
  `rag_index.py`*, all incremental. Default scratch is `<vault>/.rag_source/` (a
  dot-folder inside the vault, ignored by the indexer and kept out of the project root).

```bash
# full deep build (notes + specs/contracts/submittals + OCR'd drawings, with embeddings)
python scripts/reindex_all.py --vault "<Project> Vault" \
  --docs "Drawings & Specs/Specifications" --docs "Subcontracts" --docs "Submittals" \
  --drawings "Drawings & Specs" --rebuild
```

**Nightly cadence.** Register `reindex_all.py` as a scheduled task **on the machine
that has the model** (Windows Task Scheduler / cron). Runs are incremental, so nightly
is cheap. This automates the *re-index* — it does **not** capture chat findings by
itself; those enter only when they're logged into notes (Living-vault). OCR of stamped
drawings is noisy (good for titles/notes/schedules, weak for one-line topology), so the
per-sheet metadata notes remain the system of record; OCR is the safety net.

## Index layout (`<vault>/.rag/`)
| File | Contents |
|---|---|
| `chunks.jsonl` | one JSON/chunk: `id, path, title, headings, section[], tags[], text, hash, mtime` |
| `embeddings.npy` | float32 `[N, D]`, row-aligned to `chunks.jsonl` (only if embedded) |
| `manifest.json` | `{relpath: {hash, mtime, n_chunks}}` for incremental rebuilds |
| `meta.json` | model, dim, counts, `embedded` flag, build time, config |
| `chunk_offsets.npy` | int64 byte offset of each chunk's line — lets a query seek the few passages it prints instead of parsing the file |
| `chunk_pathid.npy`, `chunk_kind.npy`, `paths.txt`, `path_tags.json` | small columns so `--path` / `--kind` / `--tag` filter without reading any chunk body |
| `lex_*` (8 files) | the precomputed BM25 index — sorted vocabulary + per-term postings. See below. |

### The precomputed BM25 index
`rag_query.py` used to build BM25 in memory on **every query**: parse all of
`chunks.jsonl`, tokenize every chunk, one `Counter` per chunk. That is instant for a
few hundred notes and fatal at scale — on a 3.93M-chunk vault it needed ~27 GB and
ran for minutes per question. `rag_lexical.py` moves that to build time:

| File | Contents |
|---|---|
| `lex_terms.txt` + `lex_termoff.npy` | sorted vocabulary, binary-searched; never loaded |
| `lex_start.npy`, `lex_count.npy`, `lex_idf.npy` | per-term postings slice + precomputed idf |
| `lex_docs.npy`, `lex_tf.npy` | postings grouped by term (int32 chunk row, uint8 saturating tf) |
| `lex_doclen.npy` | per-chunk token count |
| `lex_meta.json` | counts, `avgdl`, `k1`/`b`, tokenizer version |

A query reads only the postings of its own terms, so cost tracks the question rather
than the corpus. No term is dropped (not even stopwords), so scores are unchanged, not
approximated — verified against the old implementation over 68 queries: worst score
delta 1.9e-06 and zero changes in top-8 ordering.

Two guards matter. The postings store **row positions** in `chunks.jsonl`, so
`rag_index.py` deletes the whole `lex_*` set before rewriting chunks, and
`Lexical.usable_for()` refuses a set whose `n_chunks`/tokenizer version don't match —
scoring drifted rows would be silently wrong rather than obviously broken. An index
built before these files existed still queries correctly via a streaming fallback.

### What a query actually costs
Measured on the 3.93M-chunk / 6,836-file PHX069 vault (13 GB index, laptop NVMe):

| | time | peak RAM |
|---|---|---|
| `--lexical` (identifiers: E565, MCBU, "26 08 01") | **0.7 s** | ~90 MB |
| `--lexical --path <substr>` | **0.6 s** | ~90 MB |
| full hybrid | **26 s** | **2.6 GB** |
| full hybrid, `--dense-pool 20000` | 19 s | 2.6 GB |
| *(the same hybrid query before this rework)* | *never finished* | *~27 GB* |

Of the hybrid 26 s, ~12 s is importing `torch` and ~3 s is loading the model — fixed
per process, nothing to do with corpus size — and ~11 s streams `embeddings.npy`.
`--lexical` skips the import entirely, which is why it is sub-second. Reach for it
whenever the question contains the identifier you are looking for.

Add `.rag/` to `.gitignore` / `.obsidian` ignore — it's a rebuildable cache, not a note.
Because it can hold verbatim passages of confidential source text, treat it like the
source docs: keep it in the private project folder, don't publish it.

## Dependencies
- Required: Python 3.9+ (stdlib only for the lexical path).
- Optional (enables semantic leg): `numpy`, `sentence-transformers` (default model
  `BAAI/bge-small-en-v1.5`, falls back to `sentence-transformers/all-MiniLM-L6-v2`).
