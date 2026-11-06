# Release notes - project-knowledge-vault 1.4.0

**Released:** 2026-11-06. This is a maintenance release: the vault audit tools now report
accurately, and lessons from running the skill on real projects are now part of the skill
itself.

## Highlights

### The audit tools now tell the truth
| | Before | Now |
|---|---|---|
| Unresolved-link count | Summed file-name lengths (4,348 on a vault with 75 real breaks) | Counts broken links per note |
| Aliases written as a block list | Ignored, so links to them showed as broken | Read in both YAML forms |
| Link matching | Case-sensitive | Case-insensitive, like Obsidian |
| `verify_links.py` on Windows | Crashed when every link resolved | Fixed |
| Hub indexer | Filed equipment under any system it linked to | Files by `systems:` / `spaces:` frontmatter; previews before writing |
| Sync-conflict copies (`Note-DEVICE-2.md`) | Counted as orphans and indexed as equipment | Listed separately, with the original each one copies; skipped by the indexer |

Run `python scripts/audit_vault.py "<vault>"` for the health check. `python scripts/link_hubs.py "<vault>"`
now only previews; add `--write` to apply.

### New rules in the skill
- **Register IDs:** before adding a row, take the highest ID across the register, its sync-conflict
  copies and the whole vault. Collisions are renumbered, and parallel writers use placeholders.
- **Add and modify, never delete.** Conflict copies and stray files are flagged for the owner.
- **Contract questions:** quote the governing clause verbatim, with document, exhibit and paragraph,
  then interpret.
- **Checks before a determination:**
  - test a claim's physical premise against the schedule and drawings;
  - "existing" may be another contractor's earlier work;
  - drawings may defer a dimension to a later submittal;
  - watch for content carried over from another site.
- **Sibling projects:** route by project, never cite one project's facts for another, and check
  the project that is further along.
- **Cloud sync:**
  - bulk hydration, with a fallback;
  - detect new files by comparing file lists, never by modified date;
  - walk large trees one folder at a time.
- **Confidential material:** index restricted files by name only, and flag secrets and public URLs.
- **Keep the project `CLAUDE.md` short.** It holds one overwritten line of next safe IDs; history
  goes in the Vault Change Log.

## Upgrading
- **Claude Code (plugin):** `/plugin marketplace update project-knowledge-vault`, then update the
  plugin.
- **Cowork / claude.ai:** Settings → Capabilities → Skills, then replace `project-knowledge-vault`
  with the `.skill` file from this release. Start a new session.
- **Existing vaults:**
  - Nothing to migrate.
  - To let the hub indexer place equipment on system and space hubs, add `systems:` / `spaces:` to
    equipment frontmatter.
  - Hubs you curated by hand are left alone.
  - Re-run the audit: its numbers will drop sharply, because the old ones were inflated.

See [CHANGELOG.md](CHANGELOG.md) for the full history.
