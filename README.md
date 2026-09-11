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
- Build/ask/update/verify all work as soon as the skill is saved — no extra setup, no dependencies.

### Optional: enable semantic search (RAG)
Keyword search (exact `[[wikilinks]]` + tags/IDs) works everywhere out of the box. Adding
**semantic recall** — so you can ask "who owns the wire to the annunciator" instead of knowing it's
tagged `26 32 13 §K` — needs a one-time step that **Cowork's sandbox can't do for you**: it has no
network access to PyPI or the Hugging Face model hub, so it can't install the embedding model itself.
Do this once from a real command prompt on your own computer (not inside the Claude/Cowork chat):

1. Get this repo onto that machine (`git clone https://github.com/rmn8r/project-knowledge-vault.git`,
   or download the ZIP from GitHub's **Code → Download ZIP**).
2. Open **Command Prompt** (Windows) or **Terminal** (Mac/Linux) in that folder and run:
   ```bat
   cd project-knowledge-vault
   pip install -r project-knowledge-vault\scripts\requirements-rag.txt
   python project-knowledge-vault\scripts\rag_index.py "C:\path\to\Your Project Vault"
   ```
   (Mac/Linux: same commands, forward slashes.) This downloads the local embedding model once
   (cached for reuse) and writes a `.rag/` index folder inside your vault. Nothing is uploaded —
   the model runs, and stays, entirely on your machine.
3. Nothing else to run or keep alive. If your vault lives in a synced folder (OneDrive, Google
   Drive, etc.), the `.rag/` folder syncs with it like any other vault file.
4. Back in Cowork (or Claude Code, or any other environment), just ask your question — retrieval
   picks up the index automatically. If that environment also has the same Python packages
   installed, you get full hybrid (keyword + semantic) results; if not, it falls back to
   keyword-only automatically — same index, nothing crashes.
5. After adding a batch of new project documents, re-run step 2 to refresh the index — it's
   incremental, so only new/changed notes get re-embedded.

See `references/rag-retrieval.md` for the full design (why hybrid, what stays local, index layout).

## Repository layout
```
project-knowledge-vault/          # the skill (installable unit)
  SKILL.md                        # workflow + invocation modes
  references/                     # vault-structure, note-templates, extraction-playbook, update-workflow,
                                   # rag-retrieval (optional semantic search)
  scripts/                        # extract_text.py, verify_links.py, rag_index.py, rag_query.py,
                                   # requirements-rag.txt (optional semantic-search deps)
  assets/                         # graph.json (Obsidian graph color groups)
project-knowledge-vault.skill     # packaged, installable archive
```

## Scripts
- `scripts/extract_text.py <src_dir> <out_dir>` — batch text extraction + inventory (PDF/XLSX/PPTX/CSV/MSG).
- `scripts/verify_links.py <vault_dir>` — checks all Obsidian wikilinks resolve.
- `scripts/rag_index.py <vault_dir>` — builds/refreshes the optional local hybrid (keyword + semantic)
  retrieval index; see **Optional: enable semantic search** above.
- `scripts/rag_query.py <vault_dir> "<question>"` — queries that index.

## License
MIT — see `LICENSE`.
