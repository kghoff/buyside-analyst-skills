# model-kpis: notes

Not read by the skill at runtime. Read before changing the scripts.

## Where it came from (2026-11-04)

Two claude.ai drafts, both built on DXCM (kept outside this repo):
`model-kpis` (v1) and `model-kpis-v2` (v2). Both ran end to end. Tested on the same DXCM inputs:

| | v2 | v1 |
|---|---|---|
| Full model (a copy of the DXCM model) | 227 checks, 0 failed | 230 checks, 3 failed (2021 EPS) |
| Equal to the user's hand-built section | 1,351 / 1,353 cells | 1,336 / 1,353 |

The skill is v2 (a plan file holds the judgment calls; `--replace`; notes on links and formulas; the user's labels) plus:

- **From v1:**
  - the old "Shares used … per share" + Basic / Diluted share layout, which fills Q3 17, Q4 17 and FY17 EPS.
    Q3 17 = $0.00 restated, which matches the release.
  - row-label notes
  - tokenizer-based formula shifting
- **New in the merge:**
  - **Row inserts update every tab.** Both drafts left the ANALYZED tab's `=MOD!F12` links pointing at the old
    rows, so it showed wrong numbers with no error. v2 also missed `MOD!` references on MOD itself.
  - *(removed 2026-11-06 with the ANALYZED tab)* **model-ratios's fingerprint is refreshed** when ANALYZED was untouched, so a later /model-ratios rerun
    doesn't stop with "edited". If the user did edit ANALYZED, the mismatch is left alone and model-ratios still
    asks them.
  - **Restatement-bridge tables are skipped.** These are tables with columns "As Previously Reported | Adjustment
    | As Adjusted". Both drafts read their columns as periods. That was the source of v1's 2021 failure (a 1.2
    add-back from the Q2 22 / Q3 22 decks) and of v2's 0.0 totals in the inventory.
  - **Shares, add-backs and reported EPS follow their column's GAAP basis.** If the same document's reconciliation
    for that column starts from a GAAP figure the model doesn't have, they are skipped too. This replaced v2's
    hand-written 2021 `exclude`.
  - **Year-to-date columns are never used for a quarter's shares, add-backs or EPS.** v2 could take a six-month
    add-back as a quarter's.
  - **Documents are classified by /collect-documents folder.** v2 read "Earnings Calls" as "earnings" and ranked every
    transcript as a press release.
  - **The verifier checks more:** other tabs, missing notes on typed and linked cells, and EPS to the cent. The old
    tolerance let a wrong 2021 add-back pass in Q2 21.
  - **/model-ratios skips the NON-GAAP and KEY OPERATING sections** (a change in its `roles.py`). Otherwise its
    income-statement row search ran into non-GAAP rows, and ANALYZED duplicated rows that already have their own
    analysis.
  - **The KPI scan + backfill** (kpi_scan → discovery agent → kpi_snippets → reader agents → kpi_check →
    kpi_build). The user chose "scan and fill all".

## Layout change (2026-11-06)

The user moved the DXCM example model to one MOD tab with the analysis nested in the statements, and asked that all skills
follow it. So:
- /model-ratios now writes into MOD (no ANALYZED tab). The fingerprint refresh in `xlmodel._shift_rows` existed
  only for that tab, so it was removed.
