#!/usr/bin/env python3
"""Vault health check. Usage: python audit_vault.py <vault_dir>

Read-only. Resilient to cloud-only/dehydrated files (skips + reports them). Code-span aware.
Reports: unresolved links (count of distinct broken targets per note), orphan notes
(0 inbound), in-degree distribution, and discipline-hub index completeness (how many of each
discipline's equipment notes its hub links).

Aliases are read in both YAML forms - inline `aliases: [a, b]` and block lists
(`aliases:` followed by `- a` lines) - so links to an alias are never reported as broken.
Standard library only (no PyYAML needed)."""
import os, re, glob, sys
from collections import defaultdict, Counter

# Windows consoles default to cp1252; note names and markers can fall outside it.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FM = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)


def read(f):
    try:
        return open(f, encoding="utf-8").read()
    except Exception:
        return None


def fm_values(fm, key):
    """Values of a frontmatter key as a list: inline list, block list or a scalar."""
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
    out = []
    for a in items:
        a = a.split(" #")[0].strip().strip("\"'").strip()
        a = re.sub(r"^\[\[(.*?)(\|.*)?\]\]$", r"\1", a)
        if a:
            out.append(a)
    return out


def conflict_base(name, names):
    """If `name` is a sync-conflict copy of another note (OneDrive appends '-<device name>' and
    maybe '-2'), return that note's name, else None. A device token is >= 6 characters and
    mixes letters and digits, so ordinary hyphenated names are not caught."""
    base, dev, found = name, False, None
    for _ in range(40):                      # copies of copies stack suffixes; follow to the original
        m = re.match(r"^(.*)-([^\s-]+)$", base)
        if not m:
            break
        base, tok = m.group(1), m.group(2)
        if len(tok) >= 6 and re.search(r"\d", tok) and re.search(r"[A-Za-z]", tok):
            dev = True
        if dev and base.lower() in names:
            found = base
    return found


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    root = sys.argv[1]
    files = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
    names = {os.path.splitext(os.path.basename(f))[0].lower(): f for f in files}
    aliases = {}; unread = []; txts = {}; disc = {}
    for f in files:
        t = read(f)
        if t is None:
            unread.append(f); continue
        txts[f] = t
        m = FM.search(t)
        if m:
            for a in fm_values(m.group(1), "aliases"):
                aliases.setdefault(a.lower(), f)
            d = fm_values(m.group(1), "discipline")
            if d:
                disc[f] = d[0]
    code = re.compile(r"```.*?```|`[^`]*`|<!--.*?-->", re.S)
    link = re.compile(r"\[\[([^\]]+?)\]\]")
    def norm(t): return t.split("|")[0].split("#")[0].split("^")[0].strip()
    out = defaultdict(set); indeg = Counter(); unresolved = defaultdict(set)
    for f, t in txts.items():
        for lk in set(link.findall(code.sub("", t))):
            k = norm(lk).lower()
            if not k:
                continue
            if k in names or k in aliases:
                tgt = names.get(k) or aliases[k]
                if tgt not in out[f]:
                    out[f].add(tgt); indeg[tgt] += 1
            elif os.sep + "98 - Templates" + os.sep not in f and "README" not in f:
                unresolved[f].add(norm(lk))
    forks = {f: conflict_base(os.path.splitext(os.path.basename(f))[0], names) for f in files}
    forks = {f: b for f, b in forks.items() if b}
    orph = [f for f in files if indeg.get(f, 0) == 0 and f not in forks
            and not any(x in f for x in ("00 - Home", "98 - Templates", "README", "Change Log"))]
    print(f"notes {len(files)} | readable {len(txts)} | cloud-only {len(unread)} | aliases {len(aliases)}")
    print("UNRESOLVED links:", sum(len(v) for v in unresolved.values()),
          f"(in {len(unresolved)} notes)")
    for f, v in unresolved.items():
        print("  ", f, "->", sorted(v))
    print("ORPHANS (0 inbound):", len(orph))
    for f in orph:
        print("  ", f)
    dd = Counter(indeg.get(f, 0) for f in files)
    print("in-degree: 0:%d 1:%d 2-4:%d 5-9:%d 10+:%d" % (
        dd[0], dd[1], sum(dd[i] for i in (2, 3, 4)), sum(dd[i] for i in range(5, 10)),
        sum(v for k, v in dd.items() if k >= 10)))
    eq = [f for f in files if os.sep + "04 - Equipment" + os.sep in f and f not in forks]
    byd = defaultdict(list)
    for f in eq:
        byd[disc.get(f)].append(f)
    for d, fs in sorted((k, v) for k, v in byd.items() if k):
        hub = names.get(str(d).lower())
        if not hub:
            continue
        miss = [os.path.basename(x) for x in fs if x not in out.get(hub, set())]
        print(f"  discipline hub {d}: {len(fs)-len(miss)}/{len(fs)} of its equipment indexed")
    if forks:
        print(f"SYNC-CONFLICT COPIES: {len(forks)} (not orphans; merge into the original by hand, "
              "never delete without the owner's OK; take register IDs from the highest of all copies)")
        for f, b in sorted(forks.items()):
            print(f"   {os.path.relpath(f, root)}  (copy of: {b})")
    for f in unread:
        print("  cloud-only (hydrate to audit):", f)


if __name__ == "__main__":
    main()
