# write-pitch notes

Why things are the way they are. Read before changing scripts.

## One analyst reads everything
- The requirement is "one mind": one Opus agent (pitch-analyst) holds all the research, the earlier agents' reasoning
  files, the model digest and the tab pictures in one context, so the pitch is one coherent view and not stitched
  summaries.
- Gate test, 2026-11-19: an Opus subagent read a 17,000-line (about 2 MB) file in sequential chunks and, from memory,
  quoted a marker near the start, one near the end and an exact middle line. About 825k tokens used, no compaction.
- One Read call is capped at about 25k tokens, so the assignment tells the agent to read in chunks of about 500 lines
  and never skip.
- If a future model or tool change breaks this, the fallback design is digest agents feeding one writer.

## The model digest
- Bulk-block rule, per column: a block over 200 rows, or a column with over 200 values that are at least 80%
  numeric or date, is summarised as first / last / min / max / latest percentile. A text column over 200 cells is
  summarised with its distinct values. Error values collapse to ranges and are never used as headers.
- MOD is exempt but filtered: annual columns, the last 8 actual quarters and all forecast quarters; notes only on
  kept columns.
- Tables and row lines are compact, with a `headers:` legend so cell refs stay recoverable.
- Size on the user's DXCM dev model: 263k words in the first version, 143k after the compact format and fixes
  (target about 150k).

## Tab pictures
- LibreOffice prints every sheet (hidden ones too) as one page. A tall or wide page is cut into 1000-pt tiles (1.3
  times as tall), blank tiles are skipped, and at most 24 tiles are kept for tabs with charts and 4 for the others
  (their numbers are in the digest). Hidden tabs get no pictures.
- DXCM: about 103 PNGs, 32 MB, 12 seconds.

## Decks
- .pptx from a JSON plan: editable, imports into Google Slides. The agent decides content; code does layout. The
  template can be restyled because the builder finds layouts by name and placeholders by idx.
- UNVERIFIED goes to speaker notes, not the slide face. The user presents these decks in interviews. The report lists
  every item and the run is not done until the user has seen them.
- Length budgets live in common.BUDGET (including `row` 90 for checklist questions). Tuned with full-budget mocks
  rendered through LibreOffice: a 15 x 90 checklist fits, the summary is capped at 3 bullets, risk_reward short
  lines got their own box (idx 16).
- The pitch sheet is 8.5pt so full-budget text stays on 2 pages; know_cold is capped at 10.
- Table of contents: an exception to the house rule (every report has one after the cover). The decks and the pitch
  sheet have none: in a pitch deck, slide 2's summary and the accordion structure (ten core slides, then support
  slides each tied to a thesis point or risk, then the appendix) play that role, and a contents slide would cost one
  of the ten; the sheet is 2 pages. The Markdown copy keeps its contents list (build_md.py), since it is read as a
  document.

## The call and the hurdles
- The call starts from Valuation "Overall verdict" and Short Check "Verdict (agent's call)" (fallback "Verdict (the
  rule)"). An override needs cited evidence.
- Hurdles come from the user's own Valuation inputs ("IRR hurdle", "Buy at R/R", "Table-pound at R/R") via
  labels.py; common.HURDLES is only the fallback.
- Buy price = 3-year target / (1 + hurdle)^3. No-brainer price = target / 1.3^3 (30% IRR, the course's figure).
  plan.py checks both against the hurdle it was given ([R23], within 0.5% or the shown rounding), so a buy price
  worked at the house 20% fails when the user's tab says otherwise.
- A Long must clear both the IRR hurdle and the buy R/R (the user's decision, 2026-11-19; it used to be either).
  `override` (call vs the Valuation verdict) and `hurdle_override` (waives the hurdle check) are separate fields, so
  one cannot quietly do the other's job. A Valuation verdict outside Buy / Hold / Sell is a problem, not skipped.
- plan.py --anchor-problems takes anchors.py's --json: a Long whose hurdle numbers failed their anchors gets [R20].
- plan.py rule ids [R1]-[R23] are kept in sync with plan_schema section 12 by a test.
- plan.py rejects every plan the builders cannot build: a field's shape is checked on any slide that carries it
  (build_md prints any field wherever it is), and a test feeds single-field breakages of the example plan through
  plan.py and builds every one it accepts. plan.py runs before the build; anchors.py problems do not stop it.

## SUM boxes
- XML-only writes (copied from model-summary's xlsx.py); verify.py proves every other part is byte-identical.
- Unlike model-summary, which deletes calcChain.xml, sum_boxes keeps calcChain byte-identical and sets
  fullCalcOnLoad. It never adds or removes a formula cell, so this changes the user's file less.
- The ownership record sum_written.json holds the carry-forward rules (what the user typed over is kept). A stale
  `<dimension>` is reset.

## Working folder
- The research-side working files (plate, plan, PM review, digest, tab pictures, build output) live in
  `<research>/<T>/Pitch/_work/`, per the spec: the plate file is a research artefact the next rerun reads. This is an
  exception to the general rule in CLAUDE.md.
- Copies of the model (the recalculated `values/` and the SUM-box `out.xlsx`) and the SUM record follow the house
  rule: `<model dir>/_model_work/write-pitch/`. The copies are always deleted.
- Step 10 waits for Excel to close before it retakes the checksum, then copies straight away: a save made while
  closing Excel must change the checksum, not be overwritten.

## Preflight freshness
- Read-only openpyxl trusts a sheet's `<dimension>`; preflight resets it before reading MOD and Px Events (a stale
  one hid MOD's period headers and Px Events' newest rows).
- Px Events' left block lists only MOD's actual quarters (model-price-history builds it from them), so a quarter
  reported but not yet in MOD shows only in the event block, as an "Earnings" event named "<period> earnings". If
  /model-price-history was not rerun after the release either, nothing in the model shows it and preflight cannot
  tell.
- SUM's date is the mtime of model-summary's `inputs_written.json`: copyover.py promotes it only after a successful
  copy-over, so an aborted run's newer work files do not count as a fresh SUM.

## Other choices
- export_pdf uses a fresh LibreOffice profile per call so the deck and the sheet can convert at the same time.
- The briefs are the course in our own words with section pointers. The course's example pitches are deliberately
  not shipped and not read at run time.
- python-pptx and python-docx must be importable under `python3 -I`, because the scripts run with -I.
