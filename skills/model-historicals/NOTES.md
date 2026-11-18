# model-historicals: notes

Not read by the skill at runtime. Two things worth keeping: how `assets/core_template.xlsx` differs from the user's
original template, and what still needs work. `reference/dxcm_example/` is a verified DXCM run to compare against
after changing the scripts (rerun DXCM with its decisions.json; expect 51 filings tie, 959 checks, 0 failures; its
spreadsheet predates the grey FY shading, so compare numbers, not formatting).

## Changes made to the house template (`assets/core_template.xlsx`); tell the user if you change more

1. **Added "Exchange Rate Effects" (row 104)** and included it in Net Change in Cash. Without it, ending cash can't
   tie for any company with foreign operations.
2. **Added a cash reconciliation block** (rows 109–114): Cash (BS) | Restricted Cash | Total Cash | Cash Check. It
   was in the DXCM example model, and it's the second hard check after the balance check.
3. **Net Income = Pre-Tax Income + Taxes** and **Tax Rate = −Taxes / Pre-Tax Income**. The template used EBIT,
   which skips the Interest Income/Expense rows. build.py also applies this fix automatically and logs it, if a
   template still has the old formula.
4. **Grey FY columns (build.py, Nov 3 2026):** every FY column (reported and estimate) gets the user's "Background 2, darker 10%" fill below the header, as in the DXCM example model. Rows with their own fill (section headers) keep it.
5. **INCOME STATEMENT on its own row (2026-11-06):** row 2 holds only the period headers (and "Units"). The
   INCOME STATEMENT title moved to a new row 3, like the DXCM example model, so /model-kpis can put KEY OPERATING
   METRICS above it. Every template formula was re-pointed. The DXCM rebuild still gives 51 filings tied, 959
   checks, 0 failed.
