---
name: "project-knowledge-vault"
description: "Turn a folder of project documents (drawings, specs, schedules, reports, emails, decks) into a linked Obsidian knowledge-base vault, then KEEP it alive as the project chat continues. Use to \"set up a new project / build a vault / review & organize these files / index a construction or engineering project,\" to answer questions from a document set, to integrate newly added files, or to log findings/decisions mid-conversation. Also keeps generated deliverables organized in topic subfolders and indexed with a synopsis of their contents, and offers a lightweight model-free in-vault relevance search (BM25 over the notes, no model/GPU/deps). Construction/AEC is the primary use case but the workflow is domain-agnostic."
---

# Project Knowledge Vault

Build — and then **maintain** — an [Obsidian](https://obsidian.md) vault from a folder of project documents. The vault is a network of small, interlinked Markdown notes (a "second brain") so any question ("what's the floor-flatness spec?", "is this owner-furnished?", "what's open on ROMP 3?") is answered fast, traceable to a source.

Output is a plain folder of `.md` files with `[[wikilinks]]` — opens in Obsidian, works in any editor, no lock-in.

> **The build is a few hours; the maintenance is the whole project.** Most of a vault's life is spent in Ask/Update/Sync mode, not the first build. The sections on **Living vault**, **Connectivity**, and **Project memory** are what make this level of capability transfer to a new person — treat them as first-class, not afterthoughts.

## What "good" looks like
- One hub per **discipline** and per **system**; one note per **equipment/asset**; register notes for **conflicts**, **information gaps**, **scope clarifications**; document-index notes (drawing index, spec index, **generated-deliverables index**); a **Home** map-of-content; a **glossary**; and a **change log**.
- Every note has YAML frontmatter and cites its **source** (sheet / spec section / report page).
- **Everything is cross-linked and all links resolve.** Every hub indexes its children; every note is reachable ≥2 ways; there are **no orphans**.
- Notes **carry their own meaning** — frontmatter `aliases:`/`tags:` hold the synonyms, acronyms, and alt-names for the thing (so a search for "MEDS" finds the "USB" note). This is what makes plain search behave semantically without any model.
- Anything ambiguous or contradictory is captured in a register, not silently dropped.
- A **project memory** (`CLAUDE.md` at the project root) and a **glossary** let the next session — or the next person — extend the vault instead of rebuilding it.
- Generated deliverables are **organized into topic subfolders** (not dumped in the project root) and indexed **with a synopsis of their contents** — the vault knows what's inside each report/workbook/dashboard, not just where it lives.

---
## Invocation & modes
Invoked automatically when a request matches, or explicitly via `/project-knowledge-vault`. Pick the mode from what's asked:

| Mode | Triggers | Do |
|---|---|---|
| **Build** (first time) | "set up a project," "build a vault from this folder," "review & organize these files" | Phases 0→6, then write the **project memory**. |
| **Ask** | any project question once a vault exists | Answer from the vault/sources (use `vault_search.py` for a fast relevance sweep); **then apply the Living-vault capture rules** (log material findings). |
| **Update — new files** | "I added docs, update the vault" | Extract just the new files, create/enrich notes, update registers + indexes + Home, run **hub-indexer**, re-audit. |
| **Sync — findings** | corrections/decisions/gaps mid-chat | Apply capture rules (finding→note; gap→register; conflict→register) + a dated change-log line. |
| **Catch-up** | logging has lapsed (several answers, no edits) | Run the **Catch-up recipe** below. |
| **Audit / health check** | "check the vault," "is everything linked" | Run the **audit script**; fix orphans, unresolved links, hub-index gaps. |

If the user wants a recurring refresh, offer a **scheduled task** running Update on a cadence.

---
## Workflow (first build)
**Phase 0 — Intake & scope.** Confirm the source directory (request folder access if needed; never assume the connected folder is the source). Inventory files with sizes/page-counts (`scripts/extract_text.py` prints these). Confirm with the user: vault location (default: a `… Vault/` subfolder in the project folder), depth (*comprehensive* vs *equipment-first* vs *overview*), and for drawing-heavy sets *index+schedules* vs *every sheet*. Inventory first, then ask with numbers in hand.

**Phase 1 — Extract text.** `scripts/extract_text.py <src> <out>` (PDF via pdftotext, XLSX, PPTX, CSV, .msg). Keep extracted text in a scratch folder — it's working data, not part of the vault. Large PDFs: pdftotext, never pure-Python (timeouts).

**Phase 2 — Parse structure & shared context.** Parse the drawing index and spec TOC into index notes + the discipline map. Write `PROJECT_FACTS.md` and `STYLE_GUIDE.md` to scratch (see `references/note-templates.md`). **Fixing exact hub names up front is the single most important step for link consistency.**

**Phase 3 — Skeleton & hubs.** Create the folder structure (`references/vault-structure.md`) and write hub notes yourself (don't delegate hubs — consistency). Hubs: Home, project overview/team/codes/phasing/site, one per discipline, one per system, key spaces, document indexes, **Glossary & Acronyms**.

**Phase 4 — Mine equipment (parallelize).** The bulk. If subagents are available, dispatch one per discipline group, each given the extracted-text paths, `PROJECT_FACTS.md`, `STYLE_GUIDE.md`, the target folder, and the **exact** hub-link names; have each return a compact manifest (files + one-liners + conflicts). Capture real tags, capacities, locations, interdependencies — not generic descriptions.

**Phase 5 — Registers.** Conflicts (`X-#`), Information Gaps (`G-#`), coordination clashes (`C-#`), and an owner-facing Scope Clarifications list with a recommended position each. Route every flagged item here.

**Phase 6 — Connect, verify, persist.**
1. Run the **hub-indexer** (below) so every hub links its children.
2. Run the **audit** (below); drive unresolved links → 0 and orphans → 0.
3. Optionally seed graph colors from `assets/graph.json`.
4. **Write the project memory** (`CLAUDE.md` — below), including the **deliverable folder map**.
5. Tell the user how to open it (install Obsidian → *Open folder as vault* → start at `00 - Home`).

---
## Living vault (the rule that makes this work)
- **Answer first, update second.** Fully answer in chat, THEN edit the vault, THEN report what changed in 2–4 lines.
- **Log every material finding the same turn you surface it.** A material finding = a new fact, resolved value, decision, or contradiction. Skip routine lookups that merely restate a note. Do **not** let findings pile up — that is the failure mode.
  - New fact → write it into the right note + cite source; flip any matching gap to 🟢 resolved.
  - Missing info → add a row to the Information Gaps register (with the note it belongs in + likely source).
  - Contradiction → add to the Conflicts register with the next sequential ID.
  - Owner decision / scope boundary → Scope Clarifications with a recommended position.
- **Enrich as you log (the "meaning layer").** When a finding introduces or clarifies an entity, add its **synonyms / acronyms / alt-names** to the target note's frontmatter `aliases:` and to `Glossary & Acronyms.md`. This is the cheapest, most durable form of "vectorizing" the vault: meaning encoded in the notes makes plain search and `vault_search.py` resolve *MEDS→USB*, *camboard→camlock*, etc., with no model.
- Append a dated entry (**newest first**) to `Vault Change Log.md` summarizing notes touched and IDs added/resolved.
- **Auto-apply — never ask permission to log.** Logging a material finding is automatic and part of the same turn as the answer; do **not** end a response with "want me to log this?" / "should I add this to the vault?" Just do it and report it in the 2–4 line wrap. Reserve questions for decisions that are genuinely the user's — a scope/design call, or a **destructive/irreversible** action (deleting, publishing, pushing) — never for whether to record a finding. Switch to propose-then-confirm only if the user explicitly asks.

### Catch-up recipe (when logging has lapsed)
1. Enumerate the material findings/decisions/gaps surfaced since the last change-log entry.
2. **Assign IDs up front** (read the registers' current max `X-#`/`G-#`; the project memory should track these).
3. Parallelize with subagents for the note enrichments — but **one owner (you) writes the registers and the change log** so IDs never collide. Give each agent the exact note paths, the pre-assigned IDs to reference, and "do not touch registers/change log."
4. Add the register rows + one consolidated, dated change-log entry.
5. Run the hub-indexer + audit.

---
## Comprehensive determination (sweep every relevant source before answering)
Scope, ownership, cost, and code determinations are **multi-source by nature** — never decide one from a single document. Before concluding, sweep **every** class that could bear on it, read **both sides** of each interface, reconcile, and **cite each source**:
- **Owner contract** (GCA / Work Order / PO) — base scope, what's reimbursable, what's owner-furnished.
- **Subcontracts** — the Part 3 **inclusions AND the "by others" exclusions** of **every** plausibly-responsible trade (adjacent disciplines too), not just the obvious one. A single "by others" line in one sub's scope is the tell that another trade owns it.
- **Drawings & specs** — the governing text + general/keyed notes (the operative designator — e.g. OFCI tags, "by others" notes, testing sections).
- **Submittals** — approved product data / vendor scope where it settles furnish-vs-install or factory-vs-field (only if the user hasn't said to skip them).
- **Change docs** — RFIs, CORs/PCLs, scope-delineation clarifications that may already adjudicate the point.
- **Codes/standards** — NEC / NETA / NFPA / AHJ where a code drives the requirement.

Use `scripts/vault_search.py` to find what the vault already captured, then open the **source documents** for authoritative text. Name the sources checked in the answer.

**COR review is the canonical example:** you cannot adjudicate a COR from its own narrative. Reconcile the **owner contract** (reimbursable / already in base GMP?), the **subcontract** (whose scope — and does a "by others" exclusion move it?), and the **drawings & specs** (shown/required by the contract documents?) — the COR is valid only for the delta none of those already cover. Apply the same sweep to scope-boundary ("who owns it"), NETA/testing, and OFCI/CFCI calls.

Miss this and you get single-source tunnel vision — assigning a scope to the first sub you read, or approving a COR the base contract already covers. When a determination is contested or money/schedule rides on it, quote the exact governing language, not a paraphrase.

---
## Connectivity standard (aim for this; audit against it)
The graph and backlinks *are* the value. A note nothing links to is a defect.
- **Hub → child completeness.** Every discipline hub indexes **100%** of its equipment; every system hub and every space lists its members (as back-links). Landing on any hub should reach everything in its domain in one hop.
- **Three-way reachability.** Every equipment note is reachable from its **discipline** hub, its **system** hub(s), and its **space**.
- **Process chains.** For linear spines (e.g. power: utility→MV switchgear→transformers→switchboards→bus duct/distribution boards→panelboards→white-space power→racks; cooling: chillers→pumps→valves→AHUs, and any liquid-cooling loop), give each spine note a short **"## Power chain" / "## Cooling chain"** line showing upstream→downstream with links, so the chain is traversable from any stop.
- **Bidirectional registers.** Any note named in a conflict/gap links the register back (a one-line "## Open items → [[Conflicts & Issues Register]] · [[Information Gaps & Open Questions]]").
- **No orphans.** 0 inbound links is allowed only for Home/templates/README.
- Run the **hub-indexer** whenever equipment notes are added; run the **audit** after any batch of edits.

---
## Vault search (model-free, in-vault)
For a fast relevance sweep over the notes — "which notes bear on this question?" — use **`scripts/vault_search.py`**: **BM25** (classic term-vector IR) over the vault's own Markdown, ranked and cited. **No embedding model, no GPU, no external deps, no big index** — it runs anywhere (including a locked-down agent sandbox) and is **always fresh** because it reads the notes live at query time.

```bash
python scripts/vault_search.py "<Vault>" "who owns the annunciator wiring"   # live, cited, ~instant
python scripts/vault_search.py "<Vault>" "MCBU" --path Equipment --json       # path/tag filters
python scripts/vault_search.py build "<Vault>"                                 # optional tiny .vaultidx.json cache
```
- **Meaning comes from the notes, not a model.** Frontmatter `aliases:`/`tags:`/title are indexed with a **boost**, so the synonyms you encode (the "meaning layer" above) drive relevance — searching "MEDS" surfaces the USB note because MEDS is an alias. Enrich the notes and search gets smarter, for free.
- **Deliberately not neural.** A project vault is a few hundred small notes; BM25 over them is instant and needs nothing to install or sync. This replaces heavy embedding/RAG pipelines for project-scale vaults — those add a model dependency, a multi-GB index, and a staleness/sync burden without meaningfully beating BM25-plus-good-aliases at this scale. If a project ever genuinely needs semantic recall over a huge non-note corpus, that's a separate, opt-in tool — keep it out of the default vault workflow.
- Optional `.vaultidx.json` cache (a couple of MB) is written only if you run `build`; it auto-invalidates when a note changes. Add `.vaultidx.json` to ignore lists — it's a rebuildable cache.

---
## File organization (keep the project tidy)
Generated outputs must land in the **topic subfolder that fits**, never the project root (the root should hold only `CLAUDE.md` and the vault folder). This is a first-class rule, not a nicety — a root full of loose files is the same failure mode as a vault full of orphans.
- **Before saving any deliverable, consult the folder map** in the project `CLAUDE.md` (and the folder-map header of `06 - Documents/Generated Deliverables & Reports.md`). Save into the matching subfolder.
- **If nothing fits, create a new, sensibly-named subfolder** (topic- or discipline-based, matching the project's existing naming style) rather than dropping the file in root — then add it to the folder map.
- **Keep the folder map current.** When you add an output or the user reorganizes files, refresh the paths + folder map in both the deliverables index note and the project `CLAUDE.md`, and add a dated change-log line.
- A typical construction/AEC map (adapt names to the project): `Financial/` (cost/COR/exposure/change logs) · `Schedule/` (P6 exports, baseline-shift, `Baseline XERs/`) · a commissioning/QA hub such as `Cx/` with per-activity subfolders (`Cx Inspections/`, `Cx Schedule/`, `Cx Observations/`, `Cx-Flores/`, `Energization/`, …) · `OFCI/` (owner-furnished trackers) · `Markups/` (one-lines, marked drawings) · `Team/` (org/roster). Non-AEC projects use their own equivalents (e.g. `Reports/`, `Data/`, `Exports/`, `Diagrams/`).

---
## Project memory & transferability
At the end of a build, and whenever conventions change, write/refresh a **`CLAUDE.md` at the *project root*** (the shared folder that holds both the vault and the source docs — not just inside the vault). This is what lets a future session or a new teammate extend rather than rebuild. Keep paths **relative** to the shared root so it stays valid for anyone who syncs the folder. Template:

```markdown
# <Project> — Project Memory
Working context for future sessions. This folder is the shared project root; paths below are relative to it.

## Knowledge vault
- Location: `<Project> Vault/` (Obsidian). Start at `00 - Home.md`.
- Living-vault workflow: answer first, then log findings/gaps/conflicts (+ aliases/glossary), then a dated `Vault Change Log` entry.
- Registers: Conflicts `X-#` (currently to **X-##**), Info Gaps `G-#` (to **G-##**), coordination `C-#`.
- Keep the exact hub names + templates so `[[wikilinks]]` stay consistent; run the audit after edits.
- Fast relevance search: `scripts/vault_search.py "<Project> Vault" "<question>"` (model-free BM25, runs anywhere).

## Source documents (same shared folder)
- Drawings/specs: `…/`  · Change orders/financials: `…/` · Schedule/baselines: `…/` · Submittals/subcontracts: `…/`
- Generated deliverables are filed into **topic subfolders** (below), never the project root; `06 - Documents/Generated Deliverables & Reports.md` indexes every output — path **plus a synopsis of its contents** (structure + headline figures as-of a date), with a companion `<Deliverable> (contents).md` note for substantial workbooks/dashboards.

## Deliverable folders (keep the root clean)
Save each output into the matching topic subfolder; the root holds only `CLAUDE.md`. Map (adapt names to the project):
- `Financial/` — cost/COR/change-order/exposure workbooks + owner change logs.
- `Schedule/` — P6 exports, baseline-shift reports, `Baseline XERs/`.
- `Cx/` (or the project's commissioning/QA hub) — with subfolders per activity (e.g. `Cx Inspections/`, `Cx Schedule/`, `Cx Observations/`, `Cx-Flores/`, `Energization/`).
- `OFCI/` (owner-furnished trackers) · `Markups/` (one-lines, marked drawings) · `Team/` (org/roster).
- If a new output fits none of these, **create a sensibly-named subfolder** rather than dropping it in root.

## Cloud-sync caveat (the real fragility — not the path)
Files here are cloud-synced; some are cloud-only placeholders ("dehydrated") that error on tooling reads. The Read tool hydrates them; bash/pure-python may fail with "Invalid argument" — this is NOT corruption. Fix: right-click → "Always keep on this device," let it sync, retry. Known dehydrated: `…`.
```
Also capture project shorthand in `01 - Project/Glossary & Acronyms.md` (acronyms, nicknames, codenames, vendor↔scope) so the vault decodes internal language for someone new.

---
## Generated deliverables (index them + capture their contents)
The vault is the single source of truth for spreadsheets/reports/dashboards the team asks for — generate them **from the vault's notes/registers**, **file each into the topic subfolder it belongs to** (see the folder map in the project `CLAUDE.md` — Financial/, Schedule/, the Cx/QA hub and its subfolders, OFCI/, Markups/, Team/, …), **never the project root**; if nothing fits, **create a new sensibly-named subfolder**. Use the right output skill for fidelity (**`xlsx`** spreadsheets, **`docx`** reports/letters, **`pdf`** PDFs).

**Log that it exists.** Add a row to the **`06 - Documents/Generated Deliverables & Reports.md`** index note (deliverable · **relative path incl. subfolder** · date · source note it derives from), keep a short **folder map** at the top of that note, and link it from `00 - Home`. When files get reorganized, refresh the paths + folder map here and in the project `CLAUDE.md`.

**Capture what's inside it — a path is not enough.** The vault must know each generated file's **contents**, not just that it exists, so the team can answer "what did that exposure log show / which equipment is on that rollup / what's the headline number" from the vault *without reopening the file*. For every deliverable, record a **synopsis**: purpose · **structure** (tabs/sheets · key columns/sections) · **headline figures/counts as-of a date** (totals, status splits, top items — whatever the file's point is) · how it's **derived** · how it's **refreshed** (source export, parser, cadence). For a one-off table the synopsis can live in the index row; for a **substantial deliverable** (multi-tab workbook, HTML dashboard, recurring log) create a small **companion note** in `06 - Documents` named `<Deliverable> (contents).md` holding the synopsis and **back-links to the source/equipment/register notes it draws from and feeds**, then link it from the index row. Treat the companion note like any hub — it must not be an orphan.
- **Findings flow into the vault, not just the file.** Any material fact surfaced while building a deliverable (a new value, a conflict, a resolved gap) is logged into the right note/register per the **Living-vault** rules — the deliverable is an output, the vault is the record.
- **Keep the synopsis live.** When a deliverable is regenerated/refreshed, update its headline figures + as-of date (and the structure line if columns/tabs changed) and add a dated `Vault Change Log` entry.

Common ones: phased construction schedule, buyout log by CSI division, owner scope-clarifications export, testing/commissioning matrix, equipment/submittal/long-lead logs, status/backlog reports. Flag draft/DD-stage basis; leave cost/vendor/date fields for the team.

---
## Cloud-synced files (dehydration) — operational rule
On OneDrive/SharePoint/Dropbox, files can be **cloud-only placeholders**. A read that fails with `Invalid argument` / `Errno 22` is almost always dehydration, **not corruption or a bad path**. Use the Read tool (it downloads/hydrates) for individual files; when scanning many files in bash/python, wrap reads in `try/except` and **report** unreadable files rather than crash. Remedy for the user: File Explorer → right-click file/folder → **"Always keep on this device."** Never conclude "corrupt" from a read error alone.

---
## Audit & health check (embedded — resilient)
The bundled `scripts/verify_links.py` checks link resolution but **reads files without guarding, so it aborts on the first cloud-only file.** Prefer this resilient audit — it tolerates unreadable files, strips code spans, and reports orphans, in-degree, and hub-index completeness. Write it to scratch and run `python audit.py "<vault>"`:

```python
import os,re,glob,sys
from collections import defaultdict,Counter
root=sys.argv[1]; files=glob.glob(os.path.join(root,"**","*.md"),recursive=True)
names={os.path.splitext(os.path.basename(f))[0].lower():f for f in files}; aliases={}; unread=[]
code=re.compile(r"```.*?```|`[^`]*`|<!--.*?-->",re.S); link=re.compile(r"\[\[([^\]]+?)\]\]")
def norm(t): return t.split("|")[0].split("#")[0].split("^")[0].strip()
txts={}
for f in files:
    try: txts[f]=open(f,encoding="utf-8").read()
    except Exception: unread.append(f)                 # cloud-only/dehydrated — skip, don't crash
for f,t in txts.items():
    m=re.search(r"^---\n(.*?)\n---",t,re.S)
    if m:
        am=re.search(r"aliases:\s*\[(.*?)\]",m.group(1))
        if am:
            for a in am.group(1).split(","):
                a=a.strip().strip("\"'").lower()
                if a: aliases[a]=f
out=defaultdict(set); indeg=Counter(); unresolved=defaultdict(set)
for f,t in txts.items():
    for lk in set(link.findall(code.sub("",t))):
        k=norm(lk).lower()
        if not k: continue
        if k in names or k in aliases: tgt=names.get(k) or aliases[k]; out[f].add(tgt); indeg[tgt]+=1
        elif os.sep+"98 - Templates"+os.sep not in f and "README" not in f: unresolved[f].add(norm(lk))
orph=[f for f in files if indeg.get(f,0)==0 and not any(x in f for x in ("00 - Home","98 - Templates","README","Change Log"))]
print("notes",len(files),"| readable",len(txts),"| cloud-only",len(unread))
print("UNRESOLVED links:",sum(len(v) for v in unresolved))
for f,v in unresolved.items(): print("  ",f,"->",sorted(v))
print("ORPHANS (0 inbound):",len(orph))
for f in orph: print("  ",f)
for f in unread: print("  cloud-only (hydrate to audit):",f)
```

## Hub back-link indexer (embedded — idempotent)
Makes every hub index its children: disciplines from each equipment note's frontmatter `discipline:`; systems/spaces from who links to them. Idempotent — safe to re-run; only adds missing links. Insert a `## Indexed equipment` (disciplines), `## Related equipment` (systems), or `## Equipment & systems here` (spaces) section before the first of `## Issues/## Related/## Interdependencies/## Notes`, else at end.

```python
import os,re,glob,sys,yaml
from collections import defaultdict
root=sys.argv[1]; files=glob.glob(os.path.join(root,"**","*.md"),recursive=True)
names={os.path.splitext(os.path.basename(f))[0]:f for f in files}
def read(f):
    try: return open(f,encoding="utf-8").read()
    except: return None
link=re.compile(r"\[\[([^\]#|]+)"); out=defaultdict(set); disc={}
for b,f in names.items():
    t=read(f);
    if t is None: continue
    for l in link.findall(t): out[f].add(l)
    m=re.search(r"^---\n(.*?)\n---",t,re.S)
    if m:
        try: disc[f]=(yaml.safe_load(m.group(1)) or {}).get("discipline")
        except: pass
inn=defaultdict(set)
for f,ts in out.items():
    for t in ts:
        if t in names: inn[names[t]].add(f)
ANCH=["## Issues","## Interdependencies","## Related","## Ties","## Notes","## Open"]
def inject(hubf,hdr,members):
    t=read(hubf)
    if t is None: return 0
    miss=[m for m in members if f"[[{m}]]" not in t]
    if not miss: return 0
    if hdr in t:  # extend existing section's first line
        mo=re.search(re.escape(hdr)+r"\s*\n(.*?)(\n)",t,re.S)
        t=t[:mo.start(1)]+mo.group(1).rstrip()+" · "+" · ".join(f"[[{m}]]" for m in miss)+t[mo.end(1):]
    else:
        line=hdr+"\n"+" · ".join(f"[[{m}]]" for m in miss)+"\n"
        pos=min([m.start() for a in ANCH for m in [re.search(r"^"+re.escape(a),t,re.M)] if m] or [len(t)])
        t=t[:pos]+"\n"+line+"\n"+t[pos:]
    open(hubf,"w",encoding="utf-8").write(t); return len(miss)
n=0
# disciplines: equipment whose frontmatter discipline maps to a hub filename
for hubf in [f for f in files if os.sep+"02 - Disciplines"+os.sep in f]:
    hubname=os.path.splitext(os.path.basename(hubf))[0]
    mem=sorted(os.path.splitext(os.path.basename(x))[0] for x,d in disc.items() if d and (d in hubname or hubname in str(d)) and os.sep+"04 - Equipment"+os.sep in x)
    if mem: n+=inject(hubf,"## Indexed equipment",mem)
# systems & spaces: back-links from equipment
for folder,hdr in [("03 - Systems","## Related equipment"),("05 - Spaces","## Equipment & systems here")]:
    for hubf in [f for f in files if os.sep+folder+os.sep in f]:
        mem=sorted(os.path.splitext(os.path.basename(x))[0] for x in inn.get(hubf,()) if os.sep+"04 - Equipment"+os.sep in x)
        if mem: n+=inject(hubf,hdr,mem)
print("links added:",n)
```
After running either script, re-run the audit and confirm 0 unresolved / 0 orphans.

---
## Reference files (read as needed — progressive disclosure)
- `references/vault-structure.md` — folder layout, naming, frontmatter, graph groups.
- `references/note-templates.md` — equipment/hub/system/register templates; `PROJECT_FACTS.md` / `STYLE_GUIDE.md` contents.
- `references/extraction-playbook.md` — per-file-type extraction (large PDFs, image-only decks/OCR, cloud-synced files).
- `references/update-workflow.md` — living-vault sync rules + new-files recipe.

## Scripts
- `scripts/extract_text.py` — batch extraction + inventory. `python extract_text.py <src> <out>`.
- `scripts/verify_links.py` — link check (note: guard reads / prefer the embedded resilient **audit** above on cloud-synced vaults).
- `scripts/vault_search.py` — model-free BM25 relevance search over the vault notes (alias/tag-boosted, cited, runs anywhere; no model/deps). `python vault_search.py "<vault>" "<question>" [-k N] [--path P] [--tag T] [--json]`; optional `build "<vault>"` writes a tiny `.vaultidx.json` cache.

## Companion skills (bundled)
This skill ships the Obsidian open-format skills from [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT), embedded under `references/obsidian-skills/` so PKV is self-contained, and also installed as first-class sibling skills when the full plugin is installed. Use them:
- **obsidian-markdown** (`references/obsidian-skills/obsidian-markdown/obsidian-markdown.md`) — authoritative Obsidian Flavored Markdown syntax (wikilinks, embeds `![[ ]]`, callouts, properties/frontmatter, block refs). Consult when writing or repairing note bodies so links and callouts render correctly.
- **obsidian-bases** (`references/obsidian-skills/obsidian-bases/obsidian-bases.md`) — build `.base` live database views. Prefer a Base over a hand-maintained Markdown table for any register/dashboard that must stay current (Conflicts `X-#` / Gaps `G-#` registers, the generated-deliverables index, equipment-by-discipline rollups): the Base queries note frontmatter live, so it never goes stale. Keep a static fallback table only where Bases aren't available.
- **json-canvas** (`references/obsidian-skills/json-canvas/json-canvas.md`) — author `.canvas` files for visual deliverables (power/cooling one-lines, loop diagrams, coordination maps) meant to open in Obsidian's canvas.
- **obsidian-cli** (`references/obsidian-skills/obsidian-cli/obsidian-cli.md`) — drive the vault from the CLI where available (open/search notes; plugin/theme tasks).
- **defuddle / knap** (`references/obsidian-skills/defuddle/…`, `…/knap/…`) — pull clean Markdown from web sources, and batch-render notes from JSON/CSV (e.g. one note per equipment tag from a schedule export).

**If a companion capability is needed but its skill isn't installed** (e.g. you want to build a `.base` view and `obsidian-bases` is not a registered skill in this session): proceed anyway using the embedded copy under `references/obsidian-skills/<name>/<name>.md` — it carries the full syntax, so never block work on this. Then, once per session and only when the capability actually comes up, tell the user they can install all six as first-class, independently-triggerable skills by installing the full plugin:
`/plugin marketplace add rmn8r/project-knowledge-vault`
`/plugin install project-knowledge-vault@project-knowledge-vault`
This is a one-time recommendation, not a blocker — the embedded copies already let you continue without it. Do not repeat the nudge if the user declines or if the companion skills are already installed.

## Principles
- **One install, whole workflow:** the vault skill embeds the Obsidian open-format skills (markdown/bases/canvas/cli/defuddle/knap) and the plugin also installs them as siblings — a new user installs one thing and has everything; prefer a live Base over a static table for anything that must stay current.
- **Determinations are multi-source.** Scope / COR / ownership / code calls sweep the owner contract + subcontracts (inclusions *and* "by others" exclusions, every plausibly-responsible trade) + drawings/specs + submittals + change docs + code — reconciled and cited. Never decide from one document.
- **Organize outputs, don't dump them.** Every generated file lands in the topic subfolder that fits (create one if needed); the project root stays clean; the deliverables index + folder map stay current.
- **The vault knows its outputs' contents.** Index every generated report/workbook/dashboard with a synopsis of what's inside (structure + headline figures as-of a date), not just its path — so questions get answered from the vault without reopening the file.
- **Source-traceable:** every note cites where its facts came from.
- **Small, linked notes beat big documents:** one idea per note, connected by `[[wikilinks]]`.
- **Connectivity is a feature:** hubs index children; no orphans; run the hub-indexer + audit after edits.
- **Meaning lives in the notes, not a model:** encode synonyms/acronyms as `aliases`/`tags` + a glossary; search is a model-free BM25 over the notes (`vault_search.py`) — nothing to install, sync, or let go stale.
- **Log as you go, don't ask to log:** capture material findings the same turn, automatically; only ask the user about genuine decisions or destructive actions.
- **Track problems, don't bury them:** conflicts and gaps get registers.
- **Persist for the next person:** a project-memory `CLAUDE.md` + a glossary make the skill transferable.
- **A read error on cloud storage is dehydration, not corruption:** hydrate, don't conclude "corrupt."
- **DD/draft caveat:** if documents are design/draft stage, say so in notes — values change.
