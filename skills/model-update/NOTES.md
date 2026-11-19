# model-update notes

Why things are the way they are. Read before changing scripts.

## Origin
- Built from Chapter 13 (Earnings Season), second of three skills (model-earnings-before, model-update,
  model-earnings-after). Spec docs/2026-11-18-model-update-design.md, plan docs/2026-11-18-model-update-plan.md
  (local). The scripts were reworked after reviews on the real DXCM model; the docstrings are the current contract.
- `xlsx.py`, `xledit.py`, `modmap.py`, `modfill.py`, `notebox.py`, `lo.py` are copies of model-forecast's (first line
  says so; keep in sync). model-forecast's own `move_rows.py` / `build.py` / `check.py` / `layout.py` are called from
  their folder for the roll, never copied.

## Matching
- **Value matching, not labels.** The release prints the year-ago quarter next to the new one, and the model
  already holds it. A prior-period value that equals a model cell is near-proof of the row; labels change between
  releases and between the release and the 10-K. Labels only break ties (two rows with the same value, e.g. total
  assets and total liabilities + equity).
- **Zero never matches by value.** Too many rows are 0; a zero maps only on an exact label (`zero_skipped`).
- **Table kind picks the section first.** A reconciliation's "GAAP gross profit" equals the income statement's
  gross profit; searching the NON-GAAP rows first keeps each on its own row. Only if nothing in the preferred
  sections matches are all rows searched, and a claim from a line's own section beats a fallback one.
- **Signs.** Models keep costs negative or positive by habit; `sign` is read from the year-ago value, so the release's
  number enters in the model's sign.
- **Repeated adjustments.** The same adjustment printed in several reconciliation blocks (MOD keys them `#2`, `#3`) is
  paired k-th occurrence to k-th row; with unequal counts only when every occurrence prints the same current value.
- **Never guess a column.** `no_layout` (more value columns than the header explains, e.g. segments) and `no_prior`
  are reported, not matched.
- **Summed rows.** A row the model keeps as the sum of printed lines is matched by code when 2-3 leftover lines add up
  to its year-ago value; the agent can do the same with several `map` answers on one key, each with `"sum": true`.
  Without the flag a second answer on a taken row is refused (it is usually a mistake).
- **Agent anchors.** Every release line already carries its file and line from the parser, so the agent's anchor is
  checked by `match.check_anchor` (its own line, the number on it) instead of copying model-earnings-before's
  anchors.py. apply checks every answer before changing anything.

## Entering actuals
- **Formula skeleton.** A row whose year-ago cell is a structure formula (own or earlier columns only, no constant, no
  absolute ref) gets it translated into the new column (the chapter's "copy last year's column"). Anything else is an
  input: the release value, or it waits.
- **Placeholders, not blanks** (user decision 2026-11-18). On DXCM, blank waiting cells broke 1,700+ forecast cells.
  A waiting cell keeps its pre-print forecast VALUE (never the formula: a formula in an actual column would be a
  forecast pretending to be history), orange, with an `Update: forecast placeholder` note, listed in state.json.
  tieout skips them, frozen's table shows no actual for them, verify proves each is orange, noted and listed. Kinds:
  10-Q / 10-K (a filing will print it), driver (DRIVERS sections or rows with no history), manual (analysis rows
  the user keeps by hand).
- **Typed subtotals.** A structure formula over a placeholder stays a formula, except where the release prints that
  subtotal: then the printed value is typed (the release is the truth) and the formula saved in state.json; the 10-Q
  rerun puts it back once nothing it reads waits.
- **Cash flow is year-to-date in releases.** The quarter is `=YTD - earlier quarters` (blue, the YTD cited).
- **Q4** follows last year's Q4: where it was `FY less Q1-Q3`, the year column takes the release's full-year value and
  Q4 stays the plug; otherwise Q4 is typed and the year sums (flows) or links (balances). Per-share, share-count and
  rate lines wait instead of summing.
- **Restatements** are never typed without the user's yes. The question shows `restate_knock_on` (the Q4 plug or year
  total that moves with each restated quarter) because a restated Q2 silently moves a `FY less Q1-Q3` Q4.
- **New lines are reported, never inserted.** Row inserts shift every reference in the workbook and belong to
  model-historicals / model-kpis.
- **state.json is written into `$TMP` and copied with the model.** actuals.py writes it as it builds the copy; a run
  that stops later must not leave a state describing cells the user's file doesn't have (the 10-Q rerun would skip
  them). The 10-Q pass is run twice when the user answers the differences question, each time from the saved state.

## Guidance
- **Guidance blocks show completed years only** (research-filings `block_guidance`). On Q1–Q3 prints the guides are
  only recorded (`Filings Research/_work/readers/update_<quarter>/guidance.csv`); on a Q4 print the closed year is
  added to model_series.csv, `last_year` is bumped and Filings Charts is rebuilt with `handoff.py --charts-only` (the
  one change made to research-filings). close-year writes research-filings' data before verify; if the run stops
  after it, a rerun skips the rows already added.

## Forecast roll
- **Targeted roll is enforced by code.** plandiff.py fails if any plan entry changed without a changes.json entry, or
  an entry lists a change that isn't one. The agent edits a copy of the plan in the quarter folder; model-forecast's
  plan is replaced only together with the model.
- **The roll keeps every MOD row in place.** model-forecast's build / move_rows / layout can insert or move rows when
  a plan adds rows, a section, a seasonal line (it inserts a seasonality row) or changes its layout. state.json names
  waiting cells, placeholders and typed subtotals (with their saved formula text) by cell, so a moved row would make
  the 10-Q rerun fill, or put a formula into, the wrong cell. Rather than remap every ref, the roll changes
  assumptions only: plandiff refuses `new_rows`, `move_rows`, `layout`, `driver_sections` changes and a switch to
  `seasonal`; the dry run and verify.py refuse any moved line (`verify.moved`, by row key). On the real DXCM model an
  unchanged plan rebuilt with all four scripts moved no row, so an honest roll never trips it. Structural changes are
  named in the agent's reply for the user to make with /model-forecast.
- **The build runs even with no changes**: seasonal years re-split around the new actual quarter.
- **Thesis first.** The reading list is one list in SKILL.md (pitch deck from /write-pitch first, when it exists).

## verify.py, and which checks live elsewhere
- With `--mid` (the actuals copy) the positional checks (cells outside the allowed columns unchanged; every typed value
  and placeholder noted, placeholders orange and listed) run on before → mid, where state.json's refs hold; the roll
  (mid → after) may change only forecast columns, no line may move, and the note checks run again on the rolled copy.
  Errors (per tab, against the recalculated original), byte-identical parts, the balance sheet in the reported column
  and the links from other tabs (label and period, so they would survive a move) run on before → after.
- Spec checks verify.py does not repeat, because model-forecast's `check.py` already proves them on every roll (and
  the run stops unless it exits 0): quarters sum to the year (Q4 for balances) in every forecast year, revenue comes
  from the drivers, balance and cash ties in the forecast, guidance landed or missed on purpose. "Each subtotal equals
  the release" and "each typed number is on its anchored line" are tieout.py and match.check_anchor. Earnings band 7
  byte-identical is the parts check (another tab's part).
- **One write.** Actuals, the forecast build and the Q4 charts all go into one temp copy; verify runs on it; the user's
  file is replaced once, after a checksum shows it didn't change meanwhile.
