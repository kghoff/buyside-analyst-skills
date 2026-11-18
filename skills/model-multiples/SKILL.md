---
name: model-multiples
description: Add the Multiples tab to a company model (TICKER_model.xlsx) - where the stock trades against its own history, the S&P 500 and its peers. Weekly history of P/E, EV/EBITDA, EV/GP, EV/Revenue and FCF yield with charts; P/E minus the S&P 500 and minus the core-peer median; a ranges table (1 / 5 / 10-year min, median, max, percentile) with the reverse P/E (the earnings power today's price implies); a forward table (today's price on each forecast year, with the Street's); a ranked comp sheet with an Include? toggle per peer, a scatter of next-year P/E against revenue growth with a line through the peers (below it = structurally underpriced on the multiple), and the subject's P/E against the core-peer median over time. Free path - trailing multiples from the model, Yahoo daily prices for 3-5 core peers (stooq only as a fallback), multpl.com for the S&P, Yahoo for comps - or paid path from FactSet / Bloomberg / CapIQ / Koyfin exports. Also writes the valuation brief that model-valuation reuses. Works for any listed company. Run after /model-forecast; rerun weekly or each print. Use when the user runs /model-multiples TICKER or asks for multiples, a comp sheet, P/E history charts or relative valuation.
---

# /model-multiples

Adds one tab, **Multiples**, that answers three questions: where has the stock traded (on its own and against the
market), where does it trade against its peers, and what does today's price imply. **Any company**: nothing here is
specific to one stock. Use plain English, and tell the user every judgment call. Read `NOTES.md` before changing scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

## Requirements
- Node 18+, with the skill's packages installed once: `npm install --prefix "$SKILLS/model-multiples"`.
- Python 3 with openpyxl, PyMuPDF (`fitz`) and Pillow; pytest to run the tests.
- LibreOffice for verify's recalculation and picture (`brew install --cask libreoffice`).

## Step 1: Locate and check
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). Set `M` to the
   model and `W=<model dir>/_model_work/model-multiples` (`mkdir -p "$W"`). All working files stay in `$W`.
2. The model needs MOD with forecast years, Px Data and Px Events. No Px Data: stop and say to run
   /model-price-history first.
3. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
4. `shasum -a 256 "$M"`: keep it for Step 7. Never write to `M` before then; keep no backup copies.
5. A Multiples tab already there is normal (rerun each print). The build replaces it and appends the new one as the
   last tab; tell the user to move it back once if they want it elsewhere.

## Step 2: Data mode
If `$W/mode.json` exists, use it. Otherwise ask with AskUserQuestion: "Do you have FactSet, Bloomberg, CapIQ or
Koyfin exports?" Options: "No: free data (Recommended unless you have a terminal)" / "Yes: I'll drop exports in".
Write `{"mode": "free"}` or `{"mode": "paid"}`. The paid path takes exported files only, never logins (a judgment
call: tell the user).

