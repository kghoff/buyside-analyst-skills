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
