#!/usr/bin/env python3
"""
reindex_all.py — One command that refreshes the whole RAG index.

Part of the `project-knowledge-vault` skill. Orchestrates the three steps so a
scheduled task (or you) can keep the index current with a single call:
  1. extract_text.py  — pull text from source docs (specs/contracts/submittals)
                        into a scratch folder
  2. ocr_drawings.py  — native-text + OCR the drawing set into the same folder
  3. rag_index.py     — (re)build the vault index, including that source text
Every step is incremental, so after the first run the nightly job is cheap
(only changed files are re-done).

Everything is local. The scratch text and the .rag/ index can contain verbatim
confidential passages — keep both in the private project folder; don't publish.

Usage (paths are per-project; see the runbook for the PHX069 example):
  python reindex_all.py \
    --vault "<Project> Vault" \
    --docs  "Drawings & Specs/Specifications" --docs "Subcontracts" --docs "Submittals" \
    --drawings "Drawings & Specs" \
    --scratch "_rag_scratch"        # created next to the vault; add to ignore lists

Options:
  --no-embed        lexical-only pass (skip embeddings; any environment)
  --rebuild         force a full rebuild (clears the manifest)
  --skip-ocr        skip the drawing OCR step (notes + source docs only)
  --skip-docs       skip source-doc extraction (notes + drawings only)
  --model NAME      embedding model passed through to rag_index.py
  --ocr-limit N     cap OCR to N drawings (for a scoped first pass)
  --python EXE      python executable to invoke sub-steps with (default: this one)
"""
import os, sys, subprocess, argparse

HERE = os.path.dirname(os.path.abspath(__file__))

def run(argv):
    print("\n$ " + " ".join(argv))
    r = subprocess.run(argv)
    if r.returncode != 0:
        print(f"  [warn] step exited {r.returncode} (continuing).")
    return r.returncode

def main():
    ap = argparse.ArgumentParser(description="Refresh the whole RAG index (extract + OCR + index).")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--docs", action="append", default=[], help="source-doc folder to extract (repeatable)")
    ap.add_argument("--drawings", action="append", default=[], help="drawing folder to OCR (repeatable)")
    ap.add_argument("--scratch", default=None, help="scratch dir for extracted text (default: <vault>/.rag_source; kept inside the vault folder so it stays out of the project root, and rag_index.py ignores it)")
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--skip-ocr", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--ocr-limit", type=int, default=0)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--keep-stale", action="store_true",
                    help="never delete extracted text whose source is gone")
    args = ap.parse_args()

    py = args.python
    vault = args.vault
    scratch = args.scratch or os.path.join(vault, ".rag_source")
    extracted = os.path.join(scratch, "extracted")
    os.makedirs(extracted, exist_ok=True)

    # Each step appends the basenames it still considers live. Anything left in
    # the scratch afterwards has no source behind it any more - renamed, deleted,
    # or its output name changed - and would otherwise be indexed forever as a
    # phantom duplicate of a document that no longer exists.
    #
    # Pruning is only safe when this run covered *everything*: a skipped step, a
    # capped OCR pass, a --docs folder that wasn't there, or a step that exited
    # non-zero all mean the record is partial, and deleting "unrecorded" files
    # would throw away good extractions. Any of those disables the prune.
    record_path = os.path.join(scratch, "produced.txt")
    try:
        if os.path.exists(record_path):
            os.remove(record_path)
    except OSError:
        pass
    complete = not (args.skip_docs or args.skip_ocr or args.ocr_limit)

    print(f"== reindex_all ==\n vault:     {vault}\n scratch:   {scratch}\n embed:     {not args.no_embed}")

    # 1) source-doc text
    if not args.skip_docs:
        for d in args.docs:
            if os.path.isdir(d):
                if run([py, os.path.join(HERE, "extract_text.py"), d, extracted,
                        "--record", record_path]) != 0:
                    complete = False
            else:
                print(f"  [skip] docs folder not found: {d}")
                complete = False

    # 2) drawing OCR (native-first, OCR fallback)
    if not args.skip_ocr:
        for d in args.drawings:
            if os.path.isdir(d):
                cmd = [py, os.path.join(HERE, "ocr_drawings.py"), d, extracted,
                       "--record", record_path]
                if args.ocr_limit:
                    cmd += ["--limit", str(args.ocr_limit)]
                if run(cmd) != 0:
                    complete = False
            else:
                print(f"  [skip] drawings folder not found: {d}")
                complete = False

    # 2b) prune extracted text with no live source behind it
    if args.keep_stale:
        pass
    elif not complete:
        print("  [prune] skipped: this run did not cover every source, so the "
              "live-file record is partial.")
    elif os.path.exists(record_path):
        live = {l.strip() for l in open(record_path, encoding="utf-8") if l.strip()}
        live.add("INVENTORY.md")
        stale = [f for f in os.listdir(extracted) if f not in live]
        for f in stale:
            try:
                os.remove(os.path.join(extracted, f))
            except OSError as e:
                print(f"  [prune] could not remove {f}: {e}")
        print(f"  [prune] {len(stale)} stale extracted file(s) removed, "
              f"{len(live)-1} live")

    # 3) index (vault notes + everything we just extracted)
    idx = [py, os.path.join(HERE, "rag_index.py"), vault, "--source", extracted]
    if args.no_embed: idx.append("--no-embed")
    if args.rebuild:  idx.append("--rebuild")
    if args.model:    idx += ["--model", args.model]
    run(idx)

    print("\n== done ==  query with:  "
          f'python "{os.path.join(HERE, "rag_query.py")}" "{vault}" "<question>"')

if __name__ == "__main__":
    main()
