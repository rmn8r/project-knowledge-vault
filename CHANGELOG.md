# Changelog

All notable changes to the project-knowledge-vault plugin and skill. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). The version is the one in
`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.

## [1.3.0] - 2026-11-06

### Added
- **`scripts/xer_tool.py`**, a Primavera P6 `.xer` analyser. It uses only the Python standard
  library, so there's nothing to install, and it never modifies the XER. Commands:
  - **`longest-path`** traces the real driving path backwards through P6's own dates and
    calendars. It is not "total float <= 0". It handles calendar-aware lag, retained logic,
    P6's SS-lag option, level-of-effort activities and ALAP constraints, and explains where
    the path starts. It matched P6's own longest-path flags on all 24 real schedules tested.
  - **`diff <old> <new>`** compares an update against the previous update or the baseline:
    - movement of the finish and of each milestone;
    - longest-path changes;
    - progress against what was planned for the period;
    - actual dates changed after the fact;
    - duration, constraint, calendar, logic and name changes;
    - added and deleted activities.
  - **`gaps <v1> <v2> ...`** checks milestone gaps across baselines, TIAs and mitigations:
    - each milestone's movement;
    - the stagger between consecutive phases;
    - the steps inside a phase (for example NEA → H2C → PFHO);
    - squeezed gaps, plus flags for zero and out-of-sequence gaps, marked new or already
      present in the reference.

    It takes XERs or `Group,Milestone,Date` CSVs. It finds the phase in the activity name,
    then the WBS, then the code. Gaps are in calendar days by default; `--workdays` switches to
    working days.
  - **`dcma`** runs all 14 DCMA checks. Missed tasks and BEI use a baseline XER when one is
    given.
  - **`earned-value`** uses a baseline XER when given, for both cost and units.
  - **`float-paths`**, **`summary`**, **`activities`**, **`activity`**, **`wbs`**,
    **`relationships`**, **`calendars`** and **`resources`** (including over-allocation),
    **`assignments`**, **`projects`** and **`export`**.
  - Every command takes `--json`, `--out report.md` and `--csv dir`.
- SKILL.md has a new "P6 schedules" section: a command table and the rules for using it.
  - The critical path is the longest path.
  - Compare updates with `diff`.
  - Run `gaps` on every new baseline, TIA or mitigation.
  - DCMA checks #11 and #14 need a baseline.
  - Log what you find.
- The skill's mode table has a new "Schedule (P6 .xer)" row.

### Changed
- `extract_text.py` now writes a digest of each `.xer` (project facts, milestones and the
  longest path) during vault builds and updates.
- The intake step runs `summary` and `diff` on a dropped-in `.xer`, plus `gaps` when it is a new
  baseline, TIA or mitigation.
- The skill description now mentions `.xer` analysis so the skill is picked up for schedule
  questions. It is still under the 1024-character limit.
- README and `references/extraction-playbook.md` document the new script.

### Notes
- Version 1.2.0 was an intermediate bump on the same branch and was never released on its own.
  Its contents are part of 1.3.0.

## [1.1.0] - 2026-10-19

### Added
- **Intake mode.** Any file dragged into the chat is de-duplicated by hash and saved into the
  matching project source folder, never the vault. It is renamed when the original name is
  cryptic, with the original name kept on record. It is indexed in
  `06 - Documents/Uploaded Files Index.md` with a synopsis, back-linked from related notes, and
  mined for findings.
- `scripts/intake_upload.py`, a stdlib-only helper that de-duplicates with sha1 and copies
  without overwriting.
- An Uploaded Files Index template in `references/note-templates.md`, and a "Files dropped into
  the chat" pointer in `references/update-workflow.md`.

## [1.0.0] - 2026-09-18

### Added
- Packaged as a Claude Code plugin with a marketplace (`.claude-plugin/`). It ships the vault
  skill plus the seven vendored kepano obsidian-skills (MIT) as first-class sibling skills. The
  same skills are also embedded inside the vault skill.
- A light prompt to install the full plugin when a companion skill is missing.
- Auto-log is now enforced. Determinations that need several sources (COR, scope, code) must
  be cross-checked across all of them.

## Before 1.0 (unversioned, 2026-07-14 to 2026-09-17)

- The first skill: build, ask and update modes that turn a project document folder into a
  linked Obsidian vault.
- Generated deliverables are filed in topic subfolders and indexed with a synopsis of their
  contents.
- An optional local hybrid RAG layer was added and hardened, then replaced with a model-free
  in-vault BM25 search (`vault_search.py`). The hardening covered OCR of drawings, incremental
  extraction, Windows MAX_PATH handling and skipping Office lock files.
- `extract_text.py` became incremental, and its `--record` option was removed.

[1.3.0]: https://github.com/rmn8r/project-knowledge-vault/releases/tag/v1.3.0
[1.1.0]: https://github.com/rmn8r/project-knowledge-vault/releases/tag/v1.1.0
[1.0.0]: https://github.com/rmn8r/project-knowledge-vault/releases/tag/v1.0.0
