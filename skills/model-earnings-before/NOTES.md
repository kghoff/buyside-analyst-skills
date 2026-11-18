# model-earnings-before notes

Why things are the way they are. Read before changing scripts.

## Origin
- Built from Chapter 13 (Earnings Season), first of three skills (model-earnings-before, model-update,
  model-earnings-after). Spec docs/2026-11-18-model-earnings-before-design.md, plan
  docs/2026-11-18-model-earnings-before-plan.md (local).
- Same shape as model-short: context.py → earnings-analyst → plan.py + anchors.py → build.py (raw XML) → verify.py
  (one recalculation) → note.py. All math lives in earnmath.py; the tab's formulas compute the same things and
  verify.py proves they agree.

## Choices
- The stance is the rule's (earnmath.stance), not the agent's: plan.py rejects a different stance. The user may type
  over it on the tab; a rerun keeps it and the note says "You changed this."
- P(upside) is the agent's probability of the upside case, so edge = P(upside) − implied PSUC compares like with
  like.
- Run-up = T-8 → T-1 close (seven daily moves); drift = reaction-day close → 7 trading days later (the chapter's NFLX
  "Drift (T+7)").
- The implied move is used only when Yahoo's earnings date is ahead of today: Yahoo shows the last date until the
  next is announced, and a straddle with no print in it is not a print move. The date is then estimated as last
  year's release for the same quarter + 364 days (same weekday) and is a yellow cell.
- "Documents since the last print" includes the print day itself (the release and call set the bar).
- The rating-change set-up row is the agent's (anchored to the Consensus log or the documents), not code's.
- Consensus means are typed (blue) into the variance table, not linked: the mean rows sit above the block and move
  when the broker count changes, and model-consensus carries B-H cells over as the user's on a rerun, so a link would
  point at the wrong row. The source is a text cell (column L of the header row) instead of a note: comments on an
  existing tab would touch its drawing parts.
- The variance gate: skeleton (model-consensus's labels, nothing in C-H) or ours (every B-H cell equals
  variance_written.json, placeholder labels included) → fill; anything else → the user is asked. model-consensus's
  "(key driver)" placeholder labels are renamed to the forecast plan's drivers without asking: they are its
  placeholders, not the user's words (every other cell that holds something is skipped unless the user chose to
  overwrite).
- Before writing into the Consensus tab, variance.put_cells writes out cell by cell every shared formula group it
  touches (a user's fill-down is stored as one master and children; overwriting the master orphans the children and
  Excel asks to repair the file). Copied from research-filings xledit.unshare, not imported (skills stay separate).
- On a rerun context.py reads the rule's thresholds (band 8) from the Earnings tab in the values copy, by their
  column-A label, numbers only, so code's answers and plan.py's stance check use the user's thresholds, not the
  house defaults; context.md says which came from the tab.
- The frozen forecast is re-frozen only for a new quarter (or --refreeze), so a rerun the day before the print keeps
  the pre-print view model-earnings-after compares against.
- lay_out runs twice: the rule (band 1) and the set-up row read rows below them and the thresholds (band 8); pass 1
  finds every row, pass 2 writes the formulas. The layout never depends on the refs; build.py checks the passes agree.
- Formulas nest IF(ISNUMBER(x), test, FALSE) instead of AND(ISNUMBER(x), test): AND evaluates every argument, so an
  #N/A or text in x would turn the whole cell into an error.
- Px Data holds a daily and a weekly block in the same header row ("{T} close" twice): rates.py keeps the first
  (leftmost) match, the daily block.
- Cash is found by "cash and/& (cash) equivalents" (the house label is "Cash & Equivalents"); FCF by a row ending
  "free cash flow" in a section starting "free cash flow" first.
- The documents list starts at the last print's release date (Px Events "Event date"), not the reaction day: an
  after-close release is dated the day before its reaction.
- A warning (not a stop) when Px Events lists a full-results release for MOD's first forecast quarter: the actuals
  have not been entered yet.
- Rel. performance, the fallback price and NTM EPS use only complete data (last row with both closes; 4 forecast
  quarters), so Python and the formulas agree.