The user's original is still at `the user's Models/mod_template_core_financials.xlsx`.

6. **Superset template (2026-11-06):** `scripts/make_template.py <old template> <new>` rebuilds it from the LAYOUT and
   SUBTOTALS lists (150 rows, 117 roles; styles cloned from the user's rows). Sources for the extra line items:
   - SEC Regulation S-X Rule 5-02 / 5-03 captions (17 CFR 210.5-02, 210.5-03)
   - a count of the lines with numbers across a 43-company sample of standardised statements of non-financial companies
   - common 3-statement models: preferred stock, finance and operating
     leases, gains/losses on sale, impairments, financial investments, dividends
   The common non-GAAP add-backs in the SEC guidance (restructuring, impairment, acquired-intangible amortization,
   acquisition costs, litigation, gains/losses) each have their own GAAP row, so /model-kpis's bridges link to
   real lines. Label changes from the DXCM-specific wording:
   - "Accounts Payable & Accrued Liabilities" → "Accounts Payable"
   - "Current LT Senior Convertible Notes" → "Current Portion of Debt"
   - "Deferred Revenue / Other" → "Deferred Revenue"
   - "LT Senior Convertible Debt:" → "Long-Term Debt:"
   - "Stock Issuance / Repurchase" → "Stock Issuance / Employee Plans", plus "(-) Share Repurchases"

7. **Two-class EPS row (2026-11-17, ABT):** "(-) Earnings Allocated to Participating Securities" between Preferred
   Dividends and Net Income to Common (in its sum). Each cell is `=allocated to common - net earnings`, both printed in
   the EPS note, so EPS ties to the cent. extract.py fills a year only when the 10-K and every 10-Q print the allocation
   to the million (Q4 is FY - Q1 - Q2 - Q3); other years stay at zero and are listed in extract_report.md. The user's
   original template wasn't on this machine, so it was added with `make_template.py --from-superset <current> <new>
   PARTSEC=PREFDIV` (styles from the current superset; cell-for-cell identical apart from the new row and the NI to
   Common formula).

## Baselines (rerun after changing the scripts; numbers as of 2026-11-06)

| Company | extract | verify | What it exercises |
|---|---|---|---|
| DXCM (`reference/dxcm_example/decisions.json`) | 51 filings tie, 12 mapped-line calls | 1,105 checks, 0 failed, 12 diluted-EPS warnings (if-converted, 2024+) | one-decimal reporter, stock split, convertibles |
| MDT (no decisions) | 41 filings tie, 26 mapped-line calls (incl. rounding) | 1,085 checks, 0 failed | April fiscal year, no gross-profit line, whole-million rounding, NCI, restructuring / litigation / acquisition rows, held-for-sale, dividends + buybacks, derived Q4 shares (no Q4 releases gathered) |

DXCM differences vs the pre-expansion model, all intended:
- amortization of intangibles has its own row (it was folded into SG&A)
- buybacks are split from stock issuance
- equity-method income, investment gains and debt extinguishment have their own rows
- 2025 "Other current liabilities" sits in its own row
- the all-zero IS D&A row is gone

| ABT (2026-11-17, its `_model_work/decisions.json`) | 43 filings tie, 28 mapped-line calls | 1,017 checks, 1 failed (FY 25 basic EPS: two-class allocation printed only to $0.1B) | "Earnings" wording, dollars in millions with shares in thousands, balance sheet split over two pages, unlabeled total rows, zero-width year header rows, working capital with no heading, discontinued-operations subtotal, two-class EPS |

Rerun 2026-11-17 (after the ABT changes): MDT 1,095 checks, 0 failed; DXCM 1,105 checks, 25 failed. Both counts are the
same on the code before the ABT changes, and DXCM's failures are identical (pre-split EPS 2016-2019 off by about 4x, so
the split adjustment no longer lines up with the current DXCM folder). Not caused by the ABT work; still to fix.

`tests/` pins each mapping rule to the filing pattern it handles.

## Known limitations / next steps

- **Target layout of the finished model** (house default), top to bottom: KEY OPERATING METRICS (ALT DATA) →
  INCOME STATEMENT → NON-GAAP METRICS → BALANCE SHEET → ROIC, ROE, ROA → LEVERAGE & CASH CONVERSION → CASH FLOW
  STATEMENT → FREE CASH FLOW, all on MOD. Later skills insert into this; keep section titles in column A.
- **Tested on two companies** (DXCM, MDT). Still untested:
  - a company reporting **in thousands** (scaling exists in mdtables.py, but no real run yet)
  - **discontinued operations, preferred dividends, mezzanine equity, finance leases, capitalized software,
    equity-method income**: rules and template rows exist and are unit-tested, but no real filing has used them
  - a 52/53-week year (the derived Q4 shares are rougher when Q4 has 14 weeks)
  Expect to add label rules in `extract.py` (`map_is` / `map_bs` / `map_cf`). The subtotal tie-out will tell you
  which line is unmapped.
- Assumes the 10-Q column order [3M current, 3M prior, YTD current, YTD prior]. diagnose.py would catch a
  different order as false "restatements".
- Banks, insurers and REITs don't fit this template: extract.py detects them and stops (exit 3).
- Revenue and cost of sales are one row each; product / service / segment splits belong in the KPI rows
  (/model-kpis) or the user's ALT DATA area.
- Equity is one row (parent shareholders' equity); common stock / APIC / retained earnings / AOCI / treasury are
  not broken out.
- MDT's diagnostics flag a segment change. The skill's policy is to stop and ask the user before building a real MDT
  model.
- Q4 shares depend on the earnings release having a share table; the fallbacks are logged.
- Restatements default to as-originally-filed. A "restated basis" option, using the company's reconciliation note,
  would be a good addition (DXCM ASU 2020-06: 2021 NI 154.7 as filed vs 216.9 restated).
- **Colour rule (confirmed by the user):** every core-financial input row is blue in every column, Q4 plugs and YTD
  differences included. Blue means "reported number from the filings," not "typed constant." Subtotals and ratios
  are black, and links between sections are green. This is set by `INPUT_ROLES` / `color_for` in build.py and
  checked by verify.py.
