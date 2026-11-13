---
name: model-industry
description: Add Industry P&L and Industry Comparison tabs to a company model (TICKER_model.xlsx) - a condensed 10-year industry income statement, balance sheet and cash flow summed from the public players (division players' segment figures from their 10-K segment notes, the rest estimated from the parent by revenue share), plus six charts (industry revenue and growth, market share, share of new dollars, margins, ROIC, capital cycle) and a peer table. Optional; runs after the model is built, analyzed and researched. Ballpark accuracy, fast. Use when the user runs /model-industry TICKER or asks for an industry P&L or industry comparison.
---

# /model-industry

Optional step in the model chain, after `/model-historicals`, `/model-ratios`, `/model-kpis` and usually
`/research-filings`. Adds two tabs: **Industry P&L** and **Industry Comparison**. **Ballpark is the standard**
(house default): not every player is public and division players need estimates. Aim for minutes, not an hour.
Write plain English, and tell the user every judgment call.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

## Requirements
- Node 18+ and Python 3 with openpyxl; LibreOffice for verify's recalculation and render.
- The separate edgar-xbrl-financials tool, which supplies the peers' XBRL figures: clone
  github.com/kghoff/edgar-xbrl-financials, install its packages, and set `xbrl_cli` in the settings file to its
  `bin/cli.js` (default `~/Desktop/edgar-xbrl-financials/bin/cli.js`). Step 4 stops with this instruction if the
  file is missing.

## Step 1: Locate

1. Model: `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>`. If it says `"build"`,
   look for `$RD/<T>/*model*.xlsx`; if the user named a path, use it. Set `M`, `W=<model dir>/_model_work/industry_pnl`
   (`mkdir -p "$W"`), `R="$RD/<T>"`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. If the model already has `Industry P&L` or `Industry Comparison`, ask the user before rebuilding (it replaces both
   tabs, including anything they added there).

## Step 2: Find the peers (read little)

Always look in `$RD` before the web, and read Markdown, not PDFs.
1. Street research report (`$R/Street Research/*.md`, if it exists): only its industry / competition sections. Find them
   with `grep -n "^#" <file>` and read just those line ranges.
2. Filings research report (`$R/Filings Research/*Filings Research Report.md`): same, industry / competition sections only.
3. The subject's latest 10-K Item 1 "Competition" paragraph.
4. One or two web searches for public players the documents don't name ("<industry> market share companies").

For each candidate decide: SEC filer (10-K / 20-F) or not; whole company or which reported segment; whether the
segment is broader than the industry (say so in `caveat`); whether `$RD/<PEER>/*model*.xlsx`
exists (then `"source": "model"`, its consolidated lines are read from it). Private companies, non-SEC filers and
inseparable divisions go in `excluded` with the reason.

## Step 3: Pause: the user confirms the peers

One AskUserQuestion: a table (company, include?, whole company or segment, why) and your recommended set as the
first option "(Recommended)". Then write `$W/peers.json`. **The subject comes first.**

```json
{"subject": "DXCM", "industry": "CGM",
 "companies": [
  {"ticker": "DXCM", "name": "DexCom", "source": "mod"},
  {"ticker": "ABT", "name": "Abbott", "source": "xbrl", "segment": "Diabetes Care",
   "caveat": "segment also includes blood-glucose meters and test strips"},
  {"ticker": "MDT", "name": "Medtronic", "source": "model", "model": "<research_dir>/MDT/MDT_model.xlsx",
   "segment": "Diabetes", "caveat": "segment includes insulin pumps"},
  {"ticker": "SENS", "name": "Senseonics", "source": "xbrl"}],
 "excluded": [{"name": "Roche Diabetes Care", "why": "Swiss, not an SEC filer"}],
 "notes": ["every judgment call, plain English"]}
```
`segment` = the name exactly as the 10-K's segment note prints it. A foreign filer reporting in another currency
also gets `"fx": {"2025": 1.08, ...}` (USD per unit, the year's average rate: from the filing if printed, else the
Fed's H.10 series) and `"fx_source"`.

## Step 4: Fetch

`python3 "$SK/fetch.py" --work "$W" --model "$M"`. It caches; reruns fetch only what's missing. Peer files go in
`<model dir>/Industry P&L/peers/<PEER>/`.

## Step 5: Segment figures (segment peers only)

1. For each: `python3 "$SK/segments.py" cut --work "$W" --ticker <PEER> --segment "<segment>"`. Exit 1 = no table
   mentions the segment: check the name in the 10-K and rerun.
2. Dispatch ONE `general-purpose` agent with `model: sonnet` for all segment peers, with this prompt:

> For each company below, type the reported figures for one segment from its 10-K segment note, for every fiscal
> year available (10 years). Evidence: `{W}/snippets/<TICKER>.md` (each table line starts with `L<line number>:`
> and the file path is the `##` heading above it). Open the file itself when you need more context (column headers,
> units).
> Companies: {TICKER: segment name, ...}
> Lines wanted, where the note prints them: revenue (segment net sales), oi (segment operating profit / earnings),
> da (segment depreciation and amortization), capex (segment capital expenditures / additions to PP&E),
> total_assets (segment assets), and, where the note lists them, cogs, rd, sga.
> Write `{W}/values/<TICKER>.json`, a list: `{"line": "revenue", "fy": 2025, "value": 7624, "raw": "7,624",
> "scale": 1, "file": "<full path of the 10-K .md>", "line_no": 412, "note": "..."}`.
> - `fy` is the company's own fiscal year (the column header). `value` in $ millions: if the table is in
>   thousands, `scale` 0.001; billions, 1000.
> - `raw` is the number exactly as printed on line `line_no`. A code check rejects anything not printed there.
> - Only printed numbers: never add, subtract or estimate. If a year appears in several 10-Ks, list each.
> - Finish with: lines and years filled per company, and anything odd (segment renamed, redefined, units changed).
3. `python3 "$SK/segments.py" check --work "$W"`. Send rejected values back to the reader once with the reasons;
   whatever is still rejected stays out. List conflicts (the newest 10-K wins) in the report.

## Step 6: Assemble

`python3 "$SK/assemble.py" --work "$W" --model "$M"`. Read every `warnings` line, and act on each:
- segment bigger than the parent, or share jumping more than 15 points: likely a redefinition; say so in the report
  and in `caveat`.
- a gross margin below -100% or revenue moving more than 3x in a year ("check against the 10-K"), or a figure that
  otherwise looks wrong: open that year's 10-K income statement. If the XBRL figure is wrong, add an override with
  its source to the company in `peers.json`, keyed by the company's own fiscal year, in $M as reported, then rerun:
  `"overrides": {"revenue": {"2022": {"v": 16.4, "note": "SENS 2022 10-K income statement"}}}`.
- input lines missing where revenue exists: that company drops out of those lines' industry totals that year; say
  so in the report (or override the figure from the 10-K if it matters).

## Step 7: Build and verify

1. `shasum "$M"`.
2. `python3 "$SK/build.py" --model "$M" --work "$W" --out "$W/built.xlsx"` (`--replace` only after the user's yes).
   Exit 3: another tab points into the old tabs; show the user and stop.
3. `python3 "$SK/verify.py" --before "$M" --built "$W/built.xlsx" --work "$W"` (with or without `--replace`: the
   old tabs' parts are allowed to change). It must say PASS. On FAIL, fix the cause and rebuild; never hand-edit
   the output.
4. **Look at `$W/industry_comparison.png`** (Read it): six charts with data, sensible axes, the peer table filled.
   LibreOffice draws #N/A as 0; Excel leaves a gap.
5. `shasum "$M"` again. If it changed, the user edited the model: stop and rebuild from step 2. Otherwise
   `cp "$W/built.xlsx" "$M"`; delete `$W/built.xlsx`, `$W/_recalc` and `$W/_render` (they hold copies of the
   model; keep no old model versions).

## Step 8: Report (plain English)

- the peer set and why; excluded players and why
- each company's source, its fiscal-year mapping (e.g. "Medtronic's year ending April 2025 counts as 2024"), and
  any segment broader than the industry
- how many cells were estimated per company, and what that means (parent × revenue share)
- rejected or conflicting segment values; assemble warnings
- what the charts show at a glance (industry growth, the subject's share and share of new dollars, margins vs the
  industry, the capital-cycle reading), stated as observations, not conclusions
- the verify result, and a reminder to open the file in Excel, where it recalculates

## Judgment policy

- Decide, keep going, and tell the user. A call they never hear about is the worst outcome.
- Fixed (house defaults): annual, 10 calendar years, history only; division players = disclosed segment lines +
  parent × revenue share for the rest; subject linked to MOD; ROIC on the condensed lines (approximation of the
  invested-capital definition in `/model-ratios`), the same for every company so they compare.
- Never invent a segment split. Never use the full /collect-documents on peers.
