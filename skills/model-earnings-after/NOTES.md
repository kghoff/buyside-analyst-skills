# model-earnings-after notes

Why things are the way they are. Read before changing scripts.

## Origin
- Built from Chapter 13 (Earnings Season), third of three skills (model-earnings-before, model-update,
  model-earnings-after). Sections used: 13.6 "Print Day: The SFOT Framework", "The Earnings Reaction Note",
  "Adjusting the Price Target on Earnings", "Earnings as a Checkpoint"; 13.7 "Summarize the Call", "Tracking
  Long-Term Guidance", "The Wrap and the Go-Forward", "Predict, Then React", "Reaction Patterns Worth Trading",
  "Weird Reactions", "Fading Moves and the Prospective IRR". Spec docs/2026-11-19-model-earnings-after-design.md,
  plan docs/2026-11-19-model-earnings-after-plan.md (local).
- Same shape as model-earnings-before: context.py → earnings-analyst (after_assignment.md) → plan.py + anchors.py →
  build.py (raw XML) → verify.py (one recalculation) → note.py. All math lives in aftermath.py; the tab's formulas
  compute the same things and verify.py proves they agree. xlsx, tabkit, lo, notebox, modmap and rates are copied
  from model-earnings-before (headers say so; keep in sync), never imported.

## Choices
- **Bands 9-15 are spliced under band 8, not a rebuild of the tab.** The preview is the record the print is judged
  against, so it must not move: earnings_tab.splice rewrites only the rows from band 9 down, bands 1-8 stay byte for
  byte, and the user's notes in them are kept byte for byte. The splice refuses (stops) when the user has typed
  anything below band 8 that is not ours, or a threaded comment sits there, rather than drop it.
- **Valuation before is parsed from the dated Valuation Note** (the user's choice; model-earnings-before was not
  changed to freeze valuation): the latest `<date> <T> Valuation Note.md` dated before the release. A layout the
  parser does not recognise gives `?`, never a guess; valnote.RELIED_ON lists every heading and label the parser
  needs, and a drift test checks model-valuation's note.py and build.py still write them. The after side links to the
  Valuation tab, and counts as fresh only if a note is dated on or after the release day (the tab's title carries no
  date); otherwise the report says /model-valuation has not been rerun since the print. The release day, not the
  reaction day: after an after-close release the user's /model-valuation run that evening is dated the release day
  and already knows the print.
- **Before values compare at the note's precision.** The note rounds (reward / risk 0.7x for the tab's 0.672, IRR
  11.2% for 0.1121); valnote.parse records each value's printed decimals (`dp`: 0.7x → 1, $107.76 → 2, 21.8% → 3
  as a fraction) and band 13's change is `ROUND(C,dp)-B` (or `ROUND(C,dp)/B-1`), aftermath.xround computing the same.
  Otherwise a value that did not move shows a spurious change. The target-change row reads that change cell.
- **Signed surprise.** Costs are stored negative in MOD, so surprise = (actual − frozen) / |frozen| reads a smaller
  cost as a beat without a special case per line.
- **σ from the 252 returns before the reaction day** (the reaction day's own return excluded: the move must not
  inflate its own yardstick). Run-up = T-8 → T-1 close, drift = reaction-day close → T+7 close, as the preview defines
  them, so the base rates and this print compare like with like.
- **Yahoo for the open.** Px Data holds closes only; the gap at the open and open-to-close need the reaction day's
  open. A yahoo_after.json for another day is nulled (the rows show `?`) rather than used.
- **"Played out?" is asked whenever the drift is in**, in any mode, a first run made after T+7 included. The T+7
  rerun copies the previous plan (call summary and SFOT kept), fills played_out and changes the react call only if
  the drift changes it, saying so either way.
- **The Call Notes tab is ours.** It is rebuilt whole each run (simpler and safer than cell edits on a tab whose
  columns shift right each quarter); the text the user typed is kept by callnotes.merge's rule (a cell that differs
  from what we last wrote is the user's), older quarters and their notes are kept, formatting is not. Ownership is
  permanent: the tab is never handed over to the user. The header row is found by "Topic" in column A, not a fixed
  row. The tab is put back right after Earnings each run.