- KEY OPERATING METRICS goes above INCOME STATEMENT (the user's ALT DATA area). Models from before the change keep it
  before BALANCE SHEET, because their INCOME STATEMENT title shares the period-header row.
- The NON-GAAP METRICS header uses the user's lighter sub-section fill (theme 3, +25%), like the ROIC / leverage / FCF
  headers.
- Full chain on a fresh DXCM base model (base → analyze → non-GAAP): ng_verify 226 checks, all zeros; kpi_check
  231 values, 0 model problems. A /model-ratios `--replace` afterwards rebuilt MOD identically (0 cells
  differ), and its verify gave 12,678 checks, 0 failed.

## DXCM baseline (rerun after changing the scripts)

Inputs: a copy of the DXCM model (without the section), sources in the DXCM research folder,
`reference/dxcm_example/plan.json`, `kpi_plan.json` and `values/` (copy `values/` into the work folder and skip
the discovery and reader agents).

| Step | Expected |
|---|---|
| ng_extract | 874 candidates, 0 unresolved, 8 restatement bridges skipped |
| ng_build | 37 rows, 181 bridges, 4 log items |
| kpi_check | 231 values, 8 metrics, 0 rejected, 13 conflicts; `--built`: 0 model problems |
| ng_verify | 230 checks, 0 failed, 0 errors, 0 colour, 0 missing notes, 0 changed outside, 0 other tabs |

The section equals v2's reference plus the 2017 EPS cells, and the user's hand build except their Q4 15 / Q4 16 share cells.

**On the core model + ANALYZED tab** (model-historicals's `DXCM_model_skill_test.xlsx`, with /model-ratios run on it):
ng_verify 226 checks, 0 other tabs changed. /model-ratios rerun: no "edited" stop, 233 rows, 9,699 checks, 0 failed.

**KPI lessons from the DXCM run:**
- The reader took 2017 sensor revenue from the 2017 releases ("Sensor revenue"), but the 2018 releases redefined
  it as "Sensor & other revenue" and restated 2017. FY17 then summed to 513.6 vs the reported 515.6. `kpi_check
  --built` caught it. The fix: `"prefer_restated": [2017]` plus the restated quarters.
- The Q1 24 deck restated international organic revenue for 2021-23 (conflicts, original kept). It also gave
  FX-only history that older decks combined with acquired revenue.

## DXCM findings that will recur

- **Definitions drift, and companies restate the prior year.** In 2018 Dexcom began excluding non-cash
  convertible interest and restated 2017 ("As Adjusted"). In 2019 it began excluding business-transition costs
  and amortization, and restated 2018. Mixing original and restated quarters breaks the FY sum, so use
  `prefer_restated` for those metric-years.
- **New accounting standards restate GAAP too.** After ASU 2020-06 (2022), the 2021 comparatives were restated,
  but the model keeps 2021 as originally filed. The extractor skips any column whose GAAP start doesn't match the
  model.
- **Early years are patchy.** The 2015–16 releases only reconciled when there was an adjustment, and the Q4 15 /
  Q4 16 releases show full-year columns only. Those full years are typed.
- **Decks omit lines that are zero that quarter.** Releases rank first.
- **the user's hand-built model** has full-year share counts in the Q4 15 / Q4 16 cells. They should be cleared;
  the skill fills FY15 / FY16 EPS instead.
- **Stock split:** pre-split share counts are ×4 (`=94.1*4`), and pre-split EPS is checked ÷4.

## ABT (second company, 2026-11-17)

- **"Specified items" reconciliations** (`specified_candidates`, `spec_shares` in ng_extract.py): one table per period
  headed by a period token (3Q26, 12M24; 6M / 9M skipped), line items down the rows, As Reported | Specified Items |
  As Adjusted across, plus a captioned "Details of Specified Items" table split by category. Before this the
  extractor found 0 candidates for ABT. Tests: `tests/test_specified.py`.
  - Gross margin there is after intangible amortization; when GAAP margin + the printed amortization line equals the
    model's gross profit, the bridge starts there and drops the amortization category (not added back twice).
  - 2016-2020 tables start from earnings from continuing operations: the bridge starts at the model's net income and
    takes the model's discontinued-operations row out first (a link row in the plan, `sign: -1`).
  - Labels vary: "(Loss)", "(benefit)", "Net Earnings from Continuing Operations", "AsReported(GAAP)" run together.
- **Two-class EPS** (ng_build.py): optional EPS row `{"role": "item", "id": "partsec"}` = non-GAAP net income x the
  model's GAAP participating-securities share (formula, IFERROR - the Evaluator has no IF). It matched ABT's reported
  adjusted EPS in all 14 periods where the GAAP allocation is filled; the 12 left are years where it is 0.
- **Sell-side notes are their own document type** (`sellside`): "JPM earnings recap" matched "earnings" and was
  ranked as a company release in the KPI reading list.
- Result: ng_verify 156 checks, 12 failed (the two-class years above), all other counts 0; kpi_check 3,404 values,
  73 metrics, `--built` 0 model problems. DXCM: the new reader adds 0 candidates and 0 unresolved.
- KPI lessons: readers took pro forma figures (2016 St. Jude businesses, Exact Sciences' pre-close sales) as sales -
  tell readers "the company's own reported figures only" for dollars; comparable growth *rates* are fine with a note.
  A business moved between lines mid-year (ICM, Q2 19) breaks the FY sum: `prefer_restated` + the restated quarter.
- **Share label split over two rows** (2026-11-18): the Q4 20 - Q2 22 releases print "Average Number of Common Shares
  Outstanding" / "Plus Dilutive Common Stock Options 1,789" on two rows. `spec_shares` joins a label-only row to the
  next one. Missing it left Q4 20 and Q1 21 EPS blank (a year of /model-price-history's P/E chart); after: 159 checks,
  the same 12 failed.
- **ng_verify on a `--replace` rerun** reports thousands of cells "changed outside the sections" when the before copy
  already has KEY OPERATING METRICS (it aligns rows as if that section were new). A direct cell compare found 0
  changes outside NON-GAAP METRICS. Not fixed yet.

## Known limitations / next steps

- **Reconciliation blocks follow "GAAP X → adjustments → Non-GAAP X".** Non-GAAP opex by line, free cash flow
  and organic growth don't fit that pattern; the KPI step picks those up as company metrics instead.
- **Fiscal years come from file names**, as /collect-documents names them: year-first ("2026 Q3 ...") since 2026-11-06, quarter-first ("Q3 26 ...") in older folders. Both parse. The DXCM reference `values/` cite the year-first names.
- **Event decks** have no period in their file name, so they're used for KPI discovery and comparatives, not as
  a period's own document.
- **Bridges are written as explicit additions** (`=start+item+item`). Adding a row later means `--replace`.
- **Second company:** not yet tested on a company other than DXCM (see the build log in the spec for the MDT plan).
