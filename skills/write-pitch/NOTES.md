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

## The call and the hurdles
- The call starts from Valuation "Overall verdict" and Short Check "Verdict (agent's call)" (fallback "Verdict (the
  rule)"). An override needs cited evidence.
- Hurdles come from the user's own Valuation inputs ("IRR hurdle", "Buy at R/R", "Table-pound at R/R") via
  labels.py; common.HURDLES is only the fallback.
- Buy price = 3-year target / (1 + hurdle)^3. No-brainer price = target / 1.3^3 (30% IRR, the course's figure).
- plan.py rule ids [R1]-[R21] are kept in sync with plan_schema section 12 by a test.

## SUM boxes
- XML-only writes (copied from model-summary's xlsx.py); verify.py proves every other part is byte-identical.
- Unlike model-summary, which deletes calcChain.xml, sum_boxes keeps calcChain byte-identical and sets
  fullCalcOnLoad. It never adds or removes a formula cell, so this changes the user's file less.
- The ownership record sum_written.json holds the carry-forward rules (what the user typed over is kept). A stale
  `<dimension>` is reset.

## Working folder
- Working files live in `<research>/<T>/Pitch/_work/`, per the spec: the plate file is a research artefact the next
  rerun reads. Only the SUM record goes in `<model dir>/_model_work/write-pitch/`. This differs from the general rule
  in CLAUDE.md. Model copies made there are always deleted.

## Other choices
- export_pdf uses a fresh LibreOffice profile per call so the deck and the sheet can convert at the same time.
- The briefs are the course in our own words with section pointers. The course's example pitches are deliberately
  not shipped and not read at run time.
- python-pptx and python-docx must be importable under `python3 -I`, because the scripts run with -I.
