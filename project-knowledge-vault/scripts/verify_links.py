#!/usr/bin/env python3
"""Verify that every [[wikilink]] in an Obsidian vault resolves to a note (or alias).

Usage:  python verify_links.py <vault_dir>

Ignores links inside inline `code`, ``` fenced blocks ```, and <!-- HTML comments -->, and skips a
'98 - Templates' folder (placeholder links there are expected). Exits non-zero if unresolved links
remain, so it can gate a build.
"""
import os, sys, re, glob

def strip_noise(t):
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)      # html comments
    t = re.sub(r"```.*?```", "", t, flags=re.S)        # fenced code
    t = re.sub(r"`[^`]*`", "", t)                       # inline code
    return t

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    root = sys.argv[1]
    files = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
    notes, aliases = set(), set()
    for f in files:
        notes.add(os.path.splitext(os.path.basename(f))[0])
        m = re.search(r"^---\n(.*?)\n---", open(f, encoding="utf-8").read(), re.S)
        if m:
            am = re.search(r"aliases:\s*\[(.*?)\]", m.group(1))
            if am:
                aliases.update(a.strip().strip('"').strip("'") for a in am.group(1).split(",") if a.strip())
    resolved = notes | aliases
    unresolved = {}
    for f in files:
        if os.sep + "98 - Templates" + os.sep in f: continue
        t = strip_noise(open(f, encoding="utf-8").read())
        for l in re.findall(r"\[\[([^\]]+)\]\]", t):
            tgt = l.split("|")[0].split("#")[0].strip()
            if tgt and tgt not in resolved:
                unresolved.setdefault(tgt, []).append(os.path.basename(f))
    print(f"Notes: {len(files)} | distinct link targets checked.")
    if not unresolved:
        print("All wikilinks resolve. ✔"); sys.exit(0)
    print(f"UNRESOLVED ({len(unresolved)}):")
    for tgt, where in sorted(unresolved.items()):
        print(f"  [[{tgt}]]  <- {', '.join(sorted(set(where)))}")
    sys.exit(1)

if __name__ == "__main__":
    main()
