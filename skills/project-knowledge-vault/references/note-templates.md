# Note Templates

Copy-and-fill templates. Keep them consistent across the vault — consistency is what makes parallel
authoring and reliable linking possible.

## Equipment / asset note
```markdown
---
type: equipment
discipline: <Discipline hub name>
category: <Chiller | Pump | Transformer | Crane | AHU | ...>
tags: [equipment, <discipline-lower>, <category-lower>]
source: [<sheet ids>, <spec sections>, <narrative>]
phase: <phase>
---

# <Equipment Name (Abbrev / Tag)>

**Discipline:** [[<Discipline hub>]]  |  **System:** [[<System hub>]]

<1–2 sentence description of what it is and its role.>

## Key Data
| Attribute | Value |
|---|---|
| Tag(s) | ... |
| Quantity | ... |
| Capacity / Rating | ... |
| Location | ... |
| Served by / Serves | ... |
| Manufacturer / BOD | ... |

## Specifications & Requirements
- <notable spec/schedule requirement> (source ref)

## Interdependencies
- <what it connects to / depends on — power, water loop, controls, structural support> ([[wikilinks]])

## Source References
- Drawings: ...  · Specs: ...  · Narrative: ...

## Notes / Open Items
- <ambiguities/conflicts → link the register>
```

## Discipline hub
```markdown
---
type: discipline
discipline: <Name>
engineer: <EOR/consultant>
spec_divisions: [...]
drawing_prefix: [...]
tags: [discipline, <name-lower>]
---

# <Discipline>

**Engineer of Record / consultant · Drawings · Specs · Narrative** (one line each).

Short overview of the discipline's scope on this project.

## Systems / Key equipment
[[...]] · [[...]]   (link the system hubs and the major equipment notes)

## Design criteria (highlights)
...

## Interdependencies
- Cross-links to other disciplines.

## Issues / open items
See [[Conflicts & Issues Register]] — <the discipline's flagged items>.
```

## System hub
Same idea, `type: system`; sections: **Configuration/components** (link equipment notes), **Key
parameters**, **Interdependencies**, **Issues**.

## Register notes (in `07 - Issues & Conflicts`)
- **Conflicts & Issues Register** — table: `ID | Item | Discipline(s) | Source | Status`. Group by kind
  (documentation discrepancies, cross-discipline coordination, equipment/schedule data). Give IDs
  (e.g. X-1, E-1).
- **Information Gaps & Open Questions** — table: `ID (G-#) | Gap/question | Where it lives (note link) |
  Source to check | Status (🔴/🟡/🟢) | Added`.
- **Scope Clarifications (for Owner)** — table: `# (SC-#) | Topic | Discipline | Clarification needed |
  Recommended position | Impact | Ref`, plus a short "design-team RFIs (separate track)" list.

## Home / MOC
Dashboard linking: Start-here project notes, all discipline hubs, all system hubs, key equipment
anchors, document indexes, and the registers. Add a "Living vault" line pointing at the change log.

---

## Shared context files (scratch folder, for consistency + subagents)
Write these before Phase 3/4; they are NOT part of the vault.

**`PROJECT_FACTS.md`** — the key facts you've mined so far, organized by discipline/system: identity
(project, location, stage, delivery), team, phasing, and per-discipline capacities/tags/quantities
(e.g., plant tonnage, electrical service & switchboard tags, major equipment counts). Subagents read
this so they don't re-derive basics.

**`STYLE_GUIDE.md`** — for equipment-note authors. Contains: where to write notes, the source-text file
paths, the equipment template above, and — critically — the **exact list of hub-note names** to use in
`[[wikilinks]]` (discipline hubs, system hubs, register names). Instruct authors never to invent new hub
names, to capture real tags/quantities/capacities, and to route conflicts to the register. Have them
return a compact manifest only.
