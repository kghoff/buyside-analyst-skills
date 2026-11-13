---
name: model-dcf
description: Add the user's 30-year key-driver DCF tab (assessing what the market expects) to their company model (TICKER_model.xlsx) - the revenue drivers come from the forecast plan's revenue identity (whatever the key drivers are for that company: e.g. units x price, stores x sales per store, segments), each with its growth per year, plus gross margin; the forecast years link to MOD, each driver fades to its long-run rate after that, cost inputs, WACC and terminal multiple, all as yellow input cells the user owns; value per share, terminal-value share, implied P/E, and a reverse DCF snapshot (what today's price and the 3-year high and low imply for each driver). A rerun keeps every value the user typed. No scenarios, no agent, no approval step. Run after /model-forecast and /model-price-history. Use when the user runs /model-dcf TICKER or asks for a DCF, a reverse DCF or what the price implies.
---

# /model-dcf

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

`R="$SKILLS/model-dcf"` (scripts in `$R/scripts`). Tell the user everything in plain
English. Code does all of it (no agent): The user sets their own scenarios by typing in the yellow cells.

**Hard rules.**
- The user's model is never edited in place and never saved with openpyxl (that deletes their text boxes and pictures).
  Builds run on a copy in a temp folder; their file is replaced only after the check passes, and only if it is
  unchanged since the copy and not open.
- Only the DCF tab changes (added, or replaced whole on a rerun). MOD is never touched. check.py proves it.
- Never overwrite a number the user typed in a yellow cell: solve.py reads them back from the existing tab.
- No backup copies of the model. Work files live in `$MW` (`_model_work/dcf/`); temp folders are removed.
- Never say "done" with a check open.

## 0. Preflight
1. The model: `$RD/<T>/<T>_model.xlsx` if it exists; otherwise ask the user for the path (e.g. `<model dir>/TICKER_model.xlsx`).
   `MODEL=<path>`,
   `MW=<model folder>/_model_work/dcf` (create it).
2. MOD needs forecast years (run /model-forecast first) and the model needs a `Px Data` tab with closes (run
   /model-price-history first). context.py stops with a plain message if either is missing; pass it on.
   The filings and street research are not read directly: the drivers and their long-run rates come from the forecast plan
   (`<model folder>/_model_work/forecast/forecast_plan.json`, its `revenue_identity`).
3. The model must not be open in Excel: no `~$<model file name>` lock file in its folder. If there is one, ask the user
   to close it.

## 1. Context
```bash
python3 $R/scripts/context.py "$MODEL" "$MW/context.json"
```
Read only. The revenue drivers (the identity's factors: their MOD rows, levels in the last actual year, year 0 and
each forecast year, and long-run growth), MOD's year 0 and forecast years, history, the cap table and the price (last
Px Data close, 3-year high and low), each with the cell it came from. Statement rows are found by role (a label
pattern within their section, as /model-historicals reads its template), so any company's labels work: debt is every
debt-like liability row summed (`cap.debt_current_labels`, `cap.debt_lt_labels` say which; tell the user in step 6),
short-term securities are 0 if the model has none, and opex is gross profit - operating income (all operating
expenses, however the company splits them). A missing required row stops with its plain name; pass it on. If the forecast plan has no revenue identity
(a forecast built before identities existed), revenue itself becomes the only driver and `identity_fallback` is
true: tell the user in step 6 that the DCF is a growth engine until /model-forecast is rerun.

## 2. Solve
```bash
python3 $R/scripts/solve.py --model "$MODEL" --ctx "$MW/context.json" --written "$MW/inputs_written.json" --out "$MW/solved.json"
```
Read only. It prints value per share, the terminal-value share and which inputs were kept vs defaulted.
- The user's cells: a yellow cell counts as theirs if it differs from what the last build wrote there
  (`$MW/inputs_written.json`); cells still equal to it take fresh defaults, so MOD changes flow through. A formula they
  typed stays their formula. Inputs are found by row label and year, so a tab built for other drivers still gives up
  the inputs it shares (gross margin, costs, WACC, multiple); `orphans` lists any old driver row with no home and
  the years the user typed in it: tell them, so they can retype them on the new driver rows.
- Defaults: the forecast years are MOD (links, not inputs); after them each driver's growth fades in a straight
  line over 10 years from its last forecast-year growth to its long-run rate from the forecast plan, gross margin
  change to 0 bps, then holds; cost inputs hold MOD's last-year values; WACC 8%, multiple 10x.
