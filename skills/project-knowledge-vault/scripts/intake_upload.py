#!/usr/bin/env python3
"""Chat-upload intake helper. Usage:
    python intake_upload.py <upload_file> <project_root> <target_subfolder> [--name "Descriptive Name.ext"]

Hashes the upload (sha1) and scans <project_root>/<target_subfolder> for an identical file. If one
exists, nothing is copied. Otherwise copies the upload in WITHOUT overwriting: on a name clash it tries
"<stem> (uploaded copy)", then "<stem> (uploaded YYYY-MM-DD)", then numbered variants. Prints JSON:
    {"saved": "<rel path or null>", "duplicate_of": "<rel path or null>", "sha1": "..."}
Paths are relative to <project_root>. Choosing the folder and writing the vault index row are the
agent's job, not this script's. Stdlib only."""
import os, sys, json, hashlib, shutil, argparse, datetime

def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def find_duplicate(target, size, digest):
    for d, _, files in os.walk(target):
        for fn in files:
            p = os.path.join(d, fn)
            try:
                if os.path.getsize(p) == size and sha1(p) == digest:
                    return p
            except OSError:
                continue  # locked / cloud-only file: skip rather than fail the intake
    return None

def candidates(target, name):
    stem, ext = os.path.splitext(name)
    yield os.path.join(target, name)
    yield os.path.join(target, f"{stem} (uploaded copy){ext}")
    day = datetime.date.today().isoformat()
    yield os.path.join(target, f"{stem} (uploaded {day}){ext}")
    for i in range(2, 100):
        yield os.path.join(target, f"{stem} (uploaded {day}) {i}{ext}")

def copy_no_overwrite(src, target, name):
    for dst in candidates(target, name):
        try:
            with open(src, "rb") as fi, open(dst, "xb") as fo:  # "x" = fail if it exists
                shutil.copyfileobj(fi, fo)
            shutil.copystat(src, dst)
            return dst
        except FileExistsError:
            continue
    raise SystemExit(f"no free filename for {name} in {target}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("upload_file")
    ap.add_argument("project_root")
    ap.add_argument("target_subfolder")
    ap.add_argument("--name", help="save under this filename instead of the upload's own name")
    a = ap.parse_args()

    root = os.path.abspath(a.project_root)
    target = os.path.join(root, a.target_subfolder)
    os.makedirs(target, exist_ok=True)
    digest = sha1(a.upload_file)
    rel = lambda p: os.path.relpath(p, root).replace(os.sep, "/")

    dup = find_duplicate(target, os.path.getsize(a.upload_file), digest)
    if dup:
        out = {"saved": None, "duplicate_of": rel(dup), "sha1": digest}
    else:
        saved = copy_no_overwrite(a.upload_file, target, a.name or os.path.basename(a.upload_file))
        out = {"saved": rel(saved), "duplicate_of": None, "sha1": digest}
    print(json.dumps(out))

if __name__ == "__main__":
    main()
