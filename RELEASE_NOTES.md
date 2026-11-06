# Release notes - project-knowledge-vault 1.3.0

**Released:** 2026-11-06. **Includes:** 1.1.0 (chat-upload intake), which has not yet been
merged to `main`.

## Highlights

### P6 schedules are now analysed by the skill
Questions about a Primavera P6 `.xer` are now answered with a bundled tool,
`scripts/xer_tool.py`, instead of a parser written fresh each session. It needs no install
(standard-library Python only) and never changes the XER.

| You want to know | Run |
|---|---|
| What is driving the finish? | `longest-path <xer> [--to CODE]` |
| What changed since the last update or the baseline? | `diff <old.xer> <new.xer>` |
| Did the milestone gaps hold in the new baseline, TIA or mitigation? | `gaps <old.xer> <new.xer> --keys NEA,H2C,PFHO` |
| Is the schedule technically sound? | `dcma <xer> [--baseline BL.xer]` |
| Cost or hours performance | `earned-value <xer> [--baseline BL.xer]` |
| Quick facts, listings, one activity | `summary`, `activities`, `activity`, `wbs`, `relationships`, `calendars`, `resources` |

Each command prints Markdown. Add `--json`, `--out report.md`, or `--csv <dir>` to get a table
you can hand to the xlsx skill for a workbook.

### Milestone gap check (`gaps`)
Built from a hand-made Excel comparison of milestones by phase. Give it the versions oldest
first. For each phase/ROMP it reports:
- **Delta:** how far each milestone moved against the reference version.
- **Stagger:** the gap to the same milestone in the previous phase.
- **Steps:** the gaps inside the phase, for example NEA → H2C → PFHO.
- **Squeezed gaps:** gaps tighter than in the reference, worst first.
- **Flags:** zero or out-of-sequence gaps, marked *new* or *already so in the reference*.
- **Cadence summary:** the minimum, mean and maximum of each gap type.

Dates that exist only in a narrative table or a marked-up image can be supplied as a
three-column CSV (`Group,Milestone,Date`) alongside the XERs. Phases are found from the
activity name ("ROMP 3: … (NEA)"), else the WBS node ("ROMP 03"), else the activity code.

### Accuracy
- `longest-path` matched P6's own longest-path flags exactly on all 24 real schedules tested.
- `gaps` reproduced every figure in the reference Excel analysis: 118 of 118 dates, deltas and
  gaps.

### Also in this release (from 1.1.0)
- **Intake mode.** Files dragged into the chat are saved into the right project folder and
  indexed in the vault, so later sessions know they exist.

## Upgrading

- **Claude Code (plugin):** after this is merged to `main`, run
  `/plugin marketplace update project-knowledge-vault`, then reinstall or update the plugin.
- **Cowork / claude.ai:** Cowork uses the copy saved in your claude.ai account, not GitHub. In
  claude.ai go to **Settings → Capabilities → Skills**, then replace `project-knowledge-vault`
  with the `project-knowledge-vault.skill` file from this repo. Start a new session afterwards.
- Existing vaults need no migration. Schedule commands work on any `.xer` in the project's
  `Schedule/` folders.

## Known limitations

- The tool reads P6's last calculated dates; it does not reschedule. Export after F9 for current
  dates.
- One longest-path rule (an SS lag driving an activity that has already started) rests on a
  single observed case. All 24 test schedules match, but evidence for that rule is thin.
- Resource over-allocation reads P6 resource limits literally, so placeholder resources can show
  meaningless peaks.
- Without `--baseline`, DCMA checks #11 and #14 use the XER's planned dates and say so.

See [CHANGELOG.md](CHANGELOG.md) for the full history.
