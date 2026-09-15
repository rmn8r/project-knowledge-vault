#!/usr/bin/env python3
"""
ocr_drawings.py — Turn a drawing set into searchable text for the RAG index.

Part of the `project-knowledge-vault` skill. Stamped/CAD-exported drawing PDFs
often have a thin or missing text layer (the content is graphical), so plain
extraction misses it. This script:
  1. tries the native text layer (pdftotext -layout) first — fast, and enough
     for vector/Revit exports;
  2. if that yields too little text, OCRs the pages (pdftoppm -> tesseract);
  3. writes one <name>.txt per drawing into the output dir, which rag_index.py
     then indexes via --source.

Incremental: skips a drawing whose .txt already exists and is newer than the
source PDF. Tolerant of cloud-only/dehydrated files (reports, never crashes).

Usage:
  python ocr_drawings.py <drawings_dir> <out_dir> [options]

Options:
  --min-text-chars N   below this many chars from the text layer, OCR the file
                       (default 400)
  --dpi N              raster DPI for OCR (default 200)
  --glob PAT           only files matching PAT (repeatable), e.g. --glob "E*.pdf"
  --limit N            process at most N files (for a scoped first pass)
  --force              re-process even if an up-to-date .txt exists
  --lang L             tesseract language (default eng)

Dependencies: poppler (pdftotext, pdftoppm, pdfinfo) and tesseract-ocr.
  Windows: install poppler + Tesseract-OCR and put both on PATH.
  Linux:   apt-get install poppler-utils tesseract-ocr
If tesseract is missing, the script still exports whatever native text exists
and reports which files would have needed OCR.
"""
import os, sys, re, subprocess, shutil, argparse, glob, tempfile, hashlib, contextlib

