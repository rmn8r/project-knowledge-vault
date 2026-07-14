# Vault Structure

Canonical layout. Numeric prefixes force useful ordering in Obsidian's file explorer. Adapt discipline/
system names to the project's domain, but keep names **stable** once fixed (links depend on them).

```
<Project> Vault/
├── 00 - Home.md                     # Map of content / dashboard — the entry point
├── README.md                        # How to open & how the living-vault workflow works
├── Vault Change Log.md              # Running log of edits (newest first)
├── 01 - Project/                    # Overview, Directory (Team), Codes & Standards, Phasing,
│                                    #   Site & Location, Building Areas & Levels, plus cross-cutting
│                                    #   references (Testing/Cx, Owner-Furnished OFCI/OFOI/NIC, Geotech…)
├── 02 - Disciplines/                # One hub per discipline (see below)
├── 03 - Systems/                    # One hub per cross-discipline system
├── 04 - Equipment/                  # One note per tagged equipment/asset (the bulk)
├── 05 - Spaces/                     # Key rooms/areas
├── 06 - Documents/                  # Drawing Index, Specification Index, source-doc map, schedule, etc.
├── 07 - Issues & Conflicts/         # Conflicts Register, Information Gaps, Scope Clarifications, review logs
└── 98 - Templates/                  # Blank note templates for extending the vault
```

## Discipline hubs (AEC example set — trim/add per project)
General · Civil · Landscape · Architectural · Structural · Mechanical (HVAC) · Plumbing ·
Fire Protection · Electrical · Lighting · Integrated Automation (BMCS) · Technology (IT-Telecom) ·
Audiovisual (AV) · Security (ESS) · Vibration & Acoustics · EMI-EMF Shielding

## System hubs (examples)
Central plant / chilled-heating water · Process cooling · Air distribution · Domestic water ·
Sanitary/storm/drainage · Fire suppression · Electrical distribution · Standby/emergency power ·
Grounding & lightning protection · Building management/controls · plus any project-specific process systems.

## Naming & linking rules
- **Wikilinks resolve by filename** (without folder or `.md`). So `[[Mechanical (HVAC)]]` finds
  `02 - Disciplines/Mechanical (HVAC).md` anywhere in the vault. Keep filenames unique.
- Avoid characters illegal in filenames: `\ / : * ? " < > |`. Use `-` or `&` instead.
- If two documents refer to the same thing by different names, pick one filename and add the others as
  `aliases:` in frontmatter so `[[alias]]` still resolves.
- Link **liberally** — the graph and backlinks are the value. A note that nothing links to is a smell.

## Frontmatter (every note)
```yaml
---
type: home | project | discipline | system | equipment | space | document | document-index | register | log
discipline: <discipline hub name, when applicable>
category: <e.g. Chiller, Transformer, Crane>          # equipment notes
tags: [<type>, <discipline-lower>, <category-lower>]
source: [<sheet ids / spec sections / report + page>]
phase: <project phase, if applicable>
aliases: [<alternate names>]                            # optional
---
```

## Graph-view color groups (optional, nice touch)
Obsidian stores graph color groups in `<vault>/.obsidian/graph.json`. Color by **discipline** (property
query `["discipline":"Mechanical"]`, which substring-matches variants) so the big equipment cluster
splits into meaningful sub-clusters, and by **folder** (`path:"07 - Issues"`) for the cross-cutting
notes. Put discipline queries first and add folder-path fallbacks last so every node is colored even if
a property query isn't supported on the user's Obsidian version. `assets/graph.json` has a starter set —
merge its `colorGroups` array into the vault's existing `graph.json` (preserve other settings) and set
`"collapse-color-groups": false` so the legend shows. Changes appear when the user re-opens Graph view.
```
```
