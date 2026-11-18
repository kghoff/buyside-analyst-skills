---
name: model-price-history
description: Add the user's price-history tabs to a company model (TICKER_model.xlsx) - Px Data (daily closes, rolling beta, idiosyncratic return, point-in-time TTM fundamentals, month-end P/E on TTM EPS, annual FCF vs buybacks, weekly 3-factor alpha), Px Events (full-results release dates, TTM EPS and fundamentals linked to MOD, every earnings / preliminary-revenue / investor-event reaction with its idio move) and Idio Chart (price with TTM overlays, TTM P/E with TTM EPS, FCF vs buybacks with P/E, 3-factor alpha with overlays, Top-20 up/down idio days). Asks GAAP vs non-GAAP for the overlays and pauses for the user to download stooq price files. Run after /model-kpis and before /research-filings. Use when the user runs /model-price-history TICKER or asks for the idio chart / price history tabs.
---

# /model-price-history

Step 5 of the user's chain: `/collect-documents` → `/model-historicals` → `/model-ratios` → `/model-kpis` →
**`/model-price-history`** → `/research-filings` (which annotates the alpha chart). It rebuilds, for any ticker, the
house price-history tabs. Every number is an Excel formula they can click into; only
prices, dates and labels are typed (blue). **No annotations**: the "Your annotation" columns stay empty and no text
boxes go on the charts. That is /research-filings's job.

The scripts do the mechanical work and the checking. Your job is the judgment calls, and **telling the user about every
one**. Write plain English. `NOTES.md` explains the design; read it before changing scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

## Step 1: Locate

1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>`. If `"status": "build"`, tell the user
   to run the earlier skills first and stop. Set `M=<model>`, `SRC=<src>` (the /collect-documents folder),
   `W=<model_dir>/_model_work/price_history` (`mkdir -p "$W"`).
2. `python3 "$SK/modmap.py" --model "$M"`. It prints the MOD rows found by label. Check each `label` is the row
   the handoff means (income-statement revenue, not a segment total; FCF from the FREE CASH FLOW section). If a role
   is missing or wrong, add a pattern to `ROLES` in `modmap.py` and say so in the report. Never use row numbers.
3. If the model already has `Idio Chart`, `Px Events` or `Px Data`, **ask the user** before going on (AskUserQuestion).
   Rebuilding replaces all three tabs, **including any text boxes, arrows or notes they added there**. Name them.

## Step 2: Events

1. `python3 "$SK/events.py" --src "$SRC" --model "$M" --out "$W/events.json"`.
2. Work through every line of its `review` list and edit `$W/events.json` directly:
   - **"Other release"**: open the file. Keep it (give it a short `name`) if it is news an investor would trade on
     (guidance, M&A, management change, FDA decision). Delete it if it duplicates an investor event (e.g. a
     conference deck filed as an 8-K).
   - **Missing full-results date**: find it (a preliminary release's "will report ... on <date>", the 10-Q filing
     date, the call transcript's date). Add it to `full` and to `events`, with a `source` that says where it came
     from.
   - **Timing**: earnings default to "After close" (from the call time). If a release went out before the open,
     set "Same day". Preliminary releases default to "Same day"; check any that went out after the close.
3. Every MOD quarter that has actuals needs a `full` date. The build refuses otherwise.

## Step 3: Ask the user two things (one AskUserQuestion call)

**Overlay margin basis: GAAP or non-GAAP.** Always give a recommendation, first option, "(Recommended)":
- Recommend **non-GAAP** when management guides on a non-GAAP margin or EBITDA (check the latest release or
  deck), the adjustments are material (stock comp, amortization, litigation), or the long-range targets are
  non-GAAP. /model-kpis's section in MOD shows what the company reports.
- Recommend **GAAP** when there is no non-GAAP, the adjustments are small, or the industry convention is GAAP.
  Flag REITs (FFO) and banks.
- In the same question, or a second one: **add EBITDA margin as a 4th line?** Only if the company guides on
  EBITDA or the sector trades on EV/EBITDA.

Revenue growth and ROIC (`ROICasset TTM`, or `roic_ex_cash` if the user prefers) always go on. P/E always uses
non-GAAP EPS when MOD has it (the user's valuation default), whatever the overlay basis.

**Industry ETF.** Research it first (web): pick the narrowest liquid ETF for the company's GICS sub-industry.
Check its inception date (does it cover the warm-up?), AUM and liquidity (thin ETFs have stale prices), **the
stock's own weight** (high weight leaks its own news into the "industry" factor) and **its biggest competitor's
weight**. Prefer equal-weighted when 1–3 names dominate a cap-weighted fund. Offer the runner-up as the second option,
with the numbers. DXCM: XHE (equal-weight, 75 names, DXCM 1.65%) over IHI (cap-weight, Abbott 18%, DXCM 4.3%).

Write `$W/price_history.json`:
```json
{"ticker": "DXCM", "overlay_basis": "non-gaap", "ebitda": true, "roic_role": "roic", "fye_month": 12,
 "etf": "XHE", "etf_label": "medtech", "notes": ["why XHE over IHI, in one line", "..."]}
