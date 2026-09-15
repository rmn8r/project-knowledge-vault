# RAG deep-refresh + nightly re-index — runbook (for Claude Code / your machine)

Goal: build the **full** hybrid RAG index over the PHX069 vault — notes **+ source docs (specs/contracts/submittals) + OCR'd drawings** — with **local embeddings**, then set it to **re-index nightly** so it stays fresh. This must run on **your machine** (or CI), not the Cowork sandbox: the sandbox's proxy blocks PyPI and the model hub, so it can only do the lexical pass. Everything here stays **local** — no content or vectors leave the machine.

Paths below are relative to the shared project root
`…\OneDrive - Clayco, Inc\Documents\AWS Avondale TI\69`. `cd` there first.

## 0. One-time prerequisites
```powershell
# Python deps for the semantic leg (one-time; then reused):
pip install -r pkv-skill-update\scripts\requirements-rag.txt

# OCR toolchain for drawings (native-text first, OCR only image-only sheets):
#   - Poppler for Windows (pdftotext, pdftoppm, pdfinfo)  -> add its \bin to PATH
#   - Tesseract-OCR (UB-Mannheim build)                    -> add to PATH
# Verify:
pdftotext -v; pdftoppm -v; tesseract --version
```
If Tesseract isn't installed, the rebuild still runs — image-only sheets are just
listed as "need-ocr" and skipped until you add it.

**Use the GPU if there is one.** Embedding is by far the longest step of a first
build, and `pip install sentence-transformers` pulls the **CPU-only** torch wheel.
On an NVIDIA card, install the CUDA build that matches `nvidia-smi`'s CUDA version
and `rag_index.py` picks it up automatically (`--device` / `--no-fp16` override it):
```powershell
nvidia-smi                      # read the "CUDA Version" in the header
pip install --index-url https://download.pytorch.org/whl/cu132 "torch==2.14.0+cu132"
python -c "import torch; print(torch.cuda.is_available())"   # must print True
```
Measured on this project's corpus (3.9M chunks, RTX 2000 Ada laptop GPU):
CPU 26 chunks/s = ~42 h; GPU fp16 693 chunks/s = **~1.6 h**.

## 1. Hydrate the cloud-only source files first
The `Drawings & Specs\Specifications\` set and some submittals are OneDrive
**cloud-only** (gaps G-19/G-20). In File Explorer: right-click
`Drawings & Specs` and `Submittals` → **"Always keep on this device"**, let them
sync, or the extractor will report them as unreadable and skip them.

## 2. One-time deep build (notes + source + OCR drawings, with embeddings)
```powershell
python pkv-skill-update\scripts\reindex_all.py `
  --vault "AWS Avondale 069 Vault" `
  --scratch "$env:USERPROFILE\.pkv\phx069\rag_source" `
  --docs  "Drawings & Specs\Specifications" --docs "Subcontracts" --docs "Submittals" --docs "Owner Contract" --docs "Change Orders" `
  --drawings "Drawings & Specs" `
  --rebuild
```
- Extracts source-doc text → the `--scratch` folder. Keep that **off** OneDrive
  (`%USERPROFILE%\.pkv\phx069\rag_source`): it is rebuildable working data holding
  verbatim confidential text, and nothing reads it at query time. The `.rag\` index
  itself *does* stay inside the vault, so anyone else opening the shared OneDrive
  copy can query without rebuilding — `rag_query.py` needs only `.rag\`.
- OCRs the drawing set into the same folder (native text where present, OCR for
  stamped/image sheets). First OCR pass over the full E/M/A/S set is the slow part
  (tens of minutes); it's incremental afterward. To scope a first pass, add
  `--ocr-limit 200` or `--drawings "Drawings & Specs\Electrical"`.
- Builds `AWS Avondale 069 Vault\.rag\` with **embeddings** (`--rebuild` clears the
  stale manifest from the sandbox's lexical passes).

## 3. Verify the hybrid index
```powershell
python pkv-skill-update\scripts\rag_query.py "AWS Avondale 069 Vault" "who owns the annunciator wiring to the generator"
python pkv-skill-update\scripts\rag_query.py "AWS Avondale 069 Vault" "MCBU MCBG main breakers" --path Glossary
```
The header line should read **`mode: hybrid (BM25 + BAAI/bge-small-en-v1.5)`** (not
"lexical-only"). If it says lexical-only, the model didn't load — re-check step 0.

## 4. Daily re-index at 8am, with catch-up if the machine was off
A work laptop is usually off overnight, so a 2:30am task never fires. This runs at
**08:00**, and if the machine was off/asleep at 8 it runs **as soon as possible after
wake/logon** (`StartWhenAvailable`). Because the re-index is **incremental**, it always
processes only what changed **since the last successful run** — i.e. "from last update".

First create the wrapper `pkv-skill-update\scripts\reindex_phx069.cmd`:
```bat
@echo off
set "PKV_SCRATCH=%USERPROFILE%\.pkv\phx069\rag_source"
cd /d "%~dp0\..\.."
if not exist "AWS Avondale 069 Vault\.rag" mkdir "AWS Avondale 069 Vault\.rag"
python "pkv-skill-update\scripts\reindex_all.py" ^
  --vault "AWS Avondale 069 Vault" ^
  --scratch "%PKV_SCRATCH%" ^
  --docs "Drawings & Specs\Specifications" --docs "Subcontracts" --docs "Submittals" --docs "Owner Contract" --docs "Change Orders" ^
  --drawings "Drawings & Specs" >> "AWS Avondale 069 Vault\.rag\reindex.log" 2>&1
