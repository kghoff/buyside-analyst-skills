# /model-consensus: notes

## Data sources (tested 2026-11-12)
- Yahoo via `yahoo-finance2` (quoteSummary `upgradeDowngradeHistory`, `earningsTrend`, `recommendationTrend`,
  `financialData`, `price`; `chart` for splits). The raw `query1/2.finance.yahoo.com` crumb route was rate-limited
  ("Too Many Requests"); the library route worked. Rating history goes back about 14 years with prior/current targets.
- Nasdaq `api.nasdaq.com/api/analyst/<T>/earnings-forecast` and `/ratings` (Zacks data): more periods (EPS only) and
  the covering-broker list. Optional.
- Not used: Finviz (empty page to scripts), Google Finance (no API; paid scrapers only).
- Each broker's own estimates have no free source (FactSet, LSEG I/B/E/S, Visible Alpha are paid). They come only from
  reports the user drops into Sellside Research. The broker table's columns line up so a paid feed could fill them later.

## Decisions
- Covering = a Yahoo rating action in the last 12 months, plus analyst firms Nasdaq lists as covering (ratings.nasdaq_covering). Nasdaq-only firms get a broker-table row with rating/target blank and a note, and their reports are read for estimates.
- Firm types: bank / independent / specialist (analysts), rating shop / quant (separate box), other (non-research contributors such as "Company Forecast", kept out entirely). Rating buckets: Buy / Hold / Sell / Unrated (Not Rated, Suspended...).
- Post-split targets: Yahoo sometimes leaves the old target in pre-split dollars on a firm's first action after a split; ratings.py detects and fixes that. Yahoo "Adjusts" actions are labelled Maintains.
- Snapshot block Buy/Hold/Sell counts (Yahoo recommendation trend, all contributors) differ from the broker table's counts (firms with an action in 12 months); explain in the report if the user sees both.
- Chart: LibreOffice draws #N/A marker values as 0 (red row along the axis in the PNG); Excel leaves gaps. Not a bug.
- verify.py writes consensus.png (whole tab, very tall) and consensus_top.png (top section; read this one).
- Stale estimate = report more than 3 days older than the firm's
  last action, or 90+ days old. build.py recomputes it from the current snapshot on every build (estimates.is_stale),
  ignoring the flag stored in estimates.json, so a rerun weeks later greys out reports that have aged.
- Period mapping: estimates.py cut writes each label's period end date (Yahoo endDate for 0q / 0y / +1y) into
  estimates_plan.json "periods"; the reader maps a broker's columns by end month and gives each eps / revenue value
  a `period_end` ("YYYY-MM"); check rejects one more than 1 month off the label's end, and notes "period end not
  stated" when it is missing (accepted).
- Currency: revenue headers use the reporting currency (Yahoo financialData.financialCurrency), "($M)" only for USD.
  When it differs from the price currency (ADRs such as TSM, SAP) the P/E rows are left blank with a note, the price
  label says so and the summary warns. Upside is kept: Yahoo targets are in the price currency.
- Share-class tickers: Yahoo wants BRK-B (BRK.B returns an empty object, no error), Nasdaq wants BRK.B. fetch.mjs maps
  X.Y to X-Y for Yahoo only; foreign suffixes (SAP.DE) are untouched. No price, history or trend = exit 1, nothing
  written.
- verify.py reads the built tab itself: every typed number (number or date, not a formula) needs a note unless its
  block has a header note (layout.json "header_noted", written by build.py: row numbers, average-target helper, log,
  snapshots); typed numbers must be blue (stale broker estimates grey, layout.json "stale"), formulas never blue.
  The user's variance block (layout.json "user") is skipped.
- Dates are New York trading days (Yahoo stamps UTC).
- Targets before a split are divided by the split ratio (Px Data closes are split-adjusted).
- Average-target line: per day, mean of each covering analyst's latest target, typed (a formula for "latest target
  per firm as of each day" would be unreadable); a header note says how.
- Downgrade markers are red diamonds: Excel has no downward triangle.
- Variance table: the user's labels and inputs (columns B-H) are read from the old tab and written back; the variance
  formulas (I-K) are regenerated unless the user typed over one (a value, or a formula other than the skill's): then their
  cell is kept and named in the warnings. Same-sheet references inside the block move with it. A rerun puts the tab
  back at the position the user gave it.

## Limitations
- Fiscal year labels come from Yahoo's year-end month (the month of the "0y" period end; periods.fye_month), not from
  the MOD tab's end dates (the spec's "MOD end dates within 7 days" was not built). A year is named by the calendar
  year it ends in (a year ending Feb 2025 = FY 25; a 52/53-week year ending in a month's first week counts as the
  month before). Some retailers name it the prior year; build.py warns when the next-quarter label isn't a MOD
  column label, which is the only cross-check against the model.
- Yahoo's history covers the firms Yahoo's feed tracks; a covering broker missing there shows up only in Nasdaq's
  broker list (reported, not in the table).
- Rating shops are rarely in Yahoo; the box fills from the user's tier-2 reports.
- Consensus history starts with the first run; earlier revisions are not recoverable from free sources.

## DXCM baseline (2026-11-12, end-to-end on a copy of the DXCM model)
- 20 analyst firms with a Yahoo action in 12 months + 7 listed only by Nasdaq (Baird, Jefferies, Leerink Partners,
  Oppenheimer, Raymond James, William Blair, Wolfe Research); 18 Buy / 2 Hold / 0 Sell; average PT $92.00 vs Yahoo
  mean $98.58; price $81.25.
- Broker estimates from reports: J.P. Morgan (2026-10-29: Q4 26, FY 26, FY 27 EPS and revenue), BofA (2026-10-30:
  FY 26, FY 27). William Blair's only report (2025-10-17 deep dive) has no EPS/revenue table. 19 values typed, 0
  rejected. Rating-shop box: Argus, CFRA, Morningstar, LSEG StarMine, Schwab, SmartConsensus.
- 188 rating actions in the 5-year log; verify PASS, 5,433 formula cells; rerun kept typed variance inputs.
- MDT (April year-end) on a copy: labels Q2 27 / FY 27 / FY 28, 21 analysts + 5 Nasdaq-only, verify PASS.

## Formatting (house style, from hand edits on the DXCM tab, now built in)
- "Price:" (bold) sits in E3, right next to the price in F3; any currency caveat goes in G3.
- The broker table's column headers (Type .. Estimates from) are repeated in a blue header row right above the
  consensus rows (A and B blank, 32 pt tall).
- Header rows sized for their wrapped text: rating-shop box 34, chart data headers (R-V) 34, log 17, snapshots 51.
- A numeric rating-shop score (e.g. StarMine's 7) is written as a number, not text.
