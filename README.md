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
**As a plugin (recommended — installs all seven skills):**
```
/plugin marketplace add rmn8r/project-knowledge-vault
/plugin install project-knowledge-vault@project-knowledge-vault
```
That brings `project-knowledge-vault` plus the six bundled Obsidian open-format skills
(`obsidian-markdown`, `obsidian-bases`, `json-canvas`, `obsidian-cli`, `defuddle`, `knap`) as
first-class siblings, reference files included.

**As a single skill:**
- **Claude (Cowork / claude.ai):** download `project-knowledge-vault.skill` and use **Save skill**
  (Settings → Capabilities), or drop the `skills/project-knowledge-vault/` folder into your skills
  directory. The six companions are embedded inside it under `references/obsidian-skills/`, so the
  standalone skill carries the full Obsidian know-how too.
- Triggers automatically when you ask to build/update a project knowledge base, or explicitly via
  `/project-knowledge-vault`.
- Build/ask/update/verify all work as soon as the skill is saved — no extra setup, no dependencies.

### Relevance search over the notes
`scripts/vault_search.py` ranks the vault's own Markdown with **BM25** (classic
term-vector IR) — useful when you want "which notes bear on this question?" rather than
a link you already know.

```bat
python skills\project-knowledge-vault\scripts\vault_search.py "C:\path\to\Your Project Vault" "who owns the annunciator wiring"
```

**No model, no GPU, no dependencies, no index to maintain.** It is Python stdlib only, so
it runs anywhere the skill does — including a locked-down agent sandbox — and it is always
current because it reads the notes live at query time. Optionally
`vault_search.py build "<Vault>"` caches a ~2 MB `.vaultidx.json`; queries fall back to
live reading whenever that cache is older than a note.

Relevance comes from the notes themselves: frontmatter `aliases:` and `tags:` are boosted,
so recording that MEDS means USB, or that a camboard is a camlock, makes a plain keyword
query behave semantically. Enrich the notes and search gets smarter — the meaning lives in
the vault, not in a model.

## Repository layout
```
.claude-plugin/                     # marketplace.json + plugin.json (ships all 7 skills)
skills/
  project-knowledge-vault/          # the vault skill (installable on its own)
    SKILL.md                        # workflow + invocation modes
    references/                     # vault-structure, note-templates, extraction-playbook, update-workflow
      obsidian-skills/              # the six kepano skills, embedded so this skill is self-contained
    scripts/                        # extract_text.py, verify_links.py, audit_vault.py, link_hubs.py,
                                    # vault_search.py (model-free BM25 search)
    assets/                         # graph.json (Obsidian graph color groups)
  obsidian-markdown/  obsidian-bases/  json-canvas/     # vendored from kepano/obsidian-skills (MIT),
  obsidian-cli/       defuddle/        knap/            # installed as first-class sibling skills
project-knowledge-vault.skill       # packaged, installable archive (vault skill + embedded companions)
THIRD_PARTY/kepano-obsidian-skills/LICENSE
ATTRIBUTION.md
```

## Scripts
- `scripts/extract_text.py <src_dir> <out_dir>` — batch text extraction + inventory (PDF/XLSX/PPTX/CSV/MSG).
- `scripts/verify_links.py <vault_dir>` — checks all Obsidian wikilinks resolve.
- `scripts/audit_vault.py <vault_dir>` — vault health/coverage audit.
- `scripts/link_hubs.py <vault_dir>` — regenerates hub-note indexes.
- `scripts/vault_search.py <vault_dir> "<question>"` — model-free BM25 relevance search over
  the notes; see **Relevance search over the notes** above.

## Credits / third-party skills
`obsidian-markdown`, `obsidian-bases`, `json-canvas`, `obsidian-cli`, `defuddle`, and `knap` are
vendored from [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) (MIT, © 2026
Steph Ango) at a pinned commit. They ship both as sibling skills and embedded inside
`project-knowledge-vault`. Full details — pinned SHA, both placements, and the upstream license —
in [`ATTRIBUTION.md`](ATTRIBUTION.md) and
[`THIRD_PARTY/kepano-obsidian-skills/LICENSE`](THIRD_PARTY/kepano-obsidian-skills/LICENSE).

## License
MIT — see `LICENSE`. Vendored third-party skills remain under their own MIT license; see
`ATTRIBUTION.md`.
