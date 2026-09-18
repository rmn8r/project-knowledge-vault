# Attribution — third-party skills

## kepano/obsidian-skills (MIT)

- **Source:** https://github.com/kepano/obsidian-skills
- **Pinned commit:** `3ccff5338ea700537839b21900aa5358a0402c98`
- **Author:** Steph Ango (@kepano) — https://stephango.com/
- **License:** MIT — full text at [`THIRD_PARTY/kepano-obsidian-skills/LICENSE`](THIRD_PARTY/kepano-obsidian-skills/LICENSE)

Six skills are vendored from that repository, unmodified apart from the filename change noted below:

| Skill | What it covers |
|---|---|
| `obsidian-markdown` | Obsidian Flavored Markdown — wikilinks, embeds, callouts, properties, block refs |
| `obsidian-bases` | `.base` live database views over note frontmatter |
| `json-canvas` | `.canvas` files (JSON Canvas open format) |
| `obsidian-cli` | driving an Obsidian vault from the command line |
| `defuddle` | extracting clean Markdown from web pages |
| `knap` | batch-rendering notes from JSON/CSV data |

### Two placements

1. **Sibling skills** — `skills/obsidian-markdown/`, `skills/obsidian-bases/`,
   `skills/json-canvas/`, `skills/obsidian-cli/`, `skills/defuddle/`, `skills/knap/`.
   Installed as first-class skills by the `project-knowledge-vault` plugin, alongside
   `project-knowledge-vault` itself (seven skills total). Verbatim upstream copies, `SKILL.md`
   filenames intact.

2. **Embedded inside project-knowledge-vault** —
   `skills/project-knowledge-vault/references/obsidian-skills/<name>/`.
   Present so the `project-knowledge-vault` skill is self-contained: the standalone packaged
   `project-knowledge-vault.skill` carries the companions with it. In this placement each
   upstream `SKILL.md` is renamed to `<name>.md` (e.g.
   `references/obsidian-skills/obsidian-bases/obsidian-bases.md`) so the embedded copies are
   reference material rather than six separately registered skills. Each skill's own
   `references/*` files are kept alongside its renamed body. No other content is changed, and
   upstream's copyright notice is preserved.

### Refreshing

Re-clone upstream, re-copy both placements, bump the pinned commit above (and in
`skills/project-knowledge-vault/references/obsidian-skills/README.md`), and rebuild
`project-knowledge-vault.skill`.

---

This repository's own code and the `project-knowledge-vault` skill are MIT licensed — see
[`LICENSE`](LICENSE).
