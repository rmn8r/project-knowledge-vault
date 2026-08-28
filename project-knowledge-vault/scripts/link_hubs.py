#!/usr/bin/env python3
"""Idempotent hub back-link indexer. Usage: python link_hubs.py <vault_dir>

Makes every hub index its children: discipline hubs (02) index equipment whose frontmatter
`discipline:` maps to the hub filename; system hubs (03) and spaces (05) index the equipment that
links to them. Safe to re-run; only adds missing links. Inserts a section before the first of
## Issues / ## Interdependencies / ## Related / ## Ties / ## Notes / ## Open, else appends."""
import os, re, glob, sys
from collections import defaultdict
try:
    import yaml
except Exception:
    yaml = None

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    root = sys.argv[1]
    files = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
    names = {os.path.splitext(os.path.basename(f))[0]: f for f in files}
    def read(f):
        try: return open(f, encoding="utf-8").read()
        except Exception: return None
    link = re.compile(r"\[\[([^\]#|]+)")
    out = defaultdict(set); disc = {}
    for b, f in names.items():
        t = read(f)
        if t is None: continue
        for l in link.findall(t): out[f].add(l)
        m = re.search(r"^---\n(.*?)\n---", t, re.S)
        if m and yaml:
            try: disc[f] = (yaml.safe_load(m.group(1)) or {}).get("discipline")
            except Exception: pass
    inn = defaultdict(set)
    for f, ts in out.items():
        for t in ts:
            if t in names: inn[names[t]].add(f)
    ANCH = ["## Issues", "## Interdependencies", "## Related", "## Ties", "## Notes", "## Open"]
    def inject(hubf, hdr, members):
        t = read(hubf)
        if t is None: return 0
        miss = [m for m in members if f"[[{m}]]" not in t]
        if not miss: return 0
        if hdr in t:
            mo = re.search(re.escape(hdr) + r"\s*\n(.*?)(\n)", t, re.S)
            t = t[:mo.start(1)] + mo.group(1).rstrip() + " · " + " · ".join(f"[[{m}]]" for m in miss) + t[mo.end(1):]
        else:
            line = hdr + "\n" + " · ".join(f"[[{m}]]" for m in miss) + "\n"
            pos = min([m.start() for a in ANCH for m in [re.search(r"^" + re.escape(a), t, re.M)] if m] or [len(t)])
            t = t[:pos] + "\n" + line + "\n" + t[pos:]
        open(hubf, "w", encoding="utf-8").write(t); return len(miss)
    n = 0
    for hubf in [f for f in files if os.sep + "02 - Disciplines" + os.sep in f]:
        hub = os.path.splitext(os.path.basename(hubf))[0]
        mem = sorted(os.path.splitext(os.path.basename(x))[0] for x, d in disc.items()
                     if d and (str(d) in hub or hub in str(d)) and os.sep + "04 - Equipment" + os.sep in x)
        if mem: n += inject(hubf, "## Indexed equipment", mem)
    for folder, hdr in [("03 - Systems", "## Related equipment"), ("05 - Spaces", "## Equipment & systems here")]:
        for hubf in [f for f in files if os.sep + folder + os.sep in f]:
            mem = sorted(os.path.splitext(os.path.basename(x))[0] for x in inn.get(hubf, ()) if os.sep + "04 - Equipment" + os.sep in x)
            if mem: n += inject(hubf, hdr, mem)
    print("links added:", n)

if __name__ == "__main__":
    main()