- A formula the user types that points at cells inside the DCF tab can move if the tab's layout changes in a later
  version of this skill; check.py flags a formula that no longer gives the value the reverse DCF used.
- A value they type that equals the default is treated as the default and refreshes with MOD.
- A tab built before `inputs_written.json` existed keeps all its values as theirs (they won't refresh).
- If the existing tab has no year header, it stops with a plain message (pass it on); it never silently resets
  the user's inputs.
- Reverse DCF: one driver at a time (each revenue driver, then gross margin), the same amount added to its five
  yellow cells after the forecast (DXCM: 2031E-2035E) (the others at their
  inputs) until value per share equals the price; the user can reproduce any row by typing it in. "out of range" means
  no move in the searched range reaches it.

## 3. Build on a copy and check
```bash
T=$(mktemp -d)
cp "$MODEL" "$T/before.xlsx"
python3 $R/scripts/build.py --model "$T/before.xlsx" --ctx "$MW/context.json" --solved "$MW/solved.json" --out "$T/after.xlsx" --written "$T/inputs_written.json" > "$MW/build_report.json"
python3 $R/scripts/check.py --before "$T/before.xlsx" --after "$T/after.xlsx" --ctx "$MW/context.json" --solved "$MW/solved.json" --work "$T" > "$MW/check_report.json"
```
check.py exits 1 if anything is wrong (`problems`): broken XML, a change outside the DCF tab, the tab's value per
share or revenue / operating income differing from the Python math, the forecast years off MOD by more than 0.5%, an error
cell, or a reverse-DCF row that, typed into a copy of the tab and recalculated, doesn't give its price within $0.02.
A failure is a bug: stop and tell the user.

## 4. Replace
Only if `cmp -s "$MODEL" "$T/before.xlsx"` (the user didn't edit it meanwhile) and there is no `~$` lock file:
`cp "$T/after.xlsx" "$MODEL"` and `cp "$T/inputs_written.json" "$MW/"` (the record of what the build wrote,
saved only when the model is replaced so the two always match), then remove `$T`. Otherwise tell the user and rerun from step 2.

## 5. Look
`python3 -c "import sys; sys.path.insert(0,'$R/scripts'); import lo; print(lo.render_pdf('$MODEL', '$MW/preview'))"`
renders one PDF page per tab; the DCF tab sits right after DCF Cheat Sheet (count from 0). Render that page with
`lo.page_png` and look: yellow inputs, green links, black formulas, a grey reverse-DCF table, no `#` errors, nothing
cut off. Judge layout, not pixels. Remove `$MW/preview` after.
- The layout and formatting are the user's own (their hand edit of the DXCM tab, 2026-11-10): "<T> 30 yr DCF" title, terminal
  value in the valuation block, TTM EPS (last four reported quarters in MOD) above the forward EPS, blank rows between
  line groups, $ on the money lines, the boxed PV of FCF row, notes in cell comments rather than text rows.
  `test_layout_and_formatting_follow_the_users_edit` holds it. If the user reformats the tab again and asks for it to stick,
  rebuild the tab from the saved run on a copy, diff it against the user's tab cell by cell, and port the differences to build.py.

## 6. Deliver
Tell the user, in plain English (numbers from `$MW/solved.json` and `$MW/check_report.json`):
- value per share and the return from today's price
- the reverse DCF in words, per driver, e.g. "today's price needs <driver> growth N points a year higher in
  <the five years after the forecast> than yours, with your other inputs"; the same for the 3-year high and low;
  any "out of range" (a driver too small to reach the price)
- the terminal value's share of value (a common rule of thumb is under ~25%; say if it's over)
- which inputs were kept from their tab and which took the defaults
- the drivers and their long-run rates (from the forecast plan), and any `orphans` or `identity_fallback`
- which MOD rows were counted as debt (from context.json)
- the check: tab equals the Python math, the forecast years equal MOD, nothing outside the DCF tab changed, no errors
- how to use it: change any yellow cell and the tab recalculates live. The forecast years are links to MOD (change
  the forecast to change them); the yellow cells start the year after. The price follows the last close in Px Data. The
  grey reverse-DCF table is a snapshot: rerun /model-dcf to refresh it; a rerun keeps everything they typed.
