---
name: "project-knowledge-vault"
description: "Turn a folder of project documents (drawings, specs, schedules, reports, emails, decks) into a linked Obsidian knowledge-base vault, then KEEP it alive as the project chat continues. Use to \"set up a new project / build a vault / review & organize these files / index a construction or engineering project,\" to answer questions from a document set, to integrate newly added files (including any file the user drags or attaches into the chat, which is auto-saved to the right project folder and indexed), or to log findings/decisions mid-conversation. Also keeps generated deliverables organized in topic subfolders and indexed with a synopsis of their contents, offers model-free in-vault search (BM25, no deps), and analyzes Primavera P6 .xer schedules (driving path, update/baseline diff, milestone gap checks between baselines/TIAs, DCMA 14-point, EV) for any .xer question. Construction/AEC is the primary use case but the workflow is domain-agnostic."
---

# Project Knowledge Vault

Build — and then **maintain** — an [Obsidian](https://obsidian.md) vault from a folder of project documents. The vault is a network of small, interlinked Markdown notes (a "second brain") so any question ("what's the floor-flatness spec?", "is this owner-furnished?", "what's open on ROMP 3?") is answered fast, traceable to a source.

Output is a plain folder of `.md` files with `[[wikilinks]]` — opens in Obsidian, works in any editor, no lock-in.

> **The build is a few hours; the maintenance is the whole project.** Most of a vault's life is spent in Ask/Update/Sync mode, not the first build. The sections on **Living vault**, **Chat-upload intake**, **Connectivity**, and **Project memory** are what make this level of capability transfer to a new person — treat them as first-class, not afterthoughts.

## What "good" looks like
- One hub per **discipline** and per **system**; one note per **equipment/asset**; register notes for **conflicts**, **information gaps**, **scope clarifications**; document-index notes (drawing index, spec index, **generated-deliverables index**, **uploaded-files index**); a **Home** map-of-content; a **glossary**; and a **change log**.
- Every note has YAML frontmatter and cites its **source** (sheet / spec section / report page).
- **Everything is cross-linked and all links resolve.** Every hub indexes its children; every note is reachable ≥2 ways; there are **no orphans**.
- Notes **carry their own meaning** — frontmatter `aliases:`/`tags:` hold the synonyms, acronyms, and alt-names for the thing (so a search for "MEDS" finds the "USB" note). This is what makes plain search behave semantically without any model.
- Anything ambiguous or contradictory is captured in a register, not silently dropped.
- A **project memory** (`CLAUDE.md` at the project root) and a **glossary** let the next session — or the next person — extend the vault instead of rebuilding it.
- Generated deliverables are **organized into topic subfolders** (not dumped in the project root) and indexed **with a synopsis of their contents** — the vault knows what's inside each report/workbook/dashboard, not just where it lives.
- Files the user **drops into the chat** are saved into the right project folder and indexed with a synopsis — nothing the user shares is lost when the session's temporary uploads folder is cleared.

---
## Invocation & modes
Invoked automatically when a request matches, or explicitly via `/project-knowledge-vault`. Pick the mode from what's asked:

| Mode | Triggers | Do |
|---|---|---|
| **Build** (first time) | "set up a project," "build a vault from this folder," "review & organize these files" | Phases 0→6, then write the **project memory**. |
| **Ask** | any project question once a vault exists | Answer from the vault/sources (use `vault_search.py` for a fast relevance sweep); **then apply the Living-vault capture rules** (log material findings). |
| **Update — new files** | "I added docs, update the vault" | Extract just the new files, create/enrich notes, update registers + indexes + Home, run **hub-indexer**, re-audit. |
| **Intake — file dropped in chat** | the user drags/attaches **any** file into the conversation (with or without a request about it) | Automatically run the **Chat-upload intake** recipe: save it to the matching project folder, index it with a synopsis, back-link it, log findings. Never ask first. |
| **Sync — findings** | corrections/decisions/gaps mid-chat | Apply capture rules (finding→note; gap→register; conflict→register) + a dated change-log line. |
| **Catch-up** | logging has lapsed (several answers, no edits) | Run the **Catch-up recipe** below. |
| **Schedule (P6 .xer)** | any question about an `.xer` (critical/driving path, what slipped between updates, schedule quality, EV) | Run `scripts/xer_tool.py` (see **P6 schedules** below); never hand-parse the XER. Log findings per the Living-vault rules. |
| **Audit / health check** | "check the vault," "is everything linked" | Run the **audit script**; fix orphans, unresolved links, hub-index gaps. |

If the user wants a recurring refresh, offer a **scheduled task** running Update on a cadence.

---
## Workflow (first build)
**Phase 0 — Intake & scope.** Confirm the source directory (request folder access if needed; never assume the connected folder is the source). Inventory files with sizes/page-counts (`scripts/extract_text.py` prints these). Confirm with the user: vault location (default: a `… Vault/` subfolder in the project folder), depth (*comprehensive* vs *equipment-first* vs *overview*), and for drawing-heavy sets *index+schedules* vs *every sheet*. Inventory first, then ask with numbers in hand.

**Phase 1 — Extract text.** `scripts/extract_text.py <src> <out>` (PDF via pdftotext, XLSX, PPTX, CSV, .msg, and P6 .xer as a digest of project facts, milestones and the longest path). Keep extracted text in a scratch folder — it's working data, not part of the vault. Large PDFs: pdftotext, never pure-Python (timeouts). Large sets: run it per top-level folder (a single run times out around 1,300 PDFs); it is incremental, so re-runs skip what is done.

**Phase 2 — Parse structure & shared context.** Parse the drawing index and spec TOC into index notes + the discipline map. Write `PROJECT_FACTS.md` and `STYLE_GUIDE.md` to scratch (see `references/note-templates.md`). **Fixing exact hub names up front is the single most important step for link consistency.**

**Phase 3 — Skeleton & hubs.** Create the folder structure (`references/vault-structure.md`) and write hub notes yourself (don't delegate hubs — consistency). Hubs: Home, project overview/team/codes/phasing/site, one per discipline, one per system, key spaces, document indexes, **Glossary & Acronyms**.

**Phase 4 — Mine equipment (parallelize).** The bulk. If subagents are available, dispatch one per discipline group, each given the extracted-text paths, `PROJECT_FACTS.md`, `STYLE_GUIDE.md`, the target folder, and the **exact** hub-link names; have each return a compact manifest (files + one-liners + conflicts). Capture real tags, capacities, locations, interdependencies — not generic descriptions. **Give every subagent its own scratch/staging folder** (parallel agents sharing one folder have left duplicate `n1.md…n9.md` notes in a vault), and keep registers and the change log for yourself.

**Phase 5 — Registers.** Conflicts (`X-#`), Information Gaps (`G-#`), coordination clashes (`C-#`), and an owner-facing Scope Clarifications list with a recommended position each. Route every flagged item here.

**Phase 6 — Connect, verify, persist.**
1. Run the **hub-indexer** (`scripts/link_hubs.py`: preview, then `--write`) so every hub links its children.
2. Run the **audit** (`scripts/audit_vault.py`); drive unresolved links → 0 and orphans → 0.
3. Optionally seed graph colors from `assets/graph.json`.
4. **Write the project memory** (`CLAUDE.md` — below), including the **deliverable folder map** and the **uploaded-files rule**.
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

### Register IDs, sync-conflict copies, and never deleting
Cloud sync (OneDrive especially) forks a note when two devices or sessions edit it: `Name-<DEVICE>.md`, `Name-<DEVICE>-2.md`, and copies of copies. Registers fork most, because every session writes to them, and forked registers mint the **same ID twice with different meanings**. Rules:
- **Find the real high-water mark right before adding a row**: the highest ID across the register, **every conflict copy of it** (`scripts/audit_vault.py` lists them), and **the whole vault** (grep `X-\d+`, `G-\d+`, …), because IDs get cited in notes before they reach a register. The counter in the project `CLAUDE.md` is a hint, not the truth.
- **Write to the canonical file.** If it is cloud-only and won't hydrate, stage the entry in a dated `… — Pending Merge (YYYY-MM-DD).md` note in `06 - Documents`, never in a conflict copy.
- **On a collision** (one ID, two meanings), keep the earlier meaning, renumber the later item above the high-water mark, and note "renumbered from X-##" in both places.
- **Parallel writers use placeholders** (`P-W1-G1`); one orchestrator mints the real IDs and replaces them.
- **Never delete or merge conflict copies yourself.** List them for the owner in the wrap; merging is their call.
- **Never delete project or vault files at all: only add or modify.** Clean-ups (stray files, duplicates, scratch) are flagged in the change log and project memory for the owner, not removed.

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

Miss this and you get single-source tunnel vision — assigning a scope to the first sub you read, or approving a COR the base contract already covers.

**Contract questions are answered by quoting the contract.** For any question of scope, who owes what, entitlement, rates or notice, quote the governing clause **verbatim**, with document, exhibit and paragraph or page, **then** interpret. Quote both sides of an interface (owner contract and subcontract) where both apply. Don't paraphrase where the wording decides the answer.

Checks that have caught wrong determinations:
- **A claim's narrative is the claimant's assertion, not a fact.** Before pricing demolition, repair, restoration or tie-in to something described as existing or damaged, confirm it exists and was built when the claim says: check the schedule (has that activity happened yet? `xer_tool.py activity`) and the drawings. A delivery date is not a set date; the binding date is usually the pour or install.
- **"Existing" may be someone else's earlier work.** On a fit-out or phased job, the shell or earlier phase may have been built under a separate contract by a different contractor, whose RFIs, submittals and as-builts live in a different project record. Search that record before concluding a sub is reworking its own installation. Also check whether the drawings **deferred** a dimension or location to a later equipment submittal; an installation that predates that submittal is nobody's error.
- **Easy-to-miss sources that adjudicate scope:** bid-stage RFI responses, responsibility and scope-delineation matrices, scope sheets' "not included in base bid" alternates, and each trade's bid inclusions and exclusions in the precon archive.
- **Reused-template contamination.** Specs, drawings, product data or bid forms carried over from another site sometimes sit in a project's files. Never cite them for this project. Log each as a conflict and list it under a "Carry-over warning" in the project `CLAUDE.md`.

---
## Sibling projects (programs with several vaults)
When one team runs several similar projects (buildings on one campus, phases of a program), each gets its own vault, and a **program-level `CLAUDE.md` in the parent folder** lists them (project · vault path · entry note) with the routing rule:
- **Answer from the vault of the project asked about.** If it isn't stated, ask, or answer per project. **Never cite one project's facts for another.**
- **Register IDs and note names repeat across vaults**, so always say which vault a fact or ID comes from, and log edits in the vault you changed.
- **Use the leading project as an early warning.** If a sibling is further along with the same designers, standards or owner, check whether it already hit the issue (its registers and RFI archive) before answering a design, scope-boundary or equipment question on the trailing one. Cite it as precedent, not as this project's fact.
- Rules that apply to every project in the program (people, tools, review lenses, writing rules) live once in the program `CLAUDE.md`, not copied into each project.

---
## Connectivity standard (aim for this; audit against it)
The graph and backlinks *are* the value. A note nothing links to is a defect.
- **Hub → child completeness.** Every discipline hub indexes **100%** of its equipment; every system hub and every space lists its members (as back-links). Landing on any hub should reach everything in its domain in one hop.
- **Three-way reachability.** Every equipment note is reachable from its **discipline** hub, its **system** hub(s), and its **space**.
- **Process chains.** For linear spines (e.g. power: utility→MV switchgear→transformers→switchboards→bus duct/distribution boards→panelboards→white-space power→racks; cooling: chillers→pumps→valves→AHUs, and any liquid-cooling loop), give each spine note a short **"## Power chain" / "## Cooling chain"** line showing upstream→downstream with links, so the chain is traversable from any stop.
- **Bidirectional registers.** Any note named in a conflict/gap links the register back (a one-line "## Open items → [[Conflicts & Issues Register]] · [[Information Gaps & Open Questions]]").
- **No orphans.** 0 inbound links is allowed only for Home/templates/README.
- **Repair a broken link by adding an alias to the target note** when the link text is a legitimate name for it, rather than rewriting the link. Other sessions' link text keeps working, and it is the Obsidian-native fix.
- **System and space membership is declared, not inferred.** An equipment note lists its `systems:` and `spaces:` in frontmatter; mentioning a system in prose (a chiller note naming the switchboard that feeds it) does not make it a member.
- **People notes:** a person gets a note only when linked by name from another note (thread participant, approver, named sender). Firms, roles and the org chart stay in the project directory.
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
## P6 schedules (.xer) — `scripts/xer_tool.py`
Schedule questions are answered from the XER with the bundled tool, not by writing a one-off parser each session. It is **standard-library Python only** (nothing to install, runs in a locked-down sandbox), **read-only** (never modifies the XER), and reads P6's own scheduled dates and calendars, so results line up with what P6 shows. Validated against P6's own longest-path flags on 24 real project schedules (exact match on all).

| Question | Command |
|---|---|
| What's in this file / quick facts | `summary <xer>` (data date, forecast finish, counts, upcoming milestones); `projects <xer>` when it holds several |
| **What is driving the finish?** | `longest-path <xer> [--to CODE] [--near WD]` |
| **What changed since the last update / vs the baseline?** | `diff <old.xer> <new.xer> [--top N] [--to CODE]` |
| **New baseline / TIA / mitigation: did the milestone gaps hold?** | `gaps <old.xer> <new.xer> [more.xer or dates.csv ...] --labels "TIA 13,TIA 14" --keys NEA,H2C,PFHO` |
| Is the schedule technically sound? | `dcma <xer> [--baseline BL.xer] [--details N]` |
| Cost/hours performance | `earned-value <xer> [--baseline BL.xer]` |
| One activity's logic, float, drivers | `activity <xer> <code or name text>` |
| Lists & filters | `activities` (`--status --type --wbs --search --float-lt --longest-path`), `wbs [--depth]`, `relationships [--code]`, `calendars [--holidays YEAR]`, `resources` (incl. over-allocation), `assignments`, `float-paths` |
| Tables for a workbook | `export <xer> <dir> [--tables TASK,TASKPRED]`, or `--csv <dir>` on any command (then the **xlsx** skill) |

Every command takes `--proj`, `--json`, `--out report.md`, `--csv dir`. "wd" = working days on the activity's calendar.

**Rules that matter:**
- **Critical path = longest path, not "total float <= 0".** With finish constraints (common on mission-critical jobs) hundreds of activities carry negative float; the driving path is a few dozen. `longest-path` traces driving relationships back from the finish (or `--to` a milestone) using calendar-aware lag/gap math, honors retained logic and P6's SS-lag option, and explains where the path starts (data date, in-progress activity, constraint). Quote it, not a float filter.
- **Updates are compared, never eyeballed.** For a monthly update, TIA or delay claim, run `diff` against the prior update / baseline. Report finish and milestone movement, longest-path churn, progress achieved vs planned, and **actuals changed after the fact** (rewritten history is a forensic red flag).
- **Every new baseline, TIA or mitigation gets a gap check.** Run `gaps` with the previous version(s) first and the new one last (or `--focus`). Per phase/ROMP it reports each milestone's delta, the **stagger** between phases (ROMP n vs n-1, same milestone) and the **steps** inside a phase (NEA to H2C to PFHO), then lists the gaps that were squeezed versus the reference and flags any that went to zero or out of sequence (marked new or already so). Calendar days by default, `--workdays` for working days. Dates that exist only in a narrative table or a marked-up image go in as a `Group,Milestone,Date` CSV alongside the XERs. Phase comes from the name ("ROMP 3: ... (NEA)"), else the WBS node ("ROMP 03"), else the code; the milestone type is the abbreviation in brackets. Lead the write-up with the squeezed and flagged gaps, then hand `--csv` output to the **xlsx** skill if a workbook is wanted.
- **DCMA needs a baseline for #11 and #14.** Without `--baseline`, those two checks use the XER's planned dates and say so in the output; state which basis you used.
- **Log it.** Material schedule findings (finish movement, a new driver, a failed DCMA check, a rewritten actual) go to the vault per the Living-vault rules; reports go to `Schedule/` and get an index row with a synopsis (data date, finish, headline movement).

---
## Chat-upload intake (files dropped into the conversation)
A file the user drags into the chat is project knowledge the moment it arrives. Chat uploads land in a **temporary session folder** that is wiped later; unless the file is saved into the project and indexed, the next session (or the next person) will never know it existed. Treat every upload as an **Update: new file**, automatically and without asking:

1. **Detect.** Any new file in the session's uploads folder or attached to the message. Skip pure illustration (a UI screenshot, a clip of a sheet already in the set) unless it carries unique project information, and say so in the wrap.
2. **De-duplicate.** Hash the upload (md5/sha1) and compare against same-type files in the likely target folders. If an identical file is already saved, don't copy it; index the existing path.
3. **Route** it to the matching **project source folder**, never the vault and never the project root, using the folder map in the project `CLAUDE.md`. Typical AEC routing: subcontractor CORs/PCOs to `Subcontracts/<trade>/02 - COs/`; owner PCL packets to `Change Orders/PCL-###…/`; owner letters and notices to `Correspondence/…`; schedules to `Schedule/` (XERs to `Baseline XERs/`); submittals to `Submittals/<spec or vendor>/`; commissioning/QA files to `Cx/<subfolder>/`; drawings and specs to `Drawings & Specs/…`; org charts and rosters to `Team/`. If nothing fits, create a sensibly named subfolder and add it to the folder map.
4. **Name** it. Keep the original filename when it is descriptive. If it is cryptic (`DP PCO 79.pdf`, `notice[1].pdf`, `Book1.xlsx`), save it under a descriptive name in the folder's existing naming style and record the original name. Never overwrite an existing file; add a suffix such as `(uploaded copy)` or a date.
5. **Read** enough of it (extraction playbook: pdftotext / xlsx / docx / OCR; for an `.xer`, `xer_tool.py summary`, plus `diff` against the previous update in `Baseline XERs/`, and `gaps` against the prior version when it is a new baseline, TIA or mitigation) to write a synopsis.
6. **Index** it in `06 - Documents/Uploaded Files Index.md`, creating that note on first use and linking it from `Source Documents` and `00 - Home`. Each row records: upload date · saved name (plus original name if renamed) · saved path · **synopsis** (what it is, parties, headline figures and dates, status) · links to related notes. A substantial file (multi-tab workbook, long report) also gets a `<File> (contents).md` companion note, the same as generated deliverables.
7. **Back-link** it. Add a `Source file:` line (path plus `[[Uploaded Files Index]]`) to each related note (email thread, equipment note, register row), so the file can be reached from its topic.
8. **Log findings** per the Living-vault rules: facts go to notes, gaps and conflicts go to registers, synonyms go to aliases and the glossary. Add a dated `Vault Change Log` entry ("intake: N files").
9. **Report** in the 2 to 4 line wrap: what was saved where, the index row, and what was logged. If the message also asked a question, answer it first and do the intake after.

- **Sandbox notes.** The uploads folder is usually read-only. Copy with the shell (`cp -n`) into the mounted project folder. If the write fails (permissions or a locked cloud file), retry through the file tool, otherwise tell the user the exact path to save it to. Cloud-only targets follow the dehydration rule below. `scripts/intake_upload.py` does the hash-check and no-overwrite copy in one step (prints JSON with `saved` / `duplicate_of`); the agent still picks the folder and writes the index row.
- **Persist the rule.** Add an "Uploaded files" section to the project `CLAUDE.md` so the behavior survives even when this skill is not loaded.
- **Back-fill.** When this rule is first switched on mid-project, offer to back-fill earlier uploads from the current session.

---
## File organization (keep the project tidy)
Generated outputs must land in the **topic subfolder that fits**, never the project root (the root should hold only `CLAUDE.md` and the vault folder). This is a first-class rule, not a nicety — a root full of loose files is the same failure mode as a vault full of orphans.
- **Before saving any deliverable, consult the folder map** in the project `CLAUDE.md` (and the folder-map header of `06 - Documents/Generated Deliverables & Reports.md`). Save into the matching subfolder.
- **If nothing fits, create a new, sensibly-named subfolder** (topic- or discipline-based, matching the project's existing naming style) rather than dropping the file in root — then add it to the folder map.
- **Keep the folder map current.** When you add an output or the user reorganizes files, refresh the paths + folder map in both the deliverables index note and the project `CLAUDE.md`, and add a dated change-log line.
- A typical construction/AEC map (adapt names to the project): `Financial/` (cost/COR/exposure/change logs) · `Schedule/` (P6 exports, baseline-shift, `Baseline XERs/`) · a commissioning/QA hub such as `Cx/` with per-activity subfolders (`Cx Inspections/`, `Cx Schedule/`, `Cx Observations/`, `Cx-Flores/`, `Energization/`, …) · `OFCI/` (owner-furnished trackers) · `Markups/` (one-lines, marked drawings) · `Team/` (org/roster). Non-AEC projects use their own equivalents (e.g. `Reports/`, `Data/`, `Exports/`, `Diagrams/`).
- **Tool-building scratch** (build scripts, session JSONs, patch files, deploy folders) goes in its own `_build/`-style subfolder or outside the project, not loose in a topic folder. Flag strays in the change log; don't delete them.

**Confidential material.** Some files in a shared project folder are restricted: payroll and HR records, internal-only cost reports and SOVs, owner-confidential documents. Index them by name, purpose and date only; never copy their contents, personal details or rates into notes. If you find **secrets** (tokens, keys, passwords) or project data **published to a public URL** without a login, log it as a gap for the owner straight away and never copy the secret into the vault.

---
## Project memory & transferability
At the end of a build, and whenever conventions change, write/refresh a **`CLAUDE.md` at the *project root*** (the shared folder that holds both the vault and the source docs — not just inside the vault). This is what lets a future session or a new teammate extend rather than rebuild. Keep paths **relative** to the shared root so it stays valid for anyone who syncs the folder.

**Keep it short: it is loaded into every session.** It holds rules, pointers and the current state, not history.
- The register line is **one line of next safe IDs, overwritten each time** (`Next safe IDs (YYYY-MM-DD): X-## / G-## / SC-## / C-##`). Never append "Earlier: …" lines.
- File-scan and email-sync results, counts and per-pass notes go in the **`Vault Change Log`**, not here.
- Aim for under ~10 KB. A memory file that grows into tens of KB of run-on history costs every session tokens, buries the rules, and is more likely to be overwritten in a sync race.
- When it has grown, move the history into the change log (keep the text; don't delete it), and leave the rules and current state.

Template:

```markdown
# <Project> — Project Memory
Working context for future sessions. This folder is the shared project root; paths below are relative to it.

## Knowledge vault
- Location: `<Project> Vault/` (Obsidian). Start at `00 - Home.md`.
- Living-vault workflow: answer first, then log findings/gaps/conflicts (+ aliases/glossary), then a dated `Vault Change Log` entry.
- Next safe IDs (YYYY-MM-DD): **X-## / G-## / SC-## / C-##**. One line, overwritten; check every conflict copy and the whole vault before minting.
- Keep the exact hub names + templates so `[[wikilinks]]` stay consistent; run `scripts/audit_vault.py` after edits.
- Never delete project or vault files; only add or modify. Conflict copies are merged by the owner.
- Fast relevance search: `scripts/vault_search.py "<Project> Vault" "<question>"` (model-free BM25, runs anywhere).

## Source documents (same shared folder)
- Drawings/specs: `…/`  · Change orders/financials: `…/` · Schedule/baselines: `…/` · Submittals/subcontracts: `…/`
- Chat uploads: any file dropped into the chat is saved into the matching folder above (never the vault/root) and indexed with a synopsis in `06 - Documents/Uploaded Files Index.md`.
- Generated deliverables are filed into **topic subfolders** (below), never the project root; `06 - Documents/Generated Deliverables & Reports.md` indexes every output — path **plus a synopsis of its contents** (structure + headline figures as-of a date), with a companion `<Deliverable> (contents).md` note for substantial workbooks/dashboards.

## Deliverable folders (keep the root clean)
Save each output into the matching topic subfolder; the root holds only `CLAUDE.md`. Map (adapt names to the project):
- `Financial/` — cost/COR/change-order/exposure workbooks + owner change logs.
- `Schedule/` — P6 exports, baseline-shift reports, `Baseline XERs/`.
- `Cx/` (or the project's commissioning/QA hub) — with subfolders per activity (e.g. `Cx Inspections/`, `Cx Schedule/`, `Cx Observations/`, `Cx-Flores/`, `Energization/`).
- `OFCI/` (owner-furnished trackers) · `Markups/` (one-lines, marked drawings) · `Team/` (org/roster).
- If a new output fits none of these, **create a sensibly-named subfolder** rather than dropping it in root.

## Carry-over warning
Files in this set that carry another site's content and must never be cited here: `…` (conflict ID).

## Team rules
Standing instructions from the team, each with who and when (e.g. "contract questions: quote the clause verbatim (<name>, <date>)").

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
- **Bulk hydration:** running the host's Grep/search tool over a dehydrated folder usually forces the whole folder to download, after which shell tools work. It can still fail on some files (OS error 362); fall back to the Read tool, or ask the user to mark the folder "Always keep on this device."
- **Detect new and changed files by comparing file lists, never by modified time.** Cloud sync preserves original timestamps, so a "newer than" scan misses files that arrived today. Keep a manifest (`06 - Documents/.file-manifest.json`: relative path, size, whole-second mtime) and diff each scan against it. Walk large trees one top-level folder at a time (deeper for very large folders) so each walk finishes inside the sandbox timeout. Office lock files (`~$…`) are not documents.

---
## Audit, link check and hub indexing (scripts)
All three are standard-library Python, tolerate cloud-only files (skip and report them), and read aliases in both YAML forms (inline `aliases: [a, b]` and block lists), case-insensitively like Obsidian.
- **Audit** (read-only): `python scripts/audit_vault.py "<vault>"`. Reports unresolved links (per note), orphans, the in-degree spread, discipline-hub completeness, and **sync-conflict copies** of notes (with the original each one copies). Run it after every batch of edits; drive unresolved and orphans to 0. Conflict copies are listed for the owner, never deleted.
- **Link check** (read-only, exits non-zero on broken links, so it can gate a build): `python scripts/verify_links.py "<vault>"`.
- **Hub indexer**: `python scripts/link_hubs.py "<vault>"` **previews** the links it would add; add `--write` to apply. Discipline hubs list equipment by its frontmatter `discipline:`; system hubs and spaces list equipment by its frontmatter `systems:` / `spaces:` (scalar, list or wikilinks). It never infers membership from links, and it skips conflict copies. `--from-links` restores the old link-based rule for vaults without those fields; review its preview first, because a note that mentions a system is not necessarily part of it.
- After `--write`, re-run the audit and confirm 0 unresolved / 0 orphans.

---
## Reference files (read as needed — progressive disclosure)
- `references/vault-structure.md` — folder layout, naming, frontmatter, graph groups.
- `references/note-templates.md` — equipment/hub/system/register templates; `PROJECT_FACTS.md` / `STYLE_GUIDE.md` contents.
- `references/extraction-playbook.md` — per-file-type extraction (large PDFs, image-only decks/OCR, cloud-synced files).
- `references/update-workflow.md` — living-vault sync rules + new-files recipe.

## Scripts
- `scripts/extract_text.py` — batch extraction + inventory. `python extract_text.py <src> <out>`.
- `scripts/audit_vault.py` — vault health audit: unresolved links, orphans, hub completeness, sync-conflict copies. Read-only.
- `scripts/verify_links.py` — link check; exits non-zero on broken links. Read-only.
- `scripts/link_hubs.py` — hub indexer from frontmatter `discipline:` / `systems:` / `spaces:`; previews by default, `--write` to apply.
- `scripts/vault_search.py` — model-free BM25 relevance search over the vault notes (alias/tag-boosted, cited, runs anywhere; no model/deps). `python vault_search.py "<vault>" "<question>" [-k N] [--path P] [--tag T] [--json]`; optional `build "<vault>"` writes a tiny `.vaultidx.json` cache.
- `scripts/xer_tool.py` — Primavera P6 .xer analysis: summary, activities/WBS/relationships/calendars/resources, **longest (driving) path**, **update/baseline diff**, **milestone gap check** (`gaps`), **DCMA 14-point**, earned value, float paths, CSV export. `python xer_tool.py <command> <file.xer> [...]` (`-h` for all options). Stdlib only, read-only.
- `scripts/intake_upload.py` — chat-upload intake helper: sha1 de-dup against the target folder, then a no-overwrite copy. `python intake_upload.py <upload_file> <project_root> <target_subfolder> [--name "Descriptive Name.ext"]` → JSON `{"saved", "duplicate_of", "sha1"}`. Stdlib only.

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
- **Uploads are knowledge, not attachments.** Every file dropped into the chat is saved to its project folder and indexed with a synopsis, because the uploads folder is temporary.
- **One install, whole workflow:** the vault skill embeds the Obsidian open-format skills (markdown/bases/canvas/cli/defuddle/knap) and the plugin also installs them as siblings — a new user installs one thing and has everything; prefer a live Base over a static table for anything that must stay current.
- **Determinations are multi-source.** Scope / COR / ownership / code calls sweep the owner contract + subcontracts (inclusions *and* "by others" exclusions, every plausibly-responsible trade) + drawings/specs + submittals + change docs + code — reconciled and cited. Never decide from one document.
- **Organize outputs, don't dump them.** Every generated file lands in the topic subfolder that fits (create one if needed); the project root stays clean; the deliverables index + folder map stay current.
- **The vault knows its outputs' contents.** Index every generated report/workbook/dashboard with a synopsis of what's inside (structure + headline figures as-of a date), not just its path — so questions get answered from the vault without reopening the file.
- **Schedules are read with the tool, and the critical path is the longest path.** Use `xer_tool.py` for every .xer question; compare updates with `diff`; never call "total float <= 0" the critical path.
- **Source-traceable:** every note cites where its facts came from.
- **Small, linked notes beat big documents:** one idea per note, connected by `[[wikilinks]]`.
- **Connectivity is a feature:** hubs index children; no orphans; run the hub-indexer + audit after edits.
- **Meaning lives in the notes, not a model:** encode synonyms/acronyms as `aliases`/`tags` + a glossary; search is a model-free BM25 over the notes (`vault_search.py`) — nothing to install, sync, or let go stale.
- **Log as you go, don't ask to log:** capture material findings the same turn, automatically; only ask the user about genuine decisions or destructive actions.
- **Track problems, don't bury them:** conflicts and gaps get registers.
- **Add and modify, never delete.** Duplicates, sync-conflict copies and stray files are flagged for the owner, not removed. Mint IDs from the highest across every copy and the whole vault.
- **Project memory is short and current.** `CLAUDE.md` holds rules, pointers and the next safe IDs; history lives in the Vault Change Log.
- **Persist for the next person:** a project-memory `CLAUDE.md` + a glossary make the skill transferable.
- **A read error on cloud storage is dehydration, not corruption:** hydrate, don't conclude "corrupt."
- **DD/draft caveat:** if documents are design/draft stage, say so in notes — values change.
