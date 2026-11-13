---
name: model-historicals
description: Build a 10-year quarterly + annual core-financials model (income statement, balance sheet, cash flow) for one ticker in the house Excel template (Q1 | Q2 | Q3 | Q4 | FY per year), from 10-K / 10-Q / press-release markdown that the /collect-documents skill saves (it finds the folder, or runs /collect-documents itself). Covers commercial and industrial companies of any shape (restructuring, impairments, noncontrolling interests, preferred dividends, equity-method income, discontinued operations, pensions, buybacks and dividends, whole-million reporters); each model keeps only the lines that company reports. Stops on banks, insurers and REITs. Use when the user asks to build, construct or "model-historicals" a company's historical model.
---

# model-historicals

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

Builds `<TICKER>_model.xlsx`: the last 10 fiscal years (Q1 | Q2 | Q3 | Q4 | FY | spacer per year), plus the current
year's reported quarters, plus blank estimate columns. Core financials only. `/model-ratios` later inserts the
analysis rows and the ROIC / leverage / FCF sections into this same MOD tab, and `/model-kpis` adds the
non-GAAP and company-metrics sections, so do not add them here. The template keeps the period headers on their own
row 2 and starts INCOME STATEMENT on its own row, like the DXCM example model, so sections can go above it.

The scripts do the mechanical 90%: parse, map, tie out, write, verify. Your job is the judgment, and making
every judgment visible to the user.

## Inputs

- **Source documents**: the ticker folder `/collect-documents` fills (`_manifest.json` plus `_md/` markdown folders). Step 0
  finds it. Always read the markdown versions, never the PDFs.
- Template: `assets/core_template.xlsx`, a **superset** of the user's `mod_template_core_financials.xlsx` (2026-11-06).
  It has a row for every common US-GAAP line item: the DXCM example rows, plus the Regulation S-X Article 5 captions and
  the lines the Morningstar 43-company count and common 3-statement models show. build.py **deletes the optional rows a company
  never reports**, so each model shows only that company's lines. Regenerate it with
  `scripts/make_template.py` (see NOTES.md). Use a different template only if the user asks.
- **Covers commercial and industrial companies** (tech, healthcare, consumer, retail, industrial, energy...).
  **Banks, insurers and REITs are out of scope:** extract.py stops with exit code 3 when the latest 10-K looks like
  one (deposits + net interest income, premiums earned, investments in real estate). Tell the user and stop.
- Needs Python 3 + openpyxl (`pip3 install openpyxl` if missing).

## Workflow (create a task list with these steps)

0. **Locate**: `python3 "<this skill's folder>/scripts/locate.py" --ticker <TICKER>`. It searches
   `$RD/<TICKER>` first, then the rest of the Desktop, then lightly searches Downloads, Documents and
   the home folder. It prints JSON and stops at the first folder with a 10-K plus Q1–Q3 10-Qs for each of the last 10
   fiscal years.
   - `"status": "found"`: use its `src` and `model_dir`. Tell the user which folder you used.
   - `"status": "gather"`: nothing complete was found, so **run the `/collect-documents` skill for the ticker** (Skill tool,
     skill `collect-documents`, args `<TICKER>`) and follow its instructions fully. Then run locate.py again. Run /collect-documents at
     most once per model-historicals run.
   - Still `"gather"` after /collect-documents: use `best` and build with `--years <best.complete_years>`, then tell the user which
     years are short and why (`best.missing`; e.g. a company listed under 10 years ago). If `best` is null or has 0
     complete years, stop and report.

   Set up the paths:
   ```bash
   SRC="<src>"; T="<model_dir>"; W="$T/_model_work"
   mkdir -p "$W"
   ```

