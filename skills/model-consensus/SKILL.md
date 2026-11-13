---
name: model-consensus
description: Add the Consensus tab to a company model (TICKER_model.xlsx) - every covering sell-side broker's rating, price target and last action (free Yahoo data), each broker's own EPS and revenue estimates for next quarter / this year / next year where its report is in Sellside Research (typed by a reader, every number checked against its line), consensus mean / high / low with P/E on the Street high and low, a 5-year rating-history chart (price, average target, upgrades and downgrades) and log, dated consensus snapshots that build a revision history over reruns, and an empty variance-table skeleton the user fills in themselves. Works for any listed company. Run after /research-street; rerun after each earnings print. Use when the user runs /model-consensus TICKER or asks for consensus, analyst ratings, price targets or rating history.
---

# /model-consensus

The first step in assessing expectations: what the sell side expects, and how that moved.
**Any company**: nothing here is specific to one stock. Use plain English, and tell the user every
judgment call.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

## Requirements
- Node 18+, with the skill's packages installed once: `npm install --prefix "$SKILLS/model-consensus"`.
- Python 3 with openpyxl, PyMuPDF (`fitz`) and Pillow; pytest to run the skill's tests.
- LibreOffice for verify's recalculation and render (`brew install --cask libreoffice`).

## Step 1: Locate
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). Set `M`,
   `W=<model dir>/_model_work/consensus` (`mkdir -p "$W"`), `SS="$RD/<T>/Sellside Research"`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. If the model has no Px Data tab, say the chart will be skipped (run /model-price-history first) and carry on.
4. A Consensus tab already there is normal: this skill is rerun after each print. It rebuilds the tab and keeps
   everything the user typed in the variance table. Say so in the report, don't ask.

## Step 2: Fetch
`node "$SK/fetch.mjs" <T> "$W"` (first time: `npm install --prefix "$SKILLS/model-consensus"`). Exit 1 =
Yahoo failed after retries (wait a few minutes and rerun) or Yahoo has no data at all for the ticker (the message
says "check the ticker"); never build from a partial fetch. Nasdaq errors are fine. Share-class tickers are typed
with a dot (BRK.B); the script asks Yahoo for BRK-B itself. Keep the `file` path it prints as `SNAP`.

