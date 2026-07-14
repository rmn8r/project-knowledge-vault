# project-knowledge-vault

A reusable **Claude skill** that turns a folder of project documents (drawings, specifications,
narratives, reports, schedules, spreadsheets, emails, decks) into a linked **Obsidian knowledge-base
vault** — a queryable "second brain" for the project where every answer is traceable to a source
document. Built for construction/AEC projects but domain-agnostic.

## What it does
- **Build:** point it at a project files directory → extracts text from every file, parses drawing
  indexes and CSI spec tables of contents, and builds an interlinked vault (disciplines, systems,
  equipment, spaces, document indexes, and registers for conflicts / gaps / owner scope clarifications).
- **Ask:** answer project questions from the vault, with sources cited.
- **Update:** when new files/folders are added, integrate just the new material and keep the vault in sync.
- **Verify:** every `[[wikilink]]` is checked to resolve.

## Install
- **Claude (Cowork / claude.ai):** download `project-knowledge-vault.skill` and use **Save skill**
  (Settings → Capabilities), or drop the `project-knowledge-vault/` folder into your skills directory.
- Triggers automatically when you ask to build/update a project knowledge base, or explicitly via
  `/project-knowledge-vault`.

## Repository layout
```
project-knowledge-vault/          # the skill (installable unit)
  SKILL.md                        # workflow + invocation modes
  references/                     # vault-structure, note-templates, extraction-playbook, update-workflow
  scripts/                        # extract_text.py, verify_links.py
  assets/                         # graph.json (Obsidian graph color groups)
project-knowledge-vault.skill     # packaged, installable archive
```

## Scripts
- `scripts/extract_text.py <src_dir> <out_dir>` — batch text extraction + inventory (PDF/XLSX/PPTX/CSV/MSG).
- `scripts/verify_links.py <vault_dir>` — checks all Obsidian wikilinks resolve.

## License
MIT — see `LICENSE`.