1. **Extract**: `python3 "$SK/extract.py" --src "$SRC" --work "$W" --decisions "$W/decisions.json"`
   (the decisions file may not exist yet; that's fine.)
   **Exit code 3** = a bank, insurer or REIT: stop and tell the user.
   Every filing must tie to its own subtotals (`$W/extract_report.md`). If one fails, open that filing's
   markdown table (grep the statement heading), find why, and fix it with a `label_overrides` entry in
   `decisions.json` (or fix the parser if it's a parsing bug). **Never plug a number to force a tie.**
2. **Diagnose**: `python3 "$SK/diagnose.py" --src "$SRC" --work "$W"`, then read `$W/diagnostics.md` in full.
3. **Decide** (see the judgment policy below), and write every decision into `$W/decisions.json`.
4. **Build**: `python3 "$SK/build.py" --work "$W" --template "<skill>/assets/core_template.xlsx" --ticker <TICKER> --out "$T/<TICKER>_model.xlsx" --decisions "$W/decisions.json"`
   **Never overwrite an existing file.** If `<TICKER>_model.xlsx` exists, write `<TICKER>_model (new).xlsx` and say so.
5. **Verify**: `python3 "$SK/verify.py" --work "$W" --model "$T/<TICKER>_model.xlsx"` must report 0 failed and
   0 colour exceptions. Fix the cause and rebuild; never hand-edit the output to pass.
   - It also checks basic EPS to the cent against each filing.
   - **Diluted-EPS differences are warnings, not failures.** The model's diluted EPS is net income to common ÷
     diluted shares, as in the DXCM example model. Companies with convertibles often add the notes' interest back to the
     numerator (the if-converted method; DXCM from 2024). Name those periods in the report, with the reason.
6. **Report**: the judgment calls stay in `$W/JUDGMENT_CALLS.md` (the user keeps working files in `_model_work`, not
   next to the model). Your final message contains:
   - what was built (years, quarters, file name)
   - the verification result (number of checks, failures)
   - **every** judgment call from JUDGMENT_CALLS.md in plain English: what you did, why, and the size of the effect
   - anything you could not resolve

## Judgment policy (house rule; this matters more than anything else in this file)

- **Business segment change** (diagnostics section A says a change, or the "Segment Recasts" folder has files):
  **STOP and ask the user before building.** No exceptions.
- **Accounting changes, restatements, reclassifications, stock splits, odd line items:** use your best judgment
  and keep going, **but log every call**. The worst outcome is a call the user never hears about. A call they disagree
  with is fine, because they can see it and reverse it.
- Defaults that worked for DXCM (house defaults):
  - **Restatements** (diagnostics C): keep each period **as originally filed**, so each year's quarters sum to the
    year. Say what the restated numbers would be, and how big the difference is, using the company's
    reconciliation table in the 10-K note (see diagnostics D).
  - **Stock splits** (diagnostics B): multiply pre-split share counts. Use the `share_splits` entry that
    diagnostics suggests, and check `through_period` = the last period whose own filing came before the first
    split-adjusted filing.
  - **Lines with no row in the template:** fold them into the nearest row. The scripts tag these as "fold" or
    "fallback" in the report. Review each one, and override it if a different row is better economically. For
    example, collaborative R&D fee → R&D, amortization of intangibles → SG&A (matches how DXCM later presented
    it), and net-share-settlement tax payments → stock issuance / repurchase.
  - **A line combined on one filing but split on a later one** (e.g. "Intangibles and other assets"): split it
    using the later filing's numbers for the same date, as a `value_overrides` entry with a note.
- Big ones to look for in the 10-K "Recently adopted" notes: ASC 606 revenue (2018), ASC 842 leases (2019; ROU rows
  are 0 before), ASU 2016-18 restricted cash (2018; restricted cash is 0 before), ASU 2020-06 convertible debt
  (2021–22).
- Q4 share counts come from the Q4 earnings release. If one is missing, the script uses the next year's release
  (prior-year column) and logs it. If both are missing, look in the 10-K's quarterly data note; if it's still not
  found, leave the cell blank and report it. **Never set Q4 shares to the FY count:** FY is the full-year average,
  not Q4.

## How filing lines map (extract.py)

- **Each common item has its own row** (house default: one row per common item). That covers:
  - operating expenses: S&M, G&A, amortization of intangibles, restructuring, impairment, acquisition &
    integration, litigation, gain/loss on asset sales
  - non-operating items: investment gains, debt extinguishment, equity-method income (before or after tax)
  - below the tax line: discontinued operations, noncontrolling interests and preferred dividends (→ Net Income to
    Common, which EPS uses)
  - balance sheet: other current assets, long-term investments, accrued expenses, income taxes payable, other
    current liabilities, long-term deferred revenue, deferred tax liabilities, pension, mezzanine equity,
    noncontrolling interests
  - cash flow: impairment, gain on sale, income-tax working capital, other operating assets & liabilities,
    capitalized software, divestiture proceeds, buybacks, dividends

  A line no rule knows goes to its block's "Other" row as a **fallback**. Every fold and fallback is listed in
  `extract_report.md`; review each one.
- **Layouts:**
  - with or without a gross-profit line (Medtronic lists every cost under one "Costs and expenses" heading)
  - "Net sales: / Cost of sales:" headings with Products / Services lines (Apple)
  - gross PP&E, accumulated depreciation and net PP&E all shown (only the net is used)
  - an "Interest expense, net" total printed under its parts (not counted twice)
  - no pre-tax line (no taxes)
  - no total-liabilities line
- **Signs come from the company's own subtotals**, not from labels. When several readings tie, the one that agrees
  with the labels wins (income positive, expense negative).
- **Rounding:** companies that report whole millions (MDT) have totals that miss the sum of their lines by $1–2M.
  The difference goes into that block's "Other" row with the tag `rounding`, so the model's subtotals equal the
  reported ones, the balance sheet balances, and ending cash ties. Only gaps of up to 3 units at the filing's own
  precision are treated as rounding; anything bigger is a real tie-out failure.
- **Q4 share counts:** these come from the Q4 release. Next is the next year's release (prior-year column).
  The last resort is **derived**: Q4 ≈ 4 × FY − (Q1 + Q2 + Q3). A year's weighted-average share count is about
  the average of its quarters, so this is close but approximate. It's logged; tell the user which years use it. It is
  never the FY count itself.

## decisions.json

```json
{
  "notes": ["Plain-English record of each policy decision (e.g. restatement basis) - copied into JUDGMENT_CALLS.md"],
  "label_overrides": [{"statement": "IS", "pattern": "regex on the filing line", "role": "RD"}],
  "share_splits": [{"through_period": "Q1 22", "factor": 4, "note": "4-for-1 split June 2022"}],
  "value_overrides": [{"period": "FY 21", "role": "GWI", "components": [26.5, 31.5], "note": "why"}]
}
```
Roles (`build.py` IS_IN / BS_IN / CF_IN):
- **IS:** `REV COGS RD SGA SM GA AMORT RESTR IMPAIR ACQEXP LITIG GAINOP OTHOPEX ISDA OTHINC GAININV DEBTEXT EQAFF INTINC
  INTEXP TAX EQAFF_AT DISCOPS NCI_IS PREFDIV`
- **BS:** `CASH STSEC AR INV PRE OCA PPE ROU GWI LTINV DTA OTHA AP PAY ACCR TAXPAY CURDEBT OPLLC CLOTH (deferred revenue)
  OCL LTDEBT OPLLLT DEFREVLT DTL PENSION OTHLTL MEZZ EQ (parent) NCTL`
- **CF:** `NI_CF DA SBC NCI (non-cash interest) DT EQI IMPAIR_CF GAIN_CF OTHNC W_AR W_INV W_PRE W_ROU W_AP W_PAY W_OTH
  W_TAX W_OTHAL PURSEC SALESEC CAPEX CAPSW ACQ DIVEST OTHINV STOCK BUYBACK DIV DEBT OTHFIN`

Costs are entered as negatives in the model; the scripts handle signs.
Period keys look like `Q1 22` and `FY 22`.

**MOD fill convention (house default).** Ordinary rows: quarter cells plain, fiscal-year cells grey; section title rows (text in column A) carry their section colour across every quarter and year; spacer columns and year columns with no quarters (2050E) untouched. `scripts/modfill.py` enforces it: the build runs `fix` after every save and the check fails on any break (`python3 scripts/modfill.py check MODEL`). Never hand-colour MOD cells; if you add or rewrite MOD rows outside the scripts, run `python3 scripts/modfill.py fix MODEL MODEL` and then `check` before saying done.

## Model conventions (build.py enforces them; verify.py checks them)

- **Colours (the house convention):** every core-financial number is **blue** in every column. That includes typed
  values, YTD differences (`=85.3-D72`), Q4 plugs (`=FY-Q3-Q2-Q1`), balance-sheet Q4 (`=FY`) and split-adjusted
  shares (`=97.2*4`), because they are all reported facts. Summations, subtotals and ratios are **black**.
  Links between sections (CF net income `=D25`, beginning cash `=prior ending cash`) are **green**.
- Quarters: income statement Q1–Q3 come from the 10-Q 3-month column; Q4 = `=FY-Q3-Q2-Q1`.
- Balance sheet Q4 = `=FY`.
- Cash flow is reported year-to-date, so Q2 = `=YTD6M-Q1`, Q3 = `=YTD9M-Q2-Q1` (blue), and Q4 = `=FY-SUM(Q1:Q3)`.
- Shares are typed in every column, Q4 included.
- **Rows:** optional rows that are zero in every built period are deleted, and their terms come out of every sum.
  These are always kept, even at zero, because later skills read them: revenue, COGS, taxes, cash, equity, current
  and long-term debt, D&A, capex and interest expense. Net Income is consolidated (it starts the cash flow). EPS uses
  Net Income to Common when there is a noncontrolling interest or a preferred dividend.
- Beginning cash: the first Q1 and first FY are typed; every later period links to the prior period's ending cash.
- Every data column is width 11.0 (66 px on the user's Mac); spacers are 2.0. Quarter groups stay collapsed like the
  template.
- Estimate columns get headers and formatting only; the forecasting agent fills them.

## Reference

- `NOTES.md`: changes made to the house template, and known limitations / next steps.
- `reference/dxcm_example/`: a full verified DXCM run (decisions.json, diagnostics, judgment calls, verify report,
  output model). Use it as the worked example and as the baseline to compare against after changing the scripts.
