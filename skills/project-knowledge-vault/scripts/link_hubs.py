#!/usr/bin/env python3
"""Idempotent hub back-link indexer.

Usage:  python link_hubs.py <vault_dir>            # preview: lists what it would add, writes nothing
        python link_hubs.py <vault_dir> --write    # apply the additions
        python link_hubs.py <vault_dir> --from-links [--write]   # legacy membership (see below)

Membership comes from what each equipment note SAYS it belongs to, in its frontmatter:
  discipline: <Discipline hub>                  -> listed on that hub in 02 - Disciplines
  system: / systems: <System hub or [[link]]>   -> listed on that hub in 03 - Systems
  space: / spaces: / location: <Space note>     -> listed on that note in 05 - Spaces
Values may be a scalar, an inline list [a, b] or a block list, and may be wikilinks. They are
matched to hub notes by file name or alias, case-insensitively.

It does NOT infer system/space membership from links. An equipment note that merely mentions a
system (a chiller note naming the electrical system that feeds it) is not a member of it; the old
link-based rule filed chillers under electrical distribution. `--from-links` restores that rule
for vaults that have no system/space frontmatter, still in preview unless --write is given.

Safe to re-run; only adds missing links. Inserts a section before the first of
## Issues / ## Interdependencies / ## Related / ## Ties / ## Notes / ## Open, else appends.
Standard library only."""
import os, re, glob, sys
from collections import defaultdict

# Windows consoles default to cp1252; note names and markers can fall outside it.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FM = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)


def fm_values(fm, key):
    m = re.search(r"^" + re.escape(key) + r":[ \t]*(.*)$", fm, re.M)
    if not m:
        return []
    v = m.group(1).strip()
    if v.startswith("[") and not v.startswith("[["):
        items = v.strip("[]").split(",")
    elif v and not v.startswith("#"):
        items = re.findall(r"\[\[[^\]]+\]\]", v) or [v]
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
        a = re.sub(r"^\[\[(.*?)(\|.*)?\]\]$", r"\1", a).split("#")[0].strip()
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write, from_links = "--write" in sys.argv, "--from-links" in sys.argv
    if not args:
        print(__doc__); sys.exit(2)
    root = args[0]
    files = glob.glob(os.path.join(root, "**", "*.md"), recursive=True)
    names = {os.path.splitext(os.path.basename(f))[0]: f for f in files}

    def read(f):
        try:
            return open(f, encoding="utf-8").read()
        except Exception:
            return None

    lookup = {k.lower(): f for k, f in names.items()}       # name or alias -> file
    fm = {}
    for f in files:
        t = read(f)
        m = FM.search(t) if t else None
        if m:
            fm[f] = m.group(1)
            for a in fm_values(m.group(1), "aliases"):
                lookup.setdefault(a.lower(), f)

    def in_folder(f, folder):
        return os.sep + folder + os.sep in f

    def resolve(vals, folder):
        return {lookup[v.lower()] for v in vals if v.lower() in lookup and in_folder(lookup[v.lower()], folder)}

    lower = {k.lower() for k in names}
    equip = [f for f in files if in_folder(f, "04 - Equipment")
             and not conflict_base(os.path.splitext(os.path.basename(f))[0], lower)]  # skip sync-conflict copies
    members = defaultdict(set)              # hub file -> equipment names
    for f in equip:
        meta = fm.get(f, "")
        nm = os.path.splitext(os.path.basename(f))[0]
        for d in fm_values(meta, "discipline"):
            for hubf in [h for h in files if in_folder(h, "02 - Disciplines")]:
                hub = os.path.splitext(os.path.basename(hubf))[0]
                if d.lower() == hub.lower() or lookup.get(d.lower()) == hubf:
                    members[hubf].add(nm)
        for key, folder in (("system", "03 - Systems"), ("systems", "03 - Systems"),
                            ("space", "05 - Spaces"), ("spaces", "05 - Spaces"),
                            ("location", "05 - Spaces")):
            for hubf in resolve(fm_values(meta, key), folder):
                members[hubf].add(nm)
    if from_links:
        link = re.compile(r"\[\[([^\]#|]+)")
        for f in equip:
            t = read(f) or ""
            nm = os.path.splitext(os.path.basename(f))[0]
            for l in set(link.findall(t)):
                hubf = lookup.get(l.strip().lower())
                if hubf and (in_folder(hubf, "03 - Systems") or in_folder(hubf, "05 - Spaces")):
                    members[hubf].add(nm)

    ANCH = ["## Issues", "## Interdependencies", "## Related", "## Ties", "## Notes", "## Open"]

    def header(hubf):
        if in_folder(hubf, "02 - Disciplines"):
            return "## Indexed equipment"
        return "## Related equipment" if in_folder(hubf, "03 - Systems") else "## Equipment & systems here"

    total = 0
    for hubf in sorted(members):
        t = read(hubf)
        if t is None:
            print("  skipped (cloud-only):", hubf); continue
        miss = sorted(m for m in members[hubf] if f"[[{m}]]" not in t and f"[[{m}|" not in t)
        if not miss:
            continue
        total += len(miss)
        print(f"{os.path.relpath(hubf, root)}: +{len(miss)} -> {', '.join(miss)}")
        if not write:
            continue
        hdr = header(hubf)
        if hdr in t:
            mo = re.search(re.escape(hdr) + r"\s*\n(.*?)(\n)", t, re.S)
            t = t[:mo.start(1)] + mo.group(1).rstrip() + " · " + " · ".join(f"[[{m}]]" for m in miss) + t[mo.end(1):]
        else:
            line = hdr + "\n" + " · ".join(f"[[{m}]]" for m in miss) + "\n"
            pos = min([m.start() for a in ANCH for m in [re.search(r"^" + re.escape(a), t, re.M)] if m] or [len(t)])
            t = t[:pos] + "\n" + line + "\n" + t[pos:]
        open(hubf, "w", encoding="utf-8").write(t)
    print(("links added: " if write else "links that would be added (preview; --write to apply): ") + str(total))


if __name__ == "__main__":
    main()
