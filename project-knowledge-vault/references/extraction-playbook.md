# Extraction Playbook

How to reliably get text out of a mixed document set in a sandboxed Linux shell. `scripts/extract_text.py`
automates most of this; this doc explains the reasoning and the manual fallbacks.

## Golden rules
- **Use `pdftotext -layout` (poppler) for PDFs, not pure-Python.** It is dramatically faster; a 180 MB,
  300+ page drawing set extracts in seconds, whereas pypdf can exceed a 45s shell timeout. Install
  poppler if missing (`pdftotext` is usually preinstalled).
- **Background jobs don't persist across independent shell calls.** Don't `nohup` a long job and expect
  it later — each call is its own process. Keep each extraction within one call, or chunk the work.
- **Cloud-synced (OneDrive/SharePoint/Dropbox) files** may be "online-only." If a shell command errors
  on such a path, the file isn't on disk yet — reading it once via the file-read tool downloads it.
  Warn the user before bulk-downloading many/large files.

## By file type
| Type | Tool | Notes |
|---|---|---|
| PDF (vector, e.g. CAD/Revit exports) | `pdftotext -layout in.pdf out.txt` | Text is reliable. Wide schedule tables interleave columns — parse with care or read the native sheet for exact values. |
| PDF (scanned/image) | `pdftoppm` → `tesseract` OCR | Only if `pdftotext` yields little/no text. Slower. |
| XLSX / XLSM | `openpyxl` (`data_only=True`) | Dump each sheet's non-empty rows. `pip install openpyxl --break-system-packages`. |
| CSV / TSV | read directly | — |
| PPTX | unzip + read `ppt/slides/slideN.xml`, pull `<a:t>` runs | If a slide has **no `<a:t>` text**, it's an image/exported graphic (common for 4D sequencing decks). Flag it as graphical; optionally render to PNG (LibreOffice → PDF → `pdftoppm`) and view the images. |
| DOCX | unzip + read `word/document.xml`, or `pdftotext` after converting | — |
| .MSG (Outlook) | `strings -e l` (UTF-16 body) + `strings` (ASCII) | Pulls subject/sender/body/thread. `extract-msg`/`olefile` if installable. |
| .EML | parse with Python `email` | — |
| Images (jpg/png) | view directly / `tesseract` | — |

## Index & TOC parsing
- **Drawing index:** the general index sheet (often "G-001 / Index of Drawings") lists every sheet:
  number → title → discipline. It may render as a dense multi-column table — use a regex `findall`
  for `ID  TITLE  DATE` triples across the whole text, then de-dupe, rather than line-by-line.
  Per-sheet title-block footers are a cross-check but are often incomplete via text extraction.
- **Spec TOC:** the project manual's Table of Contents lists CSI divisions and 6-digit section numbers.
  Extract the TOC page range and parse `DIVISION NN` headers + `NN NN NN Title` lines.

## What to keep
Write extracted text and helper files to a **scratch folder** (e.g., an `extracted/` dir), not the
vault. The vault holds only the synthesized notes. Keep the scratch text around during the build so you
(and subagents) can grep it for exact tags/values.

## Grep patterns that pay off
- Equipment tags & schedules: `AHU|RTU|EF-|P-[0-9]|CH-|MS-|transformer|switchboard|panelboard|pump|fan`
- Cross-cutting scope: `OFCI|OFOI|NIC|owner[- ]furnish|by others|by owner|not in contract`
- Testing/commissioning: `NETA|special inspection|testing agency|commission|hydrostatic|TAB|ASTM E`
- Conflicts/risks: mismatched values between narrative and schedule; TODO/typo/placeholder ("XX", "TBD").