```
`fye_month` is the month the fiscal year ends, from `fiscalYearEnd` in the gather folder's `_manifest.json` ("0424" → 4).
The FCF chart's average P/E groups month-ends by fiscal year with it.
`etf_label` is a short lowercase word for the titles ("medtech", "semis", "regional banks").

## Step 4: The price files (required pause)

This pause is part of every run. Ask the user with AskUserQuestion to download these from stooq and **wait** (options
like "Downloaded them" / "Use a different ETF"). Name the exact files:

| File | Why | Link |
|---|---|---|
| `<t>_us_d.csv` | the stock | `https://stooq.com/q/d/?s=<t>.us&i=d` |
| `spy_us_d.csv` | market (dividend-adjusted, so total return) | `https://stooq.com/q/d/?s=spy.us&i=d` |
| `<etf>_us_d.csv` | industry factor | `https://stooq.com/q/d/?s=<etf>.us&i=d` |
| `mtum_us_d.csv` | momentum factor (MTUM − SPY) | `https://stooq.com/q/d/?s=mtum.us&i=d` |

History: from at least Dec 1 of (MOD's first fiscal year − 2) to today; the full download (stooq's default) is
fine. They can land in `~/Downloads` or the model's folder. Mention that MTUM only starts in April 2013: for a
model starting before 2015, the 3-factor chart starts later (or use Ken French's UMD factor; flag it).

Then: `python3 "$SK/prices.py" --model "$M" --src "$SRC" --stock <t> --etf <etf> --mom mtum --out "$W/prices.json"`.
It moves the files into `<model folder>/Price Data/` and deletes any other copies of them in Downloads, the model folder or the gather folder, so they exist only there afterwards (say which in the report). Exit 1 means a file is missing or broken: tell the user exactly
which and ask again. Read every `notes` line:
- a big move is a split only if no news explains it (look in Px Events / the releases); if it is a real split
  stooq missed, ask the user for a fresh download
- a factor that starts late pushes the 3-factor start back; say so
- a filled date list goes in the report

## Step 5: Build and verify

1. If `~$<model file name>` exists next to `$M`, the model is open in Excel. Ask the user to close it and wait.
2. Note `shasum "$M"` (no backup copy: The user doesn't keep old model versions; the build writes to `$W/built.xlsx`
   and the original stays untouched until step 6).
3. `python3 "$SK/build.py" --model "$M" --work "$W" --out "$W/built.xlsx"` (add `--replace` only after the user's yes
   in Step 1). Exit 3 means another tab has formulas pointing into the old tabs: show the user the cells and stop.
4. `python3 "$SK/verify.py" --before "$M" --built "$W/built.xlsx" --work "$W"`. It must say PASS:
   formula results = the prototype, no Excel errors, every other part of the workbook byte-identical. On FAIL, fix
   the cause (never hand-edit the output) and rebuild.
5. **Look at `$W/idio_chart.png`** (Read it). Check that all four charts have lines, the axes are sensible, and the
   Top-20 tables are filled. LibreOffice draws #N/A as 0; Excel shows a gap. Don't "fix" that.
6. Before writing, run `shasum "$M"` again. If it changed, the user edited the model meanwhile: **stop**, re-run from
   step 2 on the new file. Never overwrite their edits. Otherwise `cp "$W/built.xlsx" "$M"`, then confirm with
   `python3 -c "import openpyxl;print(openpyxl.load_workbook('$M',read_only=True).sheetnames)"`.

## Step 6: Report

The verify report stays in `$W/verify_report.md` (working files stay in `_model_work`). Delete `$W/built.xlsx`
   after copying it over the model. The final message, in plain English:
- what was built: the date range, index base, 3-factor start, the overlays and their basis, the fiscal years on the
  FCF chart, and the overlay axis range (computed from the data)
- the ETF and why, plus the alternative
- the price files used, any filled dates, stale days, big moves
- **every judgment call**: events added or removed, timings changed, missing dates found (and where), MOD labels
  matched by fallback patterns, the GAAP / non-GAAP answer
- the verification result, and a reminder to open the file in Excel, where it recalculates
- that the P/E is trailing (TTM), not forward; months with zero or negative TTM EPS have no P/E

## Judgment policy

- Decide, keep going, and **tell the user**. A call they never hear about is the worst outcome.
- Methodology is fixed (the user and the handoff, Nov 2026). Don't change it without asking:
  - β = 252-day slope through the prior day
  - point-in-time values switch the trading day after each release
  - P/E = close / TTM EPS as known that day (trailing; there is no free history of the consensus of the time)
  - monthly P/E, not daily; TTM EPS on the P/E chart, no average line
  - 3-factor LINEST on [SPY, ETF − SPY, MTUM − SPY], one regression per week, window ending at the prior week-end
- Never graph two versions of the same metric (e.g. GAAP and non-GAAP P/E).
