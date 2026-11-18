# model-price-history: notes

Not read at runtime. Read before changing the scripts. Source of truth for intent: the original handoff kit (cloud session, Nov 2026, no longer kept) and its
golden reference model, a copy of which lives at `tests/fixtures/dxcm/reference_model.xlsx`.

## Pieces

| Script | Job |
|---|---|
| `modmap.py` | MOD period columns + rows by label (role → ordered patterns; the DXCM example labels and /model-ratios's) |
| `events.py` | proposes release dates / events from the gather folder; classifies full results by a diluted-EPS table line |
| `prices.py` | finds + checks the stooq CSVs, copies them to `<model>/Price Data/` |
| `engine.py` | pandas prototype: every number, and the layout decisions (start rows, block lengths, years) |
| `xlsx.py` | raw-XML package editing: add/remove tabs with drawings/charts/comments, append styles |
| `build.py` | writes the three tabs (formulas), fills chart templates from `assets/` |
| `lo.py` | LibreOffice headless recalc (private profile, always-recalc) and render |
| `verify.py` | recalc + compare with engine, error scan, byte-identity of every other part, PNG render |
| `refresh.py` | refresh: carry the user's shapes and notes and the tabs' places across a rebuild; check references |

Raw XML only, never openpyxl load/save on the user's file: openpyxl drops text boxes, shapes, images and OMML and
re-serializes charts. The DXCM example model has all of these on other tabs.

## The user's decisions (2026-11-08)

- **Lean Px Data**: the orphaned columns (old H–J indexes/relative, K daily alpha, L/N GAAP P/E, O TTM P/E, Q–R
  markers, AK–AM β-only weekly alpha, AR) are gone. Blocks, left to right: daily (A–G core, event label, overlays,
  TTM EPS, P/E) | monthly | annual | factor daily | weekly 3-factor. The weekly block now starts at the
  3-factor base week (DXCM: 2016-01-08), not 2014-12-31.
- Px Events keeps the reference layout (GAAP and non-GAAP EPS columns) - it is a table the user reads, not a chart.
- Test on a stripped copy of their model; never write their live file in tests.

## P/E is trailing (the user, 2026-11-17)

- P/E = close / TTM EPS as known that day, labelled TTM everywhere. It replaced "NTM P/E", which divided by the next 4
  MOD quarters: EPS nobody knew at the time (and model EPS at the end). The right forward measure is the consensus
  NTM EPS of the time, but there is no free history of it: Yahoo and Alpha Vantage `EARNINGS_ESTIMATES` keep 90
  days, and Koyfin shows it but exports only an image. Alpha Vantage `EARNINGS` has each quarter's consensus at the
  print (back to the 1990s), a possible later "consensus at print" NTM series.
- Gone with it: the NTM EPS columns (Px Data daily and monthly, Px Events). Px Data has two fewer columns, so
  everything right of the daily block moved left; other skills read Px Data's A-C by letter and the rest by header.
- The monthly block starts at the first month-end with a P/E (a leading #N/A draws as 0 in LibreOffice renders).
- Near break-even, TTM P/E runs into the hundreds (DXCM 2019: 373x on $0.09 TTM EPS). That is the measure, not a bug.

## Refresh (the user, 2026-11-17)

- Why: a rebuild deleted the user's 13 text boxes + 13 arrows on Idio Chart and every typed note, and stopped
  outright once the DCF and Multiples tabs read Px Data. So refreshing the price after a print cost the annotations.
- How: rebuild as usual (`build.py --refresh`), then `refresh.py restore` puts back, by what they belong to:
  - shapes: every Idio Chart drawing that is not the build's 'Chart 1'..'Chart 4' (and not /research-filings'
    'P1 ...' notes when its handoff file exists), byte for byte, in the same cells; only the drawing id changes;
  - notes: by date (Idio Chart Top-20) or by event date + name (Px Events), not by row; a note whose day left the
    table is reported, never dropped quietly;
  - the three tabs' places in the tab order (a build appends them at the end).
  Then research-filings' `handoff.py --idio-only` redraws its notes by date on the new axis and rewrites the
  yearly-returns block, leaving Filings Charts alone.
- References from other tabs (Multiples / Consensus link single Px Data and Px Events cells by row; DCF, MOD,
  Research read whole columns or ranges): a single cell must still have the same column header and the same row key
  (Px Data: the date; Px Events: period, event date, event); a range or column the same header. Anything else stops
  the refresh (exit 3). A range ending above the new last row is a warning: it misses the new days.
- Not done: re-placing the user's own shapes by date. In the same cells they drift left of their date as the axis
  lengthens (two weeks ~0.4% of the width, a year ~9%). handoff.py has the geometry if that is ever wanted.
- Test: `tests/test_refresh.py` on the reference model (26 user shapes, 3 notes) plus a typed Px Events note, a
  single-cell link and five extra trading days; the untouched reference (Research reads old column O) must stop.
  `handoff.py --idio-only` is proven on a copy of the user's DXCM model, not in the suite (no research fixture).

## Deliberate differences from the reference

- **Event list**: the reference's script kept only the later release when a quarter had two files, silently
  dropping preliminary-revenue releases (DXCM: 2015-10-14, 2019-01-07, 2020-01-13, 2021-01-11, 2022-01-10,
  2023-01-09). events.py classifies by content and keeps them. Full-results dates are identical (51/51).
- **Overlay right axis**: computed from the data, rounded out to 10% (DXCM: −50%..50%, because ROIC was −46% in
  2016); the user had hand-set −20%..60%.
- **P/E data-label nudges** on the FCF chart (3 manual `c:dLbl` offsets) are DXCM-specific and stripped from the template.
- Px Events reaction-day formula is wrapped in IFERROR (an "After close" event on the last price date would #REF).
- Idio Chart A2/A3 notes rewritten (the old ones described the rolling-β panel and TTM P/E).

## DXCM baseline (rerun after changing scripts)

`python3 -m pytest -q` (29 engine tests vs reference cached values, 1e-9; P/E columns are checked as close / TTM EPS
because the reference holds the old NTM P/E). End to end on a stripped copy of the
reference with `tests/fixtures/dxcm/*.csv`: verify PASS, 40,477 values, 0 failed, 0 errors, other parts
byte-identical. Handoff numbers: β 0.601, 3-factor β 0.831 / 0.696 / −0.205, R² 0.193, index 137.51, FY25 FCF 1,077.2,
buybacks 471.9, FY25 avg TTM P/E 43.9x, P/E months from Feb 2019 (11 in 2019), last P/E 33.07x on 2026-11-04.

Fixture prices were extracted from the reference model (its pasted values, with XHE/MTUM gaps already filled), so
prices.py's fill / stale checks are not exercised by them.
