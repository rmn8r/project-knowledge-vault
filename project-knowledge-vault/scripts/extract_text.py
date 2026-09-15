#!/usr/bin/env python3
"""Batch-extract text from a project document folder into a scratch dir.

Usage:  python extract_text.py <source_dir> <out_dir>

Handles PDF (pdftotext), XLSX (openpyxl), PPTX (slide XML), CSV/TXT, and .msg (strings).
Writes one <name>.txt per source and an INVENTORY.md (file list + sizes + PDF page counts).
Text is *working data* for building the vault, not part of the vault itself.
"""
import os, sys, re, subprocess, zipfile, shutil, hashlib

# Source paths and helper-tool output routinely contain characters outside a
# Windows console/redirect's default codepage (cp1252). Force UTF-8 so printing
# a filename can never abort the run.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

class _Failed:
    """Stand-in for CompletedProcess when a helper binary cannot run at all."""
    returncode = 1
    stdout = ""
    def __init__(self, err=""):
        self.stderr = err

def sh(cmd):
    """Run a helper binary. Never raises - a missing tool or undecodable output
    must not abort a whole folder's extraction.

    encoding/errors are pinned because text=True decodes with the locale codec
    (cp1252 on Windows): one non-cp1252 byte in a tool's output raises
    UnicodeDecodeError inside subprocess's reader thread, which both kills the
    run and leaves .stdout set to None."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except (OSError, ValueError) as e:
        return _Failed(str(e))

def pdf_pages(path):
    r = sh(["pdfinfo", path])
    m = re.search(r"Pages:\s+(\d+)", r.stdout)
    return int(m.group(1)) if m else None

def extract_pdf(path, out):
    if shutil.which("pdftotext"):
        sh(["pdftotext", "-layout", path, out])
        return os.path.exists(out)
    try:
        from pypdf import PdfReader
        r = PdfReader(path, strict=False)
        with open(out, "w", encoding="utf-8") as f:
            for i, pg in enumerate(r.pages):
                f.write(f"\n\n===== PAGE {i+1} =====\n")
                f.write(pg.extract_text() or "")
        return True
    except Exception as e:
        print("  pdf error:", e); return False

def extract_xlsx(path, out):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        with open(out, "w", encoding="utf-8") as f:
            for ws in wb.worksheets:
                f.write(f"\n## Sheet: {ws.title}\n")
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None and str(c).strip()]
                    if cells: f.write(" | ".join(cells) + "\n")
        return True
    except Exception as e:
        print("  xlsx error (need openpyxl?):", e); return False

def extract_pptx(path, out):
    try:
        z = zipfile.ZipFile(path)
        slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                        key=lambda x: int(re.search(r"(\d+)", x).group()))
        img_only = 0
        with open(out, "w", encoding="utf-8") as f:
            for i, s in enumerate(slides, 1):
                xml = z.read(s).decode("utf-8", "ignore")
                texts = [t.strip() for t in re.findall(r"<a:t>(.*?)</a:t>", xml, re.S) if t.strip()]
                if not texts: img_only += 1
                f.write(f"\n===== SLIDE {i} =====\n" + " ".join(texts) + "\n")
        if img_only:
            print(f"  note: {img_only}/{len(slides)} slides have no text (image/graphic slides)")
        return True
    except Exception as e:
        print("  pptx error:", e); return False

def _msg_strings_py(path, out, minlen=6):
    """Pure-Python stand-in for `strings`, which is a binutils tool and is not
    present on a stock Windows box. Collects runs of printable ASCII, read both
    as UTF-16LE (step 2) and as 8-bit (step 1), same as the two `strings` calls
    below."""
    try:
        raw = open(path, "rb").read()
    except OSError as e:
        print("  msg error:", e)
        return False

    def runs(data, step):
        found, cur = [], bytearray()
        for i in range(0, len(data) - step + 1, step):
            ch = data[i]
            wide_ok = step == 1 or data[i + 1] == 0
            if 0x20 <= ch < 0x7f and wide_ok:
                cur.append(ch)
                continue
            if len(cur) >= minlen:
                found.append(cur.decode("ascii", "replace"))
            cur = bytearray()
        if len(cur) >= minlen:
            found.append(cur.decode("ascii", "replace"))
        return found

    a, b = "\n".join(runs(raw, 2)), "\n".join(runs(raw, 1))
    with open(out, "w", encoding="utf-8") as f:
        f.write("=== UTF-16 strings ===\n" + a + "\n=== ASCII strings ===\n" + b)
    return True

def extract_msg(path, out):
    if not shutil.which("strings"):
        return _msg_strings_py(path, out)
    a = sh(["strings", "-e", "l", "-n", "8", path]).stdout or ""
    b = sh(["strings", "-n", "6", path]).stdout or ""
    with open(out, "w", encoding="utf-8") as f:
        f.write("=== UTF-16 strings ===\n" + a + "\n=== ASCII strings ===\n" + b)
    return True

def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)

def out_path(out_dir, base, ext=".txt", limit=250):
    """Join out_dir/base+ext, shortening base if the result would exceed the
    Windows MAX_PATH limit (260). Flattened relative paths from deep document
    trees routinely blow past it, and pdftotext then writes nothing (the file
    shows up as ERR and never reaches the index). Names that already fit are
    returned untouched, so this never invalidates an existing incremental cache."""
    p = os.path.join(out_dir, base + ext)
    if len(p) <= limit:
        return p
    h = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:8]
    room = limit - len(out_dir) - len(os.sep) - len(ext) - 9
    return os.path.join(out_dir, base[:max(room, 16)] + "_" + h + ext)

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    inv = []
    for root, _, files in os.walk(src):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            ext = fn.lower().rsplit(".", 1)[-1] if "." in fn else ""
            rel = os.path.relpath(p, src)
            size = os.path.getsize(p) // 1024
            base = safe(os.path.splitext(rel.replace(os.sep, "__"))[0])
            txt = out_path(out, base)
            pages = ""
            ok = False
            if ext == "pdf":
                n = pdf_pages(p); pages = f"{n} pp" if n else ""
                ok = extract_pdf(p, txt)
            elif ext in ("xlsx", "xlsm"): ok = extract_xlsx(p, txt)
            elif ext == "pptx": ok = extract_pptx(p, txt)
            elif ext in ("csv", "tsv", "txt", "md"):
                try: shutil.copy(p, txt); ok = True
                except Exception as e: print("  copy error:", e)
            elif ext == "msg": ok = extract_msg(p, txt)
            else:
                inv.append((rel, f"{size} KB", pages, "skipped (unsupported)")); continue
            inv.append((rel, f"{size} KB", pages, "ok" if ok else "FAILED"))
            print(f"{'ok ' if ok else 'ERR'} {rel} ({size} KB) {pages}")
    with open(os.path.join(out, "INVENTORY.md"), "w", encoding="utf-8") as f:
        f.write("# Source Inventory\n\n| File | Size | Pages | Extract |\n|---|---|---|---|\n")
        for rel, size, pages, status in inv:
            f.write(f"| {rel} | {size} | {pages} | {status} |\n")
    print(f"\nInventory: {len(inv)} files -> {os.path.join(out,'INVENTORY.md')}")

if __name__ == "__main__":
    main()
