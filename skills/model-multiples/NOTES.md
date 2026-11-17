# model-multiples: notes

Not read at runtime. Read before changing the scripts. Spec: docs/2026-11-17-applied-valuation-design.md §2-3 (local).

## Pieces
| Script | Job |
|---|---|
| `multiples.py` | the chapter's arithmetic: ratios with the NM rule, window stats, reverse P/E |
| `brief.py` | the valuation brief; model-valuation copies it (keep in sync). Fair share of a 15,000-word cap per section |
| `subject.py` | subject quarters from MOD, as of Px Events release dates; weekly closes from Px Data |
| `peers.py` | core peers' TTM EPS from edgar-xbrl-financials JSON; stooq closes |
| `sp500.py` | multpl.com trailing S&P 500 P/E (parser checked against tests/fixtures/multpl.html) |
| `fetch_comps.mjs` / `comps.py` | one Yahoo call per comp; comp-sheet rows |
| `importer.py` | paid exports → weekly NTM rows |
| `engine.py` | the numbers; build.py writes the same thing as formulas; verify.py compares |
| `build.py` / `build_parts.py` | the tab; package plumbing |
| `charts.py` | line and scatter chart XML |
| `xlsx.py lo.py notebox.py` (from model-consensus), `modmap.py` (from model-dcf), `prices.py` (from model-price-history) | copies; keep in sync |

## Decisions (2026-11-17, with the user)
- Two data paths. Paid = exported files, never logins.
- Free history = TTM as known on each date (no hindsight), not model-price-history's realized NTM.
- A core peer's quarter is known 45 days after quarter end (Q1-Q3) or 90 days (Q4): the latest SEC deadlines, so never early.
- Comp list wider than the industry players; 3-5 core peers get history (stooq per peer).
- Comp sheet from Yahoo only (deviation from the spec's XBRL; one source per comp).
- Ranges use `_xlfn.AGGREGATE` (ignores #N/A); LibreOffice supports it, so verify.py's recalculation is a fair check.
  The percentile is an array formula.
- Raw Yahoo dollars typed as printed and shown in millions with format `#,##0,,`. Never rescale a typed number.
- Net debt excludes operating leases (model-dcf's rule). EBITDA = Adjusted EBITDA on non-GAAP, else OI + D&A (noted).
- A rebuilt tab is appended last (the old one is replaced); the user moves it.

## Review changes (2026-11-17)
- prices.py got a CLI that copies found files into `Price Data/` and exits 1 on missing or bad files: no silent gaps.
- brief.py splits its 15,000-word cap by weighted fair share (key sections weigh 2) and lists cut and missing sections.
- fetch_comps.mjs writes an error snapshot for a null price or market cap and exits 1 if the subject fails.
- Soft comp warnings keep the numbers; only a currency mismatch blanks EV multiples (no false blanks).
- The ADV column is shares (M), not dollars (the data is shares).
- importer.py splits multi-ticker exports by ticker, reads semicolon / decimal-comma files, and stops on ambiguous
  commas, duplicate field headers or unknown headers with a mapping.json instruction (no guessing); skipped rows are reported.
- subject.py fails loudly on a missing MOD quarter column or a non-GAAP basis with no non-GAAP EPS row.
- The EBITDA fallback is reported as a note (the user hears about it).
- build.py is rerun-safe over an existing Multiples tab, reports dropped weeks, skipped charts and dangling names,
  and the paid path adds the NTM FCF yield.
- The percentile is an array formula and AGGREGATE is written `_xlfn.` (Excel opens it without repair).
- verify.py must print `"ok": true` and renders a PNG of the Multiples page.

## Final review changes (2026-11-17)
- Relative rows are GAAP vs GAAP: the S&P and XBRL peer figures are reported earnings. subject.quarters always
  carries GAAP TTM EPS; a non-GAAP basis gets its own "P/E (GAAP)" weekly column (GAAP basis: the P/E column is it).
- Paid path: the S&P NTM P/E column is kept as is. Vendor NTM consensus is consistent across subject, peers and the
  S&P, so the relative rows stay NTM vs NTM.
- Paid path unit check: the export's latest NTM sales vs MOD's last actual FY revenue (no sales: its market cap vs its
  price × MOD's latest diluted shares; neither: a warning). Outside 0.2-5x stops the build, naming the likely unit.
- Paid peer P/E is a formula on the peer's typed NTM EPS column. Trailing FCF yield is labelled LTM on the paid path.
- A typed cell with no value is NA() in black and listed as a formula: it is not a number from a source.
- Free path: MOD's unit column for revenue and shares not looking like millions is a warning.
- Street EPS is the analysts' basis (usually adjusted); years match by name (Yahoo endDate year = MOD FY label).

## DXCM baseline
Filled in by Task 13.
