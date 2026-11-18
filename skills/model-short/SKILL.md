---
name: model-short
description: Add the Short Check tab to a company model (TICKER_model.xlsx) - a chapter 12 short check with a light verdict. An agent (short-analyst) answers the FEV scorecard (fundamentals, expectations, valuation; code ticks the rows numbers can answer: deceleration, incremental and peak margin, capex / D&A, acquisitions / CFO, FCF conversion, revisions, DCF, peer and own-history percentiles, the IRR wedge), names the short type and alpha bucket, the catalyst, the reward / dream / takeout cases and a verdict (alpha short / filler short / watchlist / no short) against a fixed rule. The tab shows the subpar-algorithm IRR wedge, the risk case and R/R, the print move, short interest and days to cover, borrow drag and VaR max position. Every judgment is a yellow cell the user owns; a rerun keeps the user's changes. Also writes a short note (Markdown + PDF). Works for any listed company. Run after /model-valuation. Use when the user runs /model-short TICKER or asks whether a stock is a short, for a short check, short interest, borrow or short sizing.
---

# /model-short

Adds one tab, **Short Check**, that answers: is there a short here, what kind, and how big could it be? It also
writes a short note. **Any company**: nothing here is specific to one stock. Use plain English, and tell the user
every judgment call. Read `NOTES.md` before changing scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

Yellow means the agent chose it and the user owns it. There is **no approval pause**: the agent decides, the code
checks every number, and the report tells the user every call. A rerun keeps any yellow cell the user changed, and
any ✓ / ✗ / ? (or formula) the user typed over a code tick.

## Requirements
- Python 3 with openpyxl; pytest to run the tests.
- Node, with this skill's `npm install` done once (yahoo-finance2; Step 2 does it if `node_modules` is missing).
- LibreOffice for the recalculations (`brew install --cask libreoffice`).
- WeasyPrint for the note's PDF (research-filings' `render.py`). Without it the note is Markdown only, and you say so.
- The model needs MOD with a forecast (16 quarters for the 3-year EPS CAGR; with fewer, the wedge shows `?`), Px Data
  and Multiples. Valuation,
  Consensus and Px Events are used when present; the checks that need them show `?` otherwise.

## Step 1: Locate and check
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). It prints
   JSON; `model` is the file. Set `M` to it and `W=<model dir>/_model_work/model-short` (`mkdir -p "$W"`). All
   working files stay in `$W`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. `shasum -a 256 "$M"`: keep it for Step 8. Never write to `M` before then; keep no backup copies.
4. A Short Check tab already there is normal (rerun each print). The build replaces it; the user's changes are kept.

## Step 2: Market data
```bash
(cd "$SK/.." && { [ -d node_modules ] || npm install --silent; }) && node "$SK/fetch_short.mjs" "$W" <T>
```
It writes `$W/short.json` (price, short % of float, days to cover, dividend yield). Exit 1 means Yahoo failed: carry
on; tell the user the price and short data will show n/a.

## Step 3: Context
`python3 -I "$SK/context.py" --model "$M" --work "$W" --ticker <T>`. It recalculates a copy of the model in
LibreOffice into `$W/values/` (a minute or two), then writes `$W/context.json`, `$W/context.md` and `$W/rowmap.md`.
It stops, naming the skill to run, when MOD, Px Data or Multiples is missing. It prints the price, the stale-price
check, the missing optional tabs and code's ticks. Tell the user: the stale-price flag (if set: the Valuation tab's
price is more than 3% from today's; rerun /model-valuation), the missing optional tabs, and code's ticks.

## Step 4: Borrow
Ask the user once: "What borrow rate does your prime broker quote for <T>? (Say 'don't know' and I'll show it at 5%
and 20%.)" Keep the number as `B` (a fraction: 3% = 0.03) or leave it unset; unset shows "check with PB".