```
Then register the staged task definition (it already points at that `.cmd` and sets the
8am + catch-up behavior — plain `schtasks /SC DAILY` flags can't express "run if
missed", so use the XML):
```powershell
schtasks /Create /TN "PHX069 RAG reindex" /F /XML `
  "pkv-skill-update\scripts\phx069-rag-reindex.task.xml"

# test it now, then check it logged:
schtasks /Run /TN "PHX069 RAG reindex"
type "AWS Avondale 069 Vault\.rag\reindex.log"
```
The task XML sets: daily 08:00 · **StartWhenAvailable = true** (the catch-up) ·
runs on battery (laptop unplugged) · 3-hour limit · retry twice on failure. To change
the time, edit `<StartBoundary>…T08:00:00</StartBoundary>` in the XML and re-register.
It reflects whatever findings were **logged into the vault notes** — the index doesn't
learn from chats on its own.

## 5. Housekeeping (do once)
- Add to the repo `.gitignore` (already staged) and to any Obsidian ignore:
  `.rag/` and `.rag_source/` — both are rebuildable caches and can hold verbatim
  confidential passages; never commit or publish them.
- Do **not** put the scratch under `%LOCALAPPDATA%` if Python came from the
  Microsoft Store: that build runs with AppData redirected into its own package
  container, so it cannot see a folder written there by anything else, and
  `--source` silently matches zero files. `%USERPROFILE%\.pkv\` is fine.
- Decide deliberately which of the two syncs. `.rag_source/` is pure working data
  — point `--scratch` at a local-only path. `.rag/` is what `rag_query.py` reads,
  so leaving it in the synced vault is what lets a second person query the shared
  copy; that does put chunk text and vectors in the tenant, which is the trade.
- **Delete the stray empty folder `_rag_scratch\` in the project root** (created by an
  earlier sandbox smoke-test; the sandbox couldn't remove it due to a OneDrive lock).
- The `.rag/` index lives *inside* the vault as a dot-folder, so it stays out of the
  project root and Obsidian ignores it. The scratch is deliberately outside (above).

## Notes
- **Confidentiality:** local model, local `.rag/` + `.rag_source/`. Nothing is sent
  to any third party. Both caches hold verbatim passages — keep them private.
- **Size:** budget for it. This corpus extracts to ~3.5 GB of text and indexes to
  3.9M chunks: ~6 GB of vectors plus a multi-GB `chunks.jsonl`. `rag_index.py`
  streams embeddings into a memory-mapped array, so peak RAM stays flat, but the
  disk footprint is real.
- **Coverage reality:** OCR of stamped drawings is noisy — it makes titles, notes, and
  schedule text searchable, but the *graphical* content (one-line topology, terminal
  wiring) still lives best in the per-sheet metadata notes. Log the details that matter
  into notes; OCR is the safety net, not the system of record.
- **Freshness:** re-index after logging findings. The nightly task automates the
  re-index; the *logging* is the living-vault habit during each chat.
