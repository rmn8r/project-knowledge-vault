# Update Workflow (Living Vault)

The vault's value compounds only if it stays current. Treat the project chat as the working session.

## Default behavior (confirm/adjust with the user once)
- **Answer first, update second.** Fully answer the user's question in chat, THEN make vault edits, THEN
  report what changed in 2–4 lines. Never make the user wait on note-writing to get their answer.
- **Auto-apply** edits by default (don't wait for approval per edit). If the user prefers, switch to
  "propose-then-confirm."
- **Capture scope = material findings, gaps, conflicts.** A *material finding* is a new fact, resolved
  value, or decision. Skip routine lookups that merely restate what a note already says — those don't
  earn an edit.

## What to do with each kind of thing
- **Material finding** → write it into the most relevant note (create the note if it's a new asset),
  cite the source, and flip any matching gap row to resolved (🟢).
- **Information gap** (docs can't answer) → add a row to the Information Gaps register, linked to the
  note where the answer belongs, with the likely source to check.
- **Conflict / contradiction** → add to the Conflicts & Issues Register with an ID.
- **Owner decision / scope boundary** → add to Scope Clarifications with a recommended position.
- Always append a dated entry (newest first) to **`Vault Change Log`** summarizing notes touched and
  gaps/conflicts added or resolved.

## Consistency rules
- Reuse the **exact hub-note names** and the equipment template from the original build.
- Ensure new `[[wikilinks]]` resolve — create the target note or add an `aliases:` entry. Run
  `scripts/verify_links.py` after a batch of edits.
- If a note already covers the topic, **update it in place** rather than creating a duplicate.

## Integrating newly added files/folders
When the user drops new documents (e.g., a `Geotech/`, `Schedule/`, `Site Logistics/` folder):
1. **Inventory + extract** just the new files (Phases 1–2 on the subset).
2. **Create** the appropriate new note(s): a summary/index note per new document type
   (e.g., a geotech summary, a schedule note, a site-logistics note), in `01 - Project` or `06 - Documents`.
3. **Enrich** existing notes the new data touches (e.g., new geotech bearing values → the mat-foundation
   and site notes; a real CM schedule → supersede any earlier estimated schedule and note that).
4. **Flag** anything the new docs contradict or leave open → registers (e.g., an enclosure system in the
   schedule that differs from the drawings → a conflict).
5. **Update** `Source Documents` (add the new files with dates) and `00 - Home` (link new notes).
6. **Re-verify** links.

## Persistence across sessions
Save a short **project memory** capturing: vault location, the structure/hub names, where the source
docs live, and this update workflow — so a future chat extends the vault instead of rebuilding it. If a
memory already exists, update it rather than duplicating.
