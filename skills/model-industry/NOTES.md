# model-industry: notes

Not read at runtime. Read before changing the scripts.

## Pieces

| Script | Job |
|---|---|
| `lines.py` | the 25 condensed lines, MOD label patterns, XBRL field map, sign convention |
| `fiscal.py` | fiscal → calendar year (most months; end − 15 days for 52/53-week years) |
| `sec_fetch.mjs`, `fetch.py` | filing lists, XBRL engine runs, peer 10-K Markdown (cached in `Industry P&L/peers/`) |
| `sources.py` | MOD-style models by label |
| `segments.py` | segment-note snippets for the reader; printed-on-the-line check |
| `assemble.py` | everything → `industry.json` (link / typed / est per cell, with notes) |
| `compute.py` | Python prototype of every number (rules table in the plan) |
| `charts.py` | house-style chart XML (the FCF chart look) |
| `build.py` | the two tabs, formulas, charts (raw XML) |
| `verify.py` | LibreOffice recalc vs prototype, errors, byte identity, PNG |
| `xlsx.py`, `lo.py` | copies of model-price-history's (xlsx adds merged cells) |

## Decisions (house defaults)

Division players: option A (disclosed + parent × revenue share). Annual, 10 years, history only. Peer files inside
the subject's folder. Pause to confirm peers. Read only the industry / competition sections of the filings research and the street research.
Charts 1–6 (asset growth, working-capital days and FCF-margin charts cut for now). How-to-read notes on charts 3
and 6 only. Chart style = Idio Chart.

## Known limitations

- No acquisitions line (the XBRL engine has no field).
- Segment operating profit is before corporate costs, so segment margins run high; the block header says so.
- Estimated taxes / net income use the parent's revenue share, not the segment's profit share.
- XBRL values are the engine's (latest-filed comparatives), not each year's as originally reported.
- ROIC is the condensed approximation: cash + receivables + inventory + PP&E + G&I − payables & accrued.
- Industry gross / EBITDA / FCF margins divide by total industry revenue; a company missing COGS (or D&A, CFO) adds revenue but no profit, which understates the margin.
- Charts use twoCellAnchor (9 columns x 20 rows each): LibreOffice draws empty rows shorter than 16 pt, so fixed-size anchors overlapped the notes.

## DXCM baseline (2026-11-09, on a copy in /tmp/ipnl_dxcm)

Peers: DXCM (MOD), ABT Diabetes Care (XBRL parent; revenue only, a product line inside Medical Devices), MDT Diabetes
(MDT_model.xlsx parent; segment revenue, operating profit (EBITA to FY2019), depreciation, assets, and FY2023-25
expense lines), SENS (XBRL). Excluded: Roche, Chinese makers. Times: fetch 12 s (10 ABT 10-Ks), segment reader ~90 s,
assemble + build + verify ~7 s. Segment check: ABT 9, MDT 52 accepted, 0 rejected, 2 MDT recast conflicts (newest
wins). Estimated cells: ABT 189, MDT 174. verify PASS, 2,366 cells, 0 failed. 2025: industry revenue 15,807; DXCM
share 29.5%, ABT 50.6%, MDT 19.7%, SENS 0.2%.
Found: the XBRL engine returns a component revenue tag for SENS 2019-2022 (us-gaap:Revenues is right) -> overrides.
ABT Diabetes Care revenue is only printed from FY2017, so 2016 is DXCM + MDT + SENS (share chart steps in 2017).
MDT's FY2026 10-K drops Diabetes as a segment (MiniMed IPO, March 2026); FY2026 revenue comes from the sales table.

## Formatting (house style, from hand edits to the DXCM tabs)

Industry P&L: 22 pt title row; navy header row (A:last year, white bold); the industry block's Income statement /
Balance sheet / Cash flow rows are blue bands (0070C0, white bold) across the row, company blocks stay plain;
INDUSTRY ANALYSIS is a navy band; year columns 13 wide; notes in rows 2-3 on one line (no wrap); each company's
header note wrapped in column B, 16 pt per ~50 characters. Industry Comparison: zoom 117, column A 9 and B:T 13
(the charts span cells, so they grew), 22 pt title row, 34 pt peer-table header. Two calls beyond those edits: column
C (the first year) is 13 too (it was left at 11), and the Senseonics header row gets the same height rule.
