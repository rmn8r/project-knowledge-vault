---
name: project-knowledge-vault
description: >-
  Turn a folder of project documents (drawings, specifications, narratives, reports, schedules,
  spreadsheets, emails, decks) into a linked Obsidian knowledge-base vault that serves as a roadmap
  for answering project questions. Use this whenever the user wants to "set up a new project," "build
  a knowledge base / Obsidian vault from a document set," "review all the files and organize them,"
  "index a construction/engineering project," "create a knowledge repository," or points Claude at a
  project directory and asks to understand and cross-link everything. Also use to KEEP such a vault in
  sync as new questions are asked or new files are added. Strongly prefer this skill for any request
  that involves ingesting a document set and producing an interlinked, queryable vault — even if the
  user doesn't say the word "Obsidian." Construction/AEC projects are the primary use case, but the
  workflow is domain-agnostic.
---

# Project Knowledge Vault

Build (and then maintain) an **Obsidian vault** from a folder of project documents. The vault is a
network of small, interlinked Markdown notes — a "second brain" for the project — so that any question
("what's the floor flatness spec?", "how are the capacitors charged?", "what's owner-furnished?") can be
answered quickly, with every answer traceable to a source document.

The output is intentionally a **plain folder of `.md` files with `[[wikilinks]]`** — it opens in
[Obsidian](https://obsidian.md) but is just Markdown, so it works in any editor and needs no lock-in.

## What "good" looks like
- One hub note per **discipline** and per **system**; one note per **equipment/asset**; register notes
  for **conflicts**, **information gaps**, and **owner scope clarifications**; document-index notes
  (drawing index, spec index); a **Home** map-of-content; and a **change log**.
- Every note has YAML frontmatter and cites its **source** (sheet / spec section / report page).
- Everything is cross-linked with `[[wikilinks]]`; **all links resolve** (verified).
- Anything ambiguous or contradictory is captured in a register, not silently dropped.

---

## Invocation & modes
This skill is invoked two ways: **automatically** when a request matches the description, or
**explicitly** when the user types `/project-knowledge-vault`. No separate slash-command needs to be
created — a slash command *is* a skill. One skill covers the whole lifecycle; pick the mode from what
the user is asking:

| Mode | Trigger phrases | What to do |
|---|---|---|
| **Build** (first time) | "set up a new project," "build a vault from this folder," "review & organize these files" | Run Phases 0→6. |
| **Ask** (query the vault) | any project question once a vault exists ("what's the X spec?", "is Y owner-furnished?") | Answer from the vault/sources; then apply the Maintenance capture rules. |
| **Update — new files** | "I added new docs/a folder, update the vault," "integrate these new files" | Run the **Maintenance → Integrating newly added files** recipe (extract just the new files, create/enrich notes, update registers + `Source Documents` + `Home`, re-verify links). |
| **Sync — findings** | corrections, decisions, or gaps surfacing mid-conversation | Apply Maintenance capture rules (finding/gap/conflict → note/register + change log). |

If the user prefers a recurring automatic refresh (e.g., "check the project folder weekly and update the
vault"), offer to set up a **scheduled task** that runs the Update mode on a cadence — but event-driven
("I just added files") is usually handled by simply asking. Modes are selected by phrasing, not by
separate commands, so the vault has one memorable entry point.

---

## Workflow

Work through these phases. For a first build, do 0→6. To integrate new files later or answer a
question, jump to **Maintenance** at the bottom.

### Phase 0 — Intake & scope (do this before any heavy work)
1. **Get the source directory.** If the user hasn't pointed at one, ask for the path. If it isn't
   accessible, request access (in Cowork: `request_cowork_directory`). Never assume the connected
   project folder equals the source folder — confirm.
2. **Inventory** the folder: list files with sizes and, for PDFs, page counts (`scripts/extract_text.py`
   prints this). This tells you the scale and shapes the plan.
3. **Confirm output location & scope with the user** (use a multiple-choice question if available):
   - Where the vault goes (default: a `... Vault` subfolder in the user's working/project folder).
   - Depth: *comprehensive* (every section/tag) vs *equipment-first* (deep on equipment, narrative
     elsewhere) vs *overview roadmap*. Recommend equipment-first for very large sets.
   - For drawing-heavy sets: *index + schedule/equipment sheets* vs *every sheet*.
   Don't gate the first inventory on this — inventory first, then ask with concrete numbers in hand.

### Phase 1 — Extract text from every file
Run `scripts/extract_text.py <source_dir> <out_dir>` (see `references/extraction-playbook.md`). It
handles PDF (pdftotext, fast), XLSX, PPTX (slide XML; flags image-only decks), CSV, and .msg emails,
and writes one `.txt` per source plus an `INVENTORY.md`. Large PDFs must be extracted with `pdftotext`,
not pure-Python, or you'll time out. Keep extracted text in a scratch folder — it is *working data*, not
part of the vault.

### Phase 2 — Parse structure & build shared context
- Parse the **index/table-of-contents** artifacts: e.g., a drawing index (sheet number → title →
  discipline) and a specification TOC (CSI division → section). These become index notes and the
  discipline map.
- Write two **shared reference files** into the scratch folder for consistency (and for subagents):
  `PROJECT_FACTS.md` (key mined facts) and `STYLE_GUIDE.md` (note template + exact hub names + linking
  rules). See `references/note-templates.md` for what these contain. **Fixing exact hub-note names up
  front is the single most important step for link consistency.**

### Phase 3 — Build the vault skeleton & hub notes
Create the folder structure and write the hub notes yourself (do NOT delegate hubs — consistency
matters). See `references/vault-structure.md` for the canonical layout and `references/note-templates.md`
for templates. Hubs: Home/MOC, project overview/team/codes/phasing/site, one note per discipline, one
per system, key spaces, document indexes.

### Phase 4 — Mine equipment/assets into notes (parallelize)
This is the bulk of the work. If subagents are available, **dispatch one per discipline group in
parallel**, each given: the extracted-text paths, `PROJECT_FACTS.md`, `STYLE_GUIDE.md`, the target
`04 - Equipment` folder, and instructions to write one note per tagged item using the template and the
**exact** hub-link names. Have each agent return only a compact manifest (filenames + one-liners +
conflicts found) to keep context small. If no subagents, mine discipline-by-discipline yourself.
Capture **real tags, capacities, locations, and interdependencies** — not generic descriptions.

### Phase 5 — Registers (track problems separately)
Create/curate: **Conflicts & Issues Register** (contradictions, coordination clashes), **Information
Gaps & Open Questions** (missing info, with the note where the answer belongs + likely source), and —
for construction — an owner-facing **Scope Clarifications** list with a recommended position per item.
Route every flagged item from Phase 4 here.

### Phase 6 — Verify & finish
- Run `scripts/verify_links.py <vault_dir>` and fix every unresolved `[[wikilink]]` (create the note,
  add a frontmatter `aliases:` entry, or fix the name). Aim for zero unresolved links.
- Optionally seed graph-view color groups from `assets/graph.json` (see `references/vault-structure.md`).
- Tell the user how to open it: install Obsidian if needed, *Open folder as vault*, start at `00 - Home`.
- Save a short project memory (vault location + conventions) so future sessions extend rather than rebuild.

---

## Maintenance (the update process)
The vault is meant to **stay alive** as the project chat continues. Read `references/update-workflow.md`
for the full rules. In brief:
- **Answer the user's question first**, then update the vault, then report what changed.
- Capture **material findings, gaps, and conflicts** — not routine lookups that just restate a note.
- New fact → write it into the right note + cite source; flip any matching gap to resolved.
  Missing info → add a gap row. Contradiction → add to the conflicts register.
- Log every session's edits (newest first) in a **`Vault Change Log`** at the vault root.
- When the user **adds new files/folders**, run Phases 1–2 on just those, then int