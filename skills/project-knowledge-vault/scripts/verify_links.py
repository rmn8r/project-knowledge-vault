#!/usr/bin/env python3
"""Verify that every [[wikilink]] in an Obsidian vault resolves to a note (or alias).

Usage:  python verify_links.py <vault_dir>

Ignores links inside inline `code`, ``` fenced blocks ```, and <!-- HTML comments -->, and skips a
'98 - Templates' folder (placeholder links there are expected). Aliases are read in both YAML
forms: inline `aliases: [a, b]` and block lists of `- a` lines. Files that cannot be read (e.g.
cloud-only/dehydrated OneDrive/SharePoint placeholders that raise OSError) are SKIPPED and reported,
never fatal. Exits non-zero if unresolved links remain, so it can gate a build.
"""
import os, sys, re, glob

# Windows consoles default to cp1252; note names and markers can fall outside it.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def strip_noise(t):
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"`[^`]*`", "", t)
    return t

def read(f):
    try:
        return open(f, encoding="utf-8").read()
    except Exception:
        return None

def fm_values(fm, key):
    """Values of a frontmatter key: inline `[a, b]`, a block list of `- a` lines, or a scalar."""
    m = re.search(r"^" + re.escape(key) + r":[ \t]*(.*)$", fm, re.M)
    if not m:
        return []
    v = m.group(1).strip()
    if v.startswith("["):
        items = v.strip("[]").split(",")
    elif v and not v.startswith("#"):
        items = [v]
    else:
        items = []
        for line in fm[m.end():].splitlines()[1:]:
            b = re.match(r"^\s*-\s+(.*)$", line)
            if b:
                items.append(b.group(1))
            elif line.strip() and not line.startswith((" ", "\t")):
                break
    return [a.split(" #")[0].strip().strip("\"'").strip() for a in items if a.strip()]

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    root = sys.argv[1]
    files = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
    notes, aliases, unreadable = set(), set(), []
    for f in files:
        notes.add(os.path.splitext(os.path.basename(f))[0])
        t = read(f)
        if t is None:
            unreadable.append(f); continue
        m = re.search(r"\A---\r?\n(.*?)\r?\n---", t, re.S)
        if m:
            aliases.update(fm_values(m.group(1), "aliases"))
    resolved = {x.lower() for x in notes | aliases}   # Obsidian resolves links case-insensitively
    unresolved = {}
    for f in files:
        if os.sep + "98 - Templates" + os.sep in f: continue
        t = read(f)
        if t is None: continue
        for l in re.findall(r"\[\[([^\]]+)\]\]", strip_noise(t)):
            tgt = l.split("|")[0].split("#")[0].strip()
            if tgt and tgt.lower() not in resolved:
                unresolved.setdefault(tgt, []).append(os.path.basename(f))
    print(f"Notes: {len(files)} | readable: {len(files)-len(unreadable)} | cloud-only/unreadable: {len(unreadable)}")
    for f in unreadable:
        print(f"  (skipped, hydrate to check) {f}")
    if not unresolved:
        print("All wikilinks resolve. ✔"); sys.exit(0)
    print(f"UNRESOLVED ({len(unresolved)}):")
    for tgt, where in sorted(unresolved.items()):
        print(f"  [[{tgt}]]  <- {', '.join(sorted(set(where)))}")
    sys.exit(1)

if __name__ == "__main__":
    main()