## Step 3: The valuation brief
`python3 "$SK/brief.py" --ticker <T> --out "$W/valuation_brief.md"` (add `--research-dir "$RD"` if the research
folder is not the setting's). The brief cuts the valuation-relevant sections of the newest filings and Street
research under a 15,000-word cap, split fairly across the sections: summary, key drivers, stock-vs-drivers and the
Street executive summary count double, the rest once. Read its industry and key-driver sections, not the whole
thing. Tell the user which sections the summary lists as cut or missing.

## Step 4: Pause: confirm the comps
If `$W/comps.json` exists, show it and ask whether to keep it. Otherwise propose 8-16 comps grouped by why they are
comparable (same end market, same business model, same growth / margin profile). Use model-industry's peers
(`<model dir>/Industry P&L/peers/`) only as a starting point: the comp sheet asks how the market prices businesses
*like* this one, which is wider than the industry. Also propose 3-5 core peers from that list (the closest
comparables, used for the P/E-vs-peers history). Ask with AskUserQuestion (first option "(Recommended)"). Write
`$W/comps.json`:
`{"subject": "<T>", "comps": [{"ticker", "group", "why"}], "core": ["<T1>", ...], "files": {}}`.

## Step 5: Data
**Free path**
1. `node "$SK/fetch_comps.mjs" "$W" <T> <every comp>`. Exit 1 = the subject failed (Yahoo returned no price or
   market cap): wait a few minutes and rerun once. If it fails again, stop and tell the user Yahoo has no data now;
   offer the paid path, or trying later. No endless retries. A failed comp stays on the sheet with its error. Soft warnings
   (missing currency or debt) keep the numbers; a currency different from the subject's blanks that comp's EV
   multiples. The ADV column is shares traded, in millions, not dollars.
2. `python3 "$SK/sp500.py" --work "$W"`.
3. Core peers' fundamentals: for each core peer use `<model dir>/Industry P&L/peers/<P>/xbrl.json` if it exists,
   else `mkdir -p "$W/xbrl"` and `node "$XBRL" <P> --json > "$W/xbrl/<P>.json"`, where
   `XBRL=$(python3 -c "import sys; sys.path.insert(0, '$SK/../../../lib'); import settings; print(settings.xbrl_cli())")`
   (stop with model-industry's message if it is not installed).
4. Core peers' prices: `(cd "$SK/.." && { [ -d node_modules ] || npm install --silent; }) && node "$SK/fetch_prices.mjs" "<model dir>/Price Data" <core peers>`.
   It writes `<p>_us_d.csv` per peer (Yahoo: Close = traded price, used for P/E). Exit 1 = Yahoo failed for a peer:
   only then ask the user (AskUserQuestion) to download `https://stooq.com/q/d/?s=<p>.us&i=d` for the failed peers
   into `<model dir>/Price Data/` and **wait**. Tell them stooq's prices are dividend-adjusted, so those peers'
   historical P/E runs low if they pay dividends. Then
   `python3 "$SK/prices.py" --model "$M" --tickers <core peers> [--src DIR]`. It copies the files it finds into
   `<model dir>/Price Data/`, prints JSON, and exits 1 if any is missing or bad: ask the user for those once. If they can't supply one, drop that peer from `core`
   in `comps.json` (it stays on the comp sheet) and tell them. With one core peer left, "P/E − core-peer
   median" is against that single peer; with none, it is #N/A throughout. Say which.
5. Fill `comps.json` `files`: `{"<P>": {"xbrl": "<path>", "prices": "<path>"}}`.

**Paid path.** Ask the user to drop one export for the subject and one per core peer into `$W/inputs/`, daily or
weekly, with date, price and NTM EPS at least (plus EV, market cap, NTM sales / GP / EBITDA / FCF, LTM FCF and the
S&P 500 NTM P/E where they have them). Fill `files`: `{"<T>": {"export": "<path>"}}` for the subject and each core
peer. One file holding several tickers is fine: the build picks each ticker's rows. Semicolon files with decimal
commas are read. Comps still come from Yahoo (free-path step 1).
- Headers are recognised by the usual vendor names. If the build stops with "write mapping.json" (a header it does
  not know, two columns that both look like one field, or a comma it cannot tell is a decimal or a thousands mark),
  read the file's header row, propose `{field: header}` for the fields at issue, show the user, and write
  `$W/inputs/mapping.json` as `{"<export file name>": {"date": "<header>", "price": "<header>", "eps_ntm": "<header>",
  ...}}`. Rerun the build. Fields: date, ticker, price, eps_ntm, sales_ntm, gp_ntm, ebitda_ntm, fcf_ltm, fcf_ntm,
  mcap, ev, sp500_pe.
- The build reports rows it skipped (no readable date). Pass them on.

## Step 6: Build and verify
1. `python3 "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/out.xlsx"`. It never touches `M`. Keep the
   printed summary for the report: it lists dropped weeks, skipped charts, comp warnings, quarter notes (for example
   the EBITDA fallback) and dangling names. It stops with a clear message if MOD lacks a quarter column the history
   needs, or the overlays are non-GAAP and MOD has no non-GAAP EPS row: fix the model (or tell the user) and rerun.
   Paid path: it also stops when the export's units are not MOD's (it names the likely unit, e.g. dollars): ask the
   user to re-export in millions.
2. `python3 "$SK/verify.py" --model "$M" --out "$W/out.xlsx" --work "$W"`. It must print `"ok": true`. It
   recalculates in LibreOffice, compares every checked cell, scans for errors and proves every other part of the file
   is byte-identical. On failure, fix an obvious cause and rebuild once; never hand-edit the output.
   If it still fails, stop and do not copy over: show the user the first failed cells and errors in plain English.
   The model stays untouched.
3. Look at the PNG of the Multiples page it names (`$W/multiples.png`): charts drawn, no `#` errors except #N/A where
   a multiple is not meaningful, comp sheet filled.

## Step 7: Copy over
1. `shasum -a 256 "$M"` again. Changed since Step 1 = the user edited the model meanwhile: stop and rebuild from
   Step 6. If `~$<model file name>` exists, ask the user to close Excel and wait.
2. Unchanged: `cp "$W/out.xlsx" "$M"`. Then delete every copy of the model the run made (no backup copies): `$W/out.xlsx`, `$W/values/` (build's
   recalculated copy) and `$W/verify/` (verify's recalculation and PDF). Keep `$W/multiples.png`, `layout.json` and
   the data caches (`comps/`, `sp500.json`, `xbrl/`).

## Step 8: Report (plain English)
- Where the stock trades today: P/E and EV/EBITDA against their 5-year median and percentile; against the S&P 500
  and the core peers; the reverse P/E (the earnings power today's price implies if the stock traded at its 5-year low, median or high
  P/E; one plain sentence saying so the first time it appears).
- The comp sheet: where the subject ranks, the cheapest and most expensive comps, anything the scatter shows as off
  the line.
- The line through the peers (summary `line`): how many peers are on it, the P/E it gives at the subject's growth, the
  gap in turns, the growth the subject's P/E implies, and the reading (below the line = structurally underpriced on
  the multiple; under 3 peers or a line that doesn't slope up = no reading).
- The Include? toggles (column T of the comp sheet, yellow, 1 by default): any peer flagged at over 2x the peers'
  median P/E, any peer the user has left out (summary `left_out`, kept from their edit), and that flipping a cell to 0
  takes the peer out of the averages, medians, the line, the scatter and (for a core peer) the weekly peer median when
  Excel recalculates.
- The new chart of the subject's P/E against the core-peer median (TTM GAAP on the free path, NTM on the paid).
- Every judgment call:
  - free history is TTM, not NTM: for fast growers TTM P/E runs above NTM; the paid path is NTM and adds the NTM FCF
    yield;
  - the S&P comparison is trailing (free path);
  - Relative rows are GAAP vs GAAP: the S&P and XBRL peer figures are reported earnings (free path; on a non-GAAP
    basis the tab adds a GAAP P/E column for them). The paid path stays NTM vs NTM;
  - core peers count a quarter as known 45 days after quarter end (Q1-Q3) or 90 days (Q4), the latest SEC filing
    deadlines, so never early;
  - net debt = debt-like liabilities less cash and short-term investments; operating leases excluded;
  - EBITDA is Adjusted EBITDA on a non-GAAP basis, else operating income + D&A (the build notes when it fell back);
  - the scatter and its line use reported, not organic, revenue growth (Yahoo's next year vs this year);
  - the comp list is wider than the industry players;
  - the paid path took exported files only.
- The build summary's warnings (dropped weeks, skipped charts, failed comps, currency mismatches, missing S&P column,
  skipped export rows, dangling names).
- That the Multiples tab is now the last tab, and a reminder to open the file in Excel, where it recalculates.
