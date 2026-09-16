---
name: "project-knowledge-vault"
description: "Turn a folder of project documents (drawings, specs, schedules, reports, emails, decks) into a linked Obsidian knowledge-base vault, then KEEP it alive as the project chat continues. Use to \"set up a new project / build a vault / review & organize these files / index a construction or engineering project,\" to answer questions from a document set, to integrate newly added files, or to log findings/decisions mid-conversation. Also keeps generated deliverables organized in topic subfolders and indexed with a synopsis of their contents, and offers an optional local, hybrid (lexical + semantic) RAG retrieval layer for concept-level search over a maintained vault. Construction/AEC is the primary use case but the workflow is domain-agnostic."
---

# Project Knowledge Vault

Build — and then **maintain** — an [Obsidian](https://obsidian.md) vault from a folder of project documents. The vault is a network of small, interlinked Markdown notes (a "second brain") so any question ("what's the floor-flatness spec?", "is this owner-furnished?", "what's open on ROMP 3?") is answered fast, traceable to a source.

Output is a plain folder of `.md` files with `[[wikilinks]]` — opens in Obsidian, works in any editor, no lock-in.

> **The build is a few hours; the maintenance is the whole project.** Most of a vault's life is spent in Ask/Update/Sync mode, not the first build. The sections on **Living vault**, **Connectivity**, and **Project memory** are what make this level of capability transfer to a new person — treat them as first-class, not afterthoughts.

## What "good" looks like
- One hub per **discipline** and per **system**; one note per **equipment/asset**; register notes for **conflicts**, **information gaps**, **scope clarifications**; document-index notes (drawing index, spec index, **generated-deliverables index**); a **Home** map-of-content; a **glossary**; and a **change log**.
- Every note has YAML frontmatter and cites its **source** (sheet / spec section / report page).
- **Everything is cross-linked and all links resolve.** Every hub indexes its children; every note is reachable ≥2 ways; there are **no orphans**.
- Anything ambiguous or contradictory is captured in a register, not silently dropped.
- A **project memory** (`CLAUDE.md` at the project root) and a **glossary** let the next session — or the next person — extend the vault instead of rebuilding it.
- Generated deliverables are **organized into topic subfolders** (not dumped in the project root) and indexed **with a synopsis of their contents** — the vault knows what's inside each report/workbook/dashboard, not just where it lives.

---
## Invocation & modes
Invoked automatically when a request matches, or explicitly via `/project-knowledge-vault`. Pick the mode from what's asked:

| Mode | Triggers | Do |
|---|---|---|
| **Build** (first time) | "set up a project," "build a vault from this folder," "review & organize these files" | Phases 0→6, then write the **project memory**. |
| **Ask** | any project question once a vault exists | Answer from the vault/sources; **then apply the Living-vault capture rules** (log material findings). |
| **Update — new files** | "I added docs, update the vault" | Extract just the new files, create/enrich notes, update registers + indexes + Home, run **hub-indexer**, re-audit. |
| **Sync — findings** | corrections/decisions/gaps mid-chat | Apply capture rules (finding→note; gap→register; conflict→register) + a dated change-log line. |
| **Catch-up** | logging has lapsed (several answers, no edits) | Run the **Catch-up recipe** below. |
| **Audit / health check** | "check the vault," "is everything linked" | Run the **audit script**; fix orphans, unresolved links, hub-index gaps. |
| **Retrieve (RAG)** *(optional)* | large/maintained vault; concept-level questions where the caller doesn't know the exact tag; "add semantic search" | Build/refresh the local hybrid index and query it (see **Retrieval** below). Answer from the cited passages; still apply Living-vault capture. |

If the user wants a recurring refresh, offer a **scheduled task** running Update (and, if RAG is enabled, `rag_index.py`) on a cadence.

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
- Append a dated entry (**newest first**) to `Vault Change Log.md` summarizing notes touched and IDs added/resolved.
- Auto-apply by default (don't wait for per-edit approval) unless the user prefers propose-then-confirm.

### Catch-up recipe (when logging has lapsed)
1. Enumerate the material findings/decisions/gaps surfaced since the last change-log entry.
2. **Assign IDs up front** (read the registers' current max `X-#`/`G-#`; the project memory should track these).
3. Parallelize with subagents for the note enrichments — but **one owner (you) writes the registers and the change log** so IDs never collide. Give each agent the exact note paths, the pre-assigned IDs to reference, and "do not touch registers/change log."
4. Add the register rows + one consolidated, dated change-log entry.
5. Run the hub-indexer + audit.

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
## Retrieval (optional local RAG layer)
For a maintained vault, add **semantic recall** on top of `[[wikilinks]]` + keyword search without losing exact-identifier precision. Two scripts, one on-disk index, **no service, no cloud**. See `references/rag-retrieval.md` for the full rationale.

**When to add it.** Agentic keyword search (ripgrep + read the right note) answers most single-project questions already. RAG earns its keep when callers ask in **concepts, not tags** ("who owns the wire to the annunciator" vs. knowing it's spec `26 32 13 §K`), or the corpus outgrows what you want to grep every time / spans several projects. It's an **upgrade to a maintained vault**, not part of the first build — and the highest-value prep is still clean, well-tagged notes and registers, which make *both* keyword and RAG search accurate.

**Hybrid, not pure vectors.** Technical docs live on exact IDs (`E565`, `XMS1`, `MCBU`, `26 08 01 §3.1.A`, `X-61`). Retrieval runs **BM25 lexical** (ID-aware tokenizer — nails those) **+ dense semantic** (catches the concept), fused with Reciprocal Rank Fusion. Pure embeddings lose the tags; keep both legs.

**Non-negotiables (baked into the scripts):**
- **Local only.** Embeddings use a local `sentence-transformers` model; text and vectors never leave the machine — required for Owner-Proprietary/confidential data. No hosted vector DB, no embedding API.
- **Degrades gracefully.** No `numpy`/`sentence-transformers` → still builds and queries **lexical-only**; semantic switches on automatically once the deps exist. Nothing crashes on a missing model.
- **On-disk, portable, incremental.** Index is a `.rag/` folder inside the vault (rides the synced project folder, no service); re-embeds only changed files (content hash).
- **Citable.** Chunks carry `path` + heading path + section-like IDs, so every hit points back to a note/section — same traceability standard as the rest of the vault.

**Where compute runs.** A locked-down agent sandbox usually can't reach PyPI/model hubs, so the **first embedding build runs on the user's machine** (the one syncing the vault) or CI; after that the on-disk index syncs and any environment can query it (falling back to lexical if the model isn't present). Offer a **scheduled task** to re-run `rag_index.py` after docs are added.

```bash
# on a machine with the model available (one-time dep, then reuse):
pip install "sentence-transformers>=2.6"
python scripts/rag_index.py "<Project> Vault"                 # writes <vault>/.rag/ (incremental)
python scripts/rag_index.py "<Project> Vault" --source ./_scratch/extracted   # + raw source text
python scripts/rag_index.py "<Project> Vault" --no-embed      # fast lexical-only pass (any env)

python scripts/rag_query.py "<Project> Vault" "who owns the annunciator wiring"
python scripts/rag_query.py "<Project> Vault" "MCBU" --path Equipment    # path/tag/kind filters
python scripts/rag_query.py "<Project> Vault" "battery cabinets" --json   # for programmatic use
python scripts/rag_query.py "<Project> Vault" "E565" --lexical            # sub-second; no torch
```
**Query cost.** A hybrid query pays a fixed ~15 s to import `torch` and load the
model, then streams the vectors; `--lexical` skips that entirely and answers in well
under a second, so prefer it whenever the question already contains the identifier
(`E565`, `MCBU`, `26 08 01`). Both are flat in memory (~2.6 GB hybrid / ~90 MB
lexical) at any corpus size, because `rag_index.py` precomputes the BM25 postings
(`rag_lexical.py`) and the query memory-maps them instead of rebuilding the index per
question. If a hybrid query ever runs for minutes and climbs past 20 GB, the `lex_*`
files are missing or stale — re-run `rag_index.py`.
Each hit prints **note path + heading + section IDs + score** — quote and cite the source note, then answer (same "answer first, cite the source" habit as manual Q&A). Index the curated notes first; for deeper recall add source-doc text (`--source`) and, for stamped drawings, OCR (`ocr_drawings.py`) — but the graphical content still lives best in per-sheet metadata notes, so OCR is the safety net, not the system of record. Add `.rag/` and `.rag_source/` to ignore lists — both are rebuildable local caches that can hold verbatim confidential passages; keep them in the private folder, never publish them.

**Keeping it fresh (it is not auto-learning).** The index is a snapshot: it reflects the vault only after findings are **logged into notes** (the Living-vault habit) and a **re-index** runs. `reindex_all.py` does extract + OCR + index in one incremental pass; wire it to a **nightly scheduled task on the machine that has the model** (the sandbox can't embed). So "learns after each chat" = *log the finding, then the nightly re-index picks it up*.

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
- Living-vault workflow: answer first, then log findings/gaps/conflicts, then a dated `Vault Change Log` entry.
- Registers: Conflicts `X-#` (currently to **X-##**), Info Gaps `G-#` (to **G-##**), coordination `C-#`.
- Keep the exact hub names + templates so `[[wikilinks]]` stay consistent; run the audit after edits.

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
- `references/rag-retrieval.md` — optional local hybrid RAG layer: rationale, constraints, chunking, usage.

## Scripts
- `scripts/extract_text.py` — batch extraction + inventory. `python extract_text.py <src> <out>`.
- `scripts/verify_links.py` — link check (note: guard reads / prefer the embedded resilient **audit** above on cloud-synced vaults).
- `scripts/rag_index.py` — build/refresh the local hybrid RAG index (`.rag/` in the vault). Local embeddings, incremental, lexical-only fallback. `python rag_index.py "<vault>" [--source <dir>] [--no-embed]`.
- `scripts/rag_query.py` — hybrid (BM25 + dense, RRF-fused) retrieval with path/tag filters and cited passages. `python rag_query.py "<vault>" "<question>" [-k N] [--json]`.
- `scripts/ocr_drawings.py` — native-text + OCR a drawing set to text for indexing (pdftotext, then pdftoppm→tesseract for image-only sheets); incremental. `python ocr_drawings.py "<drawings>" "<out>"`.
- `scripts/reindex_all.py` — one-command refresh: extract source docs + OCR drawings + `rag_index.py`, all incremental. What a nightly scheduled task runs. `python reindex_all.py --vault "<vault>" --docs "<specs>" --drawings "<dwgs>"`.
- `scripts/requirements-rag.txt` — pins the optional embedding deps (numpy, sentence-transformers).

## Principles
- **Organize outputs, don't dump them.** Every generated file lands in the topic subfolder that fits (create one if needed); the project root stays clean; the deliverables index + folder map stay current.
- **The vault knows its outputs' contents.** Index every generated report/workbook/dashboard with a synopsis of what's inside (structure + headline figures as-of a date), not just its path — so questions get answered from the vault without reopening the file.
- **Source-traceable:** every note cites where its facts came from.
- **Small, linked notes beat big documents:** one idea per note, connected by `[[wikilinks]]`.
- **Connectivity is a feature:** hubs index children; no orphans; run the hub-indexer + audit after edits.
- **Retrieval stays local and hybrid:** if you add RAG, embeddings run on a local model (nothing leaves the machine) and lexical BM25 always rides alongside dense search so exact tags/IDs never get lost.
- **Log as you go:** capture material findings the same turn — don't let them pile up.
- **Track problems, don't bury them:** conflicts and gaps get registers.
- **Persist for the next person:** a project-memory `CLAUDE.md` + a glossary make the skill transferable.
- **A read error on cloud storage is dehydration, not corruption:** hydrate, don't conclude "corrupt."
- **DD/draft caveat:** if documents are design/draft stage, say so in notes — values change.