## Step 5: Agent
Dispatch the `short-analyst` agent with the assignment `references/assignment.md` (the skill's folder) and the paths:
`W`, `$W/context.md`, `$W/context.json`, `$W/rowmap.md`, the research root `$RD/<T>/`, the brief
`references/short_brief.md` and the example plan `tests/fixtures/plan_example.json` (both in the skill's folder).
Wait for `PLAN WRITTEN`.

## Step 6: Check (at most 2 rounds back to the agent)
```bash
python3 -I "$SK/plan.py" --plan "$W/short_plan.json" --context "$W/context.json"
python3 -I "$SK/anchors.py" --plan "$W/short_plan.json" --values "$W/values/<model file name>" --research "$RD/<T>" --context "$W/context.json"
```
(`--values` is the recalculated copy Step 3 made; context.json's `values` holds its path.) Each prints one problem
per line (or `plan OK` / `anchors OK`) and exits 1 on any. Problems → SendMessage them all to the same agent; run
both again. After round 2:
- plan.py problems stop the run: show the user the problems in plain English and do not build. The model stays
  untouched.
- anchors.py problems: write the names still failing (the text before the first ":" of each problem, e.g.
  `reward_eps`, `ticks.pricing`, `smoke[0]`, `catalyst`) as a JSON list to `$W/unverified.json`; the build marks
  them UNVERIFIED in red and the note lists them. Otherwise make sure no old `$W/unverified.json` is left
  (`rm -f "$W/unverified.json"`).

## Step 7: Build and verify
```bash
python3 -I "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/out.xlsx"          # add --borrow B if known
python3 -I "$SK/verify.py" --out "$W/out.xlsx" --work "$W"
```
build.py never touches `M`, and stops if any part of the workbook other than the tab (and the workbook, styles and
content-type parts it must update) changed. It prints JSON; keep for the report: `verdict_rule` and `verdict_agent`,
`users_kept` (labels of the cells the user had changed, kept) and `warnings` (no inputs_written.json record, so every
differing yellow cell was treated as the user's; or a yellow cell that holds text where a number belongs).
verify.py recalculates the copy once in LibreOffice and compares every checked cell with `shortmath.py`; it prints
`{"problems": [...], "recalculated": ...}` and exits 1 on any problem. Any verify problem: stop, tell the user the
first problems in plain English, and do not copy. Never hand-edit the output.

## Step 8: Replace the model
1. `shasum -a 256 "$M"` again: if it changed, stop (the user saved meanwhile) and rerun from Step 3.
2. Check `~$<model file name>` again (ask the user to close Excel). Then
   `cp "$W/out.xlsx" "$M" && mv "$W/inputs_written.next.json" "$W/inputs_written.json"` (the record of what this
   build wrote, so the next rerun can tell the user's changes from the agent's).
3. Delete every copy of the model the run made (keep none): `rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`.
   Keep the plan, context, `layout.json`, `short.json` and `inputs_written.json`.

## Step 9: Note and report
`python3 -I "$SK/note.py" --work "$W" --ticker <T> --out-dir "$RD/<T>/Short Check"` (add `--date YYYY-MM-DD` for
another as-of date). It writes `<T> short check <date>.md` and `.pdf` in that folder and prints their paths; if
`"pdf"` is null, tell the user the PDF was skipped and why (`pdf_skipped`).

Then tell the user, in plain English:
- The verdict and the rule's verdict (`verdict_agent`, `verdict_rule`), and why they differ if they do.
- The short type and alpha bucket, the three dimension scores (F of 9, E of 4, V of 4) and which pass.
- The IRR wedge (hurdle minus the roll-forward IRR), the reward and the risk case (dream, roll-forward, takeout:
  the largest is the risk), R/R against 1.4x, and the print move.
- Max position (VaR budget ÷ risk) and its share of the short book; crowding (short % of float against the 10% line,
  days to cover); borrow and dividend drag (or "check with PB", with the 5% and 20% cases).
- Every judgment call with its reason: each tick the agent overrode or made, the reward / dream / takeout inputs and
  their anchors, the catalyst, takeout candidacy, smoke flags (and what was read), any house input changed.
- Every flag: stale price, Yahoo failure, missing optional tabs, UNVERIFIED names, the cells the user had changed
  (`users_kept`) and that they were kept, the build's `warnings`.
- That peak margin is TTM operating margin ÷ the 10-year FY peak (✓ at 95%), not a percentile (see NOTES.md).
- The note's path, that the Short Check tab sits after Valuation (last, when there is no Valuation tab), and a
  reminder to open the file in Excel, where it recalculates.
