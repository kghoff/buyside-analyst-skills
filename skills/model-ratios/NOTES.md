# model-ratios: notes

Not read by the skill at runtime. Read before changing the scripts.

## Layout (house default)

The analysis lives **in MOD**, nested in the statements, like the DXCM example model: analysis rows under
each line; ROIC, ROE, ROA and LEVERAGE & CASH CONVERSION between the balance sheet and the cash flow statement; FREE
CASH FLOW after the cash flow statement. It replaced the ANALYZED tab (2026-11-03 to 11-06).

How the inline write works:
- `recipe.build_layout` lists every MOD row once ("keep") with the new rows in between.
- `rowmap.remap_rows` moves the existing rows down in one pass and re-points every formula in the workbook. It uses
  the same tokenizer approach as /model-kpis's `xlmodel.py`; the two copies are kept separate on purpose, so each
  skill installs on its own.
- The new rows are then written into the gaps.
- `analyze_rowmap.json` (backup row → new row) lets verify.py prove every old row kept its values.

Other changes on 2026-11-06:
- ROE / ROA moved into the ROIC section.
- Invested capital became the user's "operating assets − non-interest-bearing current liabilities", with and without
  cash. The lines are chosen per company in `analyze_decisions.json`.
- Added capex % of sales, FCF conversion (FCF / net income) and growth rows on operating cash flow.
- The user's own DXCM FCF conversion divides by **non-GAAP** net income, which /model-kpis builds later. That isn't
  wired up yet; offer it.

## DXCM baseline (rerun after changing the scripts)

Fresh model-historicals build (`reference/dxcm_example/decisions.json`), then analyze with no FCF adjustments: 229 layout
rows, verify 9,829 checks, 0 failed. After /model-kpis, a `--replace` rerun changes 0 cells and verifies 12,678
checks, 0 failed.