- **Next year's "before" estimates come from model-update's pre-print snapshot**
  (`_model_work/update/<Q>/values.json`): band 7 froze only the quarter and its fiscal year.
- **Consensus is read from the preview's variance grid** (Earnings band 6 or the Consensus tab's variance block), the
  numbers as typed before the print. A /model-consensus rerun after the print can change that block; the note says so.
- **Run mode.** `rerun` means bands 9-15 were built for this quarter: the Earnings tab holds them under a title (or
  band 9 header) naming the quarter, or call_notes_written.json (renamed in Step 9 together with
  after_inputs_written.json, and keyed by quarter, which after_inputs_written.json is not) holds it. An
  after_plan.json alone does not count: a run stopped at Step 7 leaves one, and "rerun" turns on the assignment's
  T+7 section (copy the previous plan).
- **Anchors.** Quotes need at least 4 words (short ones match anywhere), are refused straight after a negation (a
  quote that drops the "not" reverses the company's words), and must be found on the line cited. SFOT, call notes and
  guidance may cite only the call's own documents (the transcript, the release, the preview note: plan._call_docs),
  so the call summary cannot drift into older filings or broker views. Every figure in free text must be printed in context.md or on the item's own
  quoted line, as written; otherwise the agent made it up. Free text includes what is typed into the model as the
  company's words: each call note's text and each guidance item's before and now. A guidance "before" was said
  earlier, so it may cite an optional before_anchor + before_quote (any file under the research root, quote checked)
  and take its figures from that line; with no before_anchor, from the previous Call Notes columns (context history).
- **UNVERIFIED by name.** anchors.py --unverified writes each failing problem's name (the longest name check() can
  print that the problem starts with: a topic such as "Driver: units" holds a colon). build.marked matches a name to
  a cell when it equals the cell's key or starts with key + "." or "[" (sfot.tone.reason → the SFOT tone row,
  guidance[0].now → that guidance row, call_notes.Tone[1] → the Tone cell on Call Notes; react.reason marks the call
  and pattern rows, which share it; lt_target and lt_target.year mark both target rows). headline and
  quarter_thoughts have no cell; the note lists every name.
- **Anchor failures build, marked UNVERIFIED** (as model-earnings-before does): after 2 rounds, the cells whose
  anchors still fail are built red and the note lists them; only plan.py failures stop the run. This deviates from
  the spec's error table (which stopped on anchors too): a wrap with one doubtful quote, flagged, is more useful the
  morning after the print than no wrap.
- **The note's name** is `<T> <Q> after-print note <date>.md` in Earnings Reviews, not the spec's
  `<date> <T> After-Print Note.md`: it matches the preview note's `<T> <Q> earnings preview <date>.md`, so a
  quarter's preview and wrap sort together. The date is context.json `today` (the run's date), not the system clock.
- **The wrap on the Earnings tab lasts until the next preview.** Any /model-earnings-before run after /model-update
  targets the next quarter and clears bands 9-15 without asking (it reports `after_cleared`); the after-print note
  and the Call Notes tab keep the wrap. Only a same-quarter preview rerun asks first (below).
- **The long-term target is a fraction equal to anchor_value** (20% → 0.20, in MOD's units), so the pace math and
  the check against the printed line use one number.
- **Same-quarter preview rerun.** A /model-earnings-before rerun for the quarter already reviewed can shift the rows
  bands 9-15 point at, so it stops unless given `--clear-after`; then `/model-earnings-after <T> --rebuild` re-lays
  bands 9-15 from the saved plan with the user's recorded edits, no agent.

## Known issues in sibling skills (not fixed here)
- model-earnings-before build.py recognises only Excel's `<o:idmap v:ext="edit" data=...>` form when it collects
  used VML id blocks; after an openpyxl save the prefix or attribute order can differ, so ids can collide.
  earnings_tab.py here matches any prefix.
- model-valuation note.py hardcodes the label "IRR: price in 3 years"; a different IRR horizon on the tab would
  break that line of its note.