## Step 3: Firms and rating words
`python3 "$SK/firms.py" check --snapshot "$SNAP"` (the `file` fetch.mjs printed). For each unknown firm: decide its type
(`bank` / `independent` / `specialist` = analysts in the table; `rating shop` / `quant` = the separate box; `other` =
non-research contributors such as a "Company Forecast" entry, kept out entirely; look it up if unsure) and add it to `$SK/firms.json` with its spellings as aliases. Unknown rating words go into the right bucket
(Buy / Hold / Sell, or Unrated for Not Rated, Suspended and the like, by what the firm's scale means). Rerun until exit 0. Tell the user every addition.

## Step 4: Broker estimates (skip if Sellside Research has no broker reports)
1. `python3 "$SK/estimates.py" cut --work "$W" --sellside "$SS"`. It names the covering brokers with a report, and
   the rating shops. Covering brokers are firms with a Yahoo action in the last 12 months plus analyst firms Nasdaq
   lists as covering; the Nasdaq-only ones get a broker-table row with rating and target blank and a note, and their
   reports are read for estimates too (a broker's report filed under Independent Research is read as well). It
   prints each label's period end date (`periods`) and any `warnings` (unreadable periods: report them). It also
   prints a "skipped" list (covering firms whose reports have no
   estimates table, report files whose names don't parse, files of unknown firms): report it to the user.
2. Dispatch ONE `general-purpose` agent with `model: sonnet`:

> Type each firm's own figures from its research report for {COMPANY} ({TICKER}). Evidence: `{W}/snippets/<slug>.md`
> (the file path is the `##` heading; each line starts `L<line number>:`). Open the file itself when you need the
> column headers or units. Firms: {FIRM: snippet path, ...}. Period labels (company fiscal calendar) and the date
> each period ends: next quarter {Q} (ends {Q end}), this year {FY} (ends {FY end}), next year {FY1} (ends {FY1 end})
> (from `periods` in `{W}/estimates_plan.json`).
> For broker firms: `eps` (adjusted / non-GAAP EPS if the table shows both; say which in `basis`) and `revenue` for
> those three periods only. For rating shops: `rating` (the rating or score as printed) and `target` (price target
> or fair value), with `period` null.
> Write `{W}/values/<slug>.json`, a list: `{"metric": "eps", "period": "FY 27", "period_end": "2027-12",
> "value": 3.20, "raw": "3.20", "scale": 1, "file": "<full path of the .md>", "line_no": 110, "basis": "non-GAAP",
> "note": "..."}`.
> - Map the table's columns ("2027E", "4Q26E", "FY27") to the labels above by the month each period ENDS, not by
>   its name: a broker's "FY27" may end in a different calendar year than our label. Give each eps / revenue value
>   `period_end` ("YYYY-MM", the end month the report states or implies for that column). A code check rejects a
>   value whose period_end is more than a month from the label's end date.
> - `value` in millions in the reporting currency for revenue (thousands: scale 0.001; billions: 1000); EPS as
>   printed. In `note`, say the currency if it isn't US dollars, and for a company with ADRs whether EPS is per ADR
>   or per ordinary share.
> - `raw` is the number exactly as printed on line `line_no`. A code check rejects anything else.
> - Only printed numbers. Never compute, average or estimate. Skip what isn't there.
> - Finish with: per firm, what you filled, and anything odd (fiscal year not stated, two EPS bases, old report,
>   EPS per ADR vs per share, currency).
3. `python3 "$SK/estimates.py" check --work "$W"`. Send rejected values back to the same reader once with the
   reasons; whatever is still rejected stays out (report it).
4. `python3 "$SK/estimates.py" choose --work "$W"`.

## Step 5: Build and verify
1. `shasum "$M"`.
2. `python3 "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/built.xlsx"`. Exit 3: another tab, a defined
   name, a chart, pivot or table points into the old Consensus tab; show the user what it lists and stop. Keep the printed summary for the report.
3. `python3 "$SK/verify.py" --before "$M" --built "$W/built.xlsx" --work "$W"`. Must say PASS. On FAIL fix the cause
   and rebuild; never hand-edit the output.
4. Read `$W/consensus_top.png` (the top section; `consensus.png` is the whole tab and very tall because the chart's
   helper data runs about 1,250 rows in columns R-V, so don't Read it): broker table filled, consensus rows, empty yellow variance skeleton, chart lines, log and
   snapshots.
5. `shasum "$M"` again. Changed = the user edited it: stop and rebuild from step 2. If `~$<model file name>` exists next
   to `M` (Excel has it open), ask the user to close Excel and wait. Otherwise `cp "$W/built.xlsx" "$M"`,
   then delete `$W/built.xlsx`, `$W/_recalc` and `$W/_render` (keep no old model versions).

## Step 6: Report (plain English)
- the covering brokers (Yahoo actions plus Nasdaq-only): count, Buy / Hold / Sell, mean and range of targets vs the price
- the "skipped" list from estimates.py cut
- whose estimates came from reports (and report dates), which are stale; rejected values
- firms or rating words added to firms.json; firms that may have dropped coverage; unclassified firms
- what changed since the last snapshot (the build summary's `changes`): consensus moves by period, rating changes
- warnings (no Px Data, period labels, no consensus, price and estimates in different currencies)
- the verify result, and a reminder to open the file in Excel, where it recalculates
- that the variance table is the user's to fill (consensus vs their numbers); their entries survive reruns

## Judgment policy
- Decide, keep going, and tell the user. A call they never hear about is the worst outcome.
- Fixed (house defaults): banks and independent research firms only in the broker table; 5 years of history;
  estimates are EPS and revenue for next quarter, this year and next year; the variance table is a skeleton only
  (never fill it, never link it to MOD).
- Plain English always. Never run on the user's live model without the shasum guard (Step 5). Keep no old model versions.
  Working files stay in `_model_work/consensus`.
- The snapshot block's Buy / Hold / Sell counts (Yahoo recommendation trend, all contributors) differ from the broker
  table's counts (firms with an action in 12 months). If the user sees both, explain it in the report.
- The chart PNG shows a red row of markers along the axis: LibreOffice draws #N/A as 0; Excel leaves gaps. Not a bug,
  don't "fix" it.
- Never type an estimate that isn't printed in a report. Blank is the honest answer for brokers without one.