# Source paths and helper-tool output routinely contain characters outside a
# Windows console/redirect's default codepage (cp1252). Force UTF-8 so printing
# a filename can never abort the run.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def sh(cmd):
    """Run a helper binary. encoding/errors are pinned because text=True decodes
    with the locale codec (cp1252 on Windows): one non-cp1252 byte in pdftotext
    or tesseract output raises UnicodeDecodeError in subprocess's reader thread,
    which leaves .stdout set to None and takes the whole OCR pass down."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=600)
    except Exception as e:
        class R:  # minimal stand-in
            returncode = 1; stdout = ""; stderr = str(e)
        return R()

@contextlib.contextmanager
def readable(path):
    """Yield a path the helper binaries can actually open.

    Windows MAX_PATH applies to poppler and tesseract even where Python itself
    reads the file fine: for any source deeper than 260 characters they fail with
    "I/O Error: Couldn't open file", and poppler ignores the extended-length path
    prefix too. Stage those few files at a short temp path instead. Anything that
    already fits is yielded untouched, so the common case copies nothing."""
    if len(os.path.abspath(path)) < 250:
        yield path
        return
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1] or ".pdf")
    os.close(fd)
    try:
        shutil.copyfile(path, tmp)
    except OSError as e:
        # Staging failed; hand back the original and let the caller report it.
        print("  ! could not stage long path (%s): %s" % (e, path))
        _unlink(tmp)
        yield path
        return
    try:
        yield tmp
    finally:
        _unlink(tmp)

def _unlink(p):
    try:
        os.remove(p)
    except OSError:
        pass

def have(tool):
    return shutil.which(tool) is not None

def native_text(pdf):
    if not have("pdftotext"):
        return None
    r = sh(["pdftotext", "-layout", pdf, "-"])
    return r.stdout if r.returncode == 0 else None

def page_count(pdf):
    r = sh(["pdfinfo", pdf])
    m = re.search(r"Pages:\s+(\d+)", r.stdout)
    return int(m.group(1)) if m else 0

def ocr_pdf(pdf, dpi, lang):
    """OCR every page; return concatenated text (empty string on failure)."""
    if not (have("pdftoppm") and have("tesseract")):
        return None
    out = []
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "pg")
        sh(["pdftoppm", "-png", "-r", str(dpi), pdf, base])
        pages = sorted(glob.glob(base + "*.png"))
        for p in pages:
            r = sh(["tesseract", p, "stdout", "-l", lang, "--psm", "6"])
            if r.returncode == 0 and r.stdout:
                out.append(r.stdout)
    return "\n".join(out)

def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)

def out_path(out_dir, base, ext=".txt", limit=250):
    """Join out_dir/base+ext, shortening base if the result would exceed the
    Windows MAX_PATH limit (260). Flattened relative paths from deep document
    trees routinely blow past it, and pdftotext then writes nothing (the file
    shows up as ERR and never reaches the index). Names that already fit are
    returned untouched, so this never invalidates an existing incremental cache.

    Length is measured against the *resolved* directory: out_dir is typically
    passed on the command line as a short relative path, but MAX_PATH applies to
    the absolute path the OS ends up opening."""
    room = limit - len(os.path.abspath(out_dir)) - len(os.sep) - len(ext) - 9
    if len(base) + len(ext) <= room + 9:
        return os.path.join(out_dir, base + ext)
    h = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:8]
    return os.path.join(out_dir, base[:max(room, 16)] + "_" + h + ext)

def main():
    ap = argparse.ArgumentParser(description="OCR/extract a drawing set to text for RAG.")
    ap.add_argument("drawings_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--min-text-chars", type=int, default=400, dest="min_chars")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--glob", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--lang", default="eng")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    pats = args.glob or ["*.pdf", "*.PDF"]
    pdfs = []
    for pat in pats:
        pdfs += glob.glob(os.path.join(args.drawings_dir, "**", pat), recursive=True)
    pdfs = sorted(set(pdfs))
    if args.limit:
        pdfs = pdfs[:args.limit]

    have_ocr = have("pdftoppm") and have("tesseract")
    if not have_ocr:
        print("  [ocr] tesseract/pdftoppm not found — exporting native text only; "
              "image-only sheets will be listed as needing OCR.")

    n_native = n_ocr = n_skip = n_unreadable = n_need_ocr = 0
    for pdf in pdfs:
        rel = os.path.relpath(pdf, args.drawings_dir)
        out_txt = out_path(args.out_dir, safe(rel))
        # incremental skip
        if not args.force and os.path.exists(out_txt):
            try:
                if os.path.getmtime(out_txt) >= os.path.getmtime(pdf):
                    n_skip += 1
                    continue
            except OSError:
                pass
        # cloud-only / unreadable guard
        try:
            if os.path.getsize(pdf) == 0:
                raise OSError("zero bytes")
        except OSError:
            print(f"  ! unreadable (hydrate then re-run): {rel}")
            n_unreadable += 1
            continue

        with readable(pdf) as src:
            txt = native_text(src)
            used = "native"
            if txt is None:
                txt = ""
            if len(txt.strip()) < args.min_chars:
                if have_ocr:
                    ocr = ocr_pdf(src, args.dpi, args.lang)
                    if ocr and len(ocr.strip()) > len(txt.strip()):
                        txt = ocr
                        used = "ocr"
                        n_ocr += 1
                    else:
                        n_native += 1
                else:
                    n_need_ocr += 1
                    n_native += 1
            else:
                n_native += 1

        header = f"# SOURCE DRAWING: {rel}\n# extraction: {used}\n\n"
        try:
            with open(out_txt, "w", encoding="utf-8") as f:
                f.write(header + (txt or ""))
        except OSError as e:
            print(f"  ! could not write {out_txt}: {e}")

    print(f"  drawings: {len(pdfs)}  native: {n_native}  ocr: {n_ocr}  "
          f"skipped(up-to-date): {n_skip}  unreadable: {n_unreadable}"
          + (f"  need-ocr(no tesseract): {n_need_ocr}" if n_need_ocr else ""))
    print(f"  wrote text to {args.out_dir}/  → feed to rag_index.py via --source")

if __name__ == "__main__":
    main()
