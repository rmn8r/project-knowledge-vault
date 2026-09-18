#!/usr/bin/env python3
"""Vault health check. Usage: python audit_vault.py <vault_dir>

Resilient to cloud-only/dehydrated files (skips + reports them). Code-span aware. Reports:
unresolved links, orphan notes (0 inbound), in-degree distribution, and discipline-hub index
completeness (how many of each discipline's equipment notes its hub links)."""
import os, re, glob, sys
from collections import defaultdict, Counter
try:
    import yaml
except Exception:
    yaml = None

def read(f):
    try: return open(f, encoding="utf-8").read()
    except Exception: return None

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    root = sys.argv[1]
    files = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
    names = {os.path.splitext(os.path.basename(f))[0].lower(): f for f in files}
    aliases = {}; unread = []; txts = {}; disc = {}
    for f in files:
        t = read(f)
        if t is None: unread.append(f); continue
        txts[f] = t
        m = re.search(r"^---\n(.*?)\n---", t, re.S)
        if m:
            am = re.search(r"aliases:\s*\[(.*?)\]", m.group(1))
            if am:
                for a in am.group(1).split(","):
                    a = a.strip().strip("\"'").lower()
                    if a: aliases[a] = f
            if yaml:
                try: disc[f] = (yaml.safe_load(m.group(1)) or {}).get("discipline")
                except Exception: pass
    code = re.compile(r"```.*?```|`[^`]*`|<!--.*?-->", re.S)
    link = re.compile(r"\[\[([^\]]+?)\]\]")
    def norm(t): return t.split("|")[0].split("#")[0].split("^")[0].strip()
    out = defaultdict(set); indeg = Counter(); unresolved = defaultdict(set)
    for f, t in txts.items():
        for lk in set(link.findall(code.sub("", t))):
            k = norm(lk).lower()
            if not k: continue
            if k in names or k in aliases:
                tgt = names.get(k) or aliases[k]; out[f].add(tgt); indeg[tgt] += 1
            elif os.sep + "98 - Templates" + os.sep not in f and "README" not in f:
                unresolved[f].add(norm(lk))
    orph = [f for f in files if indeg.get(f, 0) == 0 and not any(x in f for x in ("00 - Home", "98 - Templates", "README", "Change Log"))]
    print(f"notes {len(files)} | readable {len(txts)} | cloud-only {len(unread)}")
    print("UNRESOLVED links:", sum(len(v) for v in unresolved))
    for f, v in unresolved.items(): print("  ", f, "->", sorted(v))
    print("ORPHANS (0 inbound):", len(orph))
    for f in orph: print("  ", f)
    dd = Counter(indeg.get(f, 0) for f in files)
    print("in-degree: 0:%d 1:%d 2-4:%d 5-9:%d 10+:%d" % (dd[0], dd[1], sum(dd[i] for i in (2,3,4)), sum(dd[i] for i in range(5,10)), sum(v for k,v in dd.items() if k >= 10)))
    if yaml:
        eq = [f for f in files if os.sep + "04 - Equipment" + os.sep in f]
        byd = defaultdict(list)
        for f in eq: byd[disc.get(f)].append(f)
        for d, fs in sorted((k, v) for k, v in byd.items() if k):
            hub = names.get(str(d).lower())
            if not hub: continue
            miss = [os.path.basename(x) for x in fs if x not in out.get(hub, set())]
            print(f"  discipline hub {d}: {len(fs)-len(miss)}/{len(fs)} of its equipment indexed")
    for f in unread: print("  cloud-only (hydrate to audit):", f)

if __name__ == "__main__":
    main()
