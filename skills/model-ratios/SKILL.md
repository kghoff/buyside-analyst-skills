---
name: model-ratios
description: Add the analysis to the user's base model (TICKER_model.xlsx from /model-historicals), inside the MOD tab in the house layout - % yoy / % 2 year / % qoq growth, margins, bps yoy and incremental margins under each line; ROIC, ROE, ROA (NOPAT, operating-asset invested capital with and without cash, averaged) and LEVERAGE & CASH CONVERSION (EBITDA, leverage, interest coverage, DSO / DIO / DPO / CCC) after the balance sheet; FREE CASH FLOW with growth, margins and conversion after the cash flow statement. Use when the user runs /model-ratios TICKER or asks to analyze a base model.
---

# model-ratios

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

Step 3: `/collect-documents` (filings) → `/model-historicals` (MOD tab) → **`/model-ratios`** → `/model-kpis` (it also works
before this one). Everything goes **into the MOD tab**, laid out like the user's own DXCM model (house default),
so each metric sits next to the statement it comes from:

```
INCOME STATEMENT            each line + its % yoy / % margin / bps yoy ... rows underneath
(NON-GAAP METRICS)          /model-kpis's section, left as it is
BALANCE SHEET               subtotals + % yoy / % 2 year / % qoq
ROIC, ROE, ROA              NOPAT, invested capital (asset based, minus cash), averages, ROIC, ROE, ROA
LEVERAGE & CASH CONVERSION  net income TTM, FCF, EBITDA, leverage, interest coverage, days, DSO / DIO / DPO / CCC
CASH FLOW STATEMENT         working capital, operating cash flow, ending cash + growth rows
FREE CASH FLOW              CFO, capex (% of sales), adjustments, FCF + margins / growth, FCF TTM, FCF conversion
```

Existing rows move down to make room. Every formula in the workbook, other tabs included, is re-pointed, so no
existing number changes. There is no ANALYZED tab any more. An old one is left alone, and its links still follow
their rows.

The scripts do the mechanical work; your job is the judgment, and making every judgment visible to the user.
Explain in plain English.


**Saving the model (house default).** The scripts edit with openpyxl but never save with it (openpyxl deletes the user's text boxes, shapes and pictures: 129 of them in the DXCM model). Every save goes through `scripts/safe_save.py`: it replays the logged row moves on the user's raw file, writes only the changed cells, styles and notes, and refuses to write unless the result equals openpyxl's, tab by tab. Never call `wb.save` on the user's model; a new row move must go through the logged insert / delete / remap functions.

**MOD fill convention (house default).** Ordinary rows: quarter cells plain, fiscal-year cells grey; section title rows (text in column A) carry their section colour across every quarter and year; spacer columns and year columns with no quarters (2050E) untouched. `scripts/modfill.py` enforces it: the build runs `fix` after every save and the check fails on any break (`python3 scripts/modfill.py check MODEL`). Never hand-colour MOD cells; if you add or rewrite MOD rows outside the scripts, run `python3 scripts/modfill.py fix MODEL MODEL` and then `check` before saying done.

## Workflow (create a task list with these steps)

`SK` and `SKILLS` are set in the block at the top.

1. **Locate:** `python3 "$SK/locate_model.py" --ticker <T>`.
   - `"status": "build"`: run the `/model-historicals` skill for the ticker (Skill tool, skill `model-historicals`, args `<T>`)
     and follow it fully, then locate again. Run /model-historicals at most once.
   - Set `M=<model>`, `W=<work>`, `SRC=<src>` from the JSON. If `src` is null, tell the user that days in period will
     assume 91 per quarter.
   - If `$W/filings.json` is missing, run
     `python3 "$SKILLS/model-historicals/scripts/extract.py" --src "$SRC" --work "$W"`.
2. **FCF judgment:**
   - Run `python3 "$SK/adjust.py" --work "$W" --list` and read `$W/extract_report.md` (the "Non-obvious mappings"
     CF rows).
   - Look for recurring real cash costs outside capex, for example capitalized software, finance-lease principal
     payments, or capitalized content.
   - Add one only if it is a real, recurring cost of running the business. Write each one to
     `$W/analyze_decisions.json`:
     ```json
     {"notes": [],
      "fcf_adjustments": [{"label": "(-) Capitalized software", "pattern": "capitalized software", "note": "why, in plain English"}],
      "fcf_note": "why no adjustment was needed (when the list is empty)",
      "outlier_notes": {"FY 2020": "one-time valuation-allowance release"}}
     ```
   - `pattern` is a regex on the filing line label. Check it matches the line in `--list`.
   - Default: no adjustments, with `fcf_note` saying why.
3. **Invested capital judgment.** the user's formula (2026-11-06) is **operating assets − non-interest-bearing
   current liabilities**:
   - **Operating assets:** things the business needs to run. For DXCM that is cash, securities, receivables,
     inventory, prepaids, net PP&E, operating-lease ROU assets and goodwill & intangibles. Leave out
     non-operating items (DTAs, investments, "other assets" that aren't part of operations).
   - **Non-interest-bearing current liabilities:** the working-capital items on the liabilities side, almost always
     AP, accrued expenses, accrued payroll, deferred revenue and the current operating-lease liability. Never include
     debt.
   - "Invested Capital (minus cash)" is the same with cash and short-term securities taken out.

   Read the MOD balance sheet, plus the folded / fallback BS rows in `$W/extract_report.md`. Choose the roles,
   then write them to `analyze_decisions.json`:
   ```json
   "invested_capital": {"operating_assets": ["CASH", "STSEC", "AR", "INV", "PRE", "PPE", "ROU", "GWI"],
                        "nibcl": ["AP", "PAY", "OPLLC", "CLOTH"], "note": "why, in plain English"}
   ```
   The roles are model-historicals's BS roles (see its SKILL.md). Without this entry the DXCM default above is used.
   That's fine when the balance sheet looks like DXCM's, but say so in the report. The user's NOPAT doesn't change:
   operating income minus taxes at the year's own effective rate, outliers included.
4. **Write:** `python3 "$SK/analyze.py" --model "$M" --work "$W" --src "$SRC" --decisions "$W/analyze_decisions.json"`.
   - **Exit code 2** means MOD already has analysis sections. **Stop and ask the user.** `--replace` removes this
     skill's rows and rebuilds them:
     - it removes the three sections and every standard analysis row (`% yoy`, `% 2 year`, `% qoq`, `% margin`,
       `% of sales`, `bps yoy`, `incremental margin`) outside the non-GAAP / KPI sections
     - their own differently named rows stay
     - if one of their formulas points into a removed row, it refuses and names the cell
5. **Outlier notes:**
   - Read the "Outlier flags" in `$W/ANALYZE_JUDGMENT_CALLS.md`.
   - For each flagged year, find the likely cause in that year's 10-K markdown (tax note, MD&A). Add it to
     `outlier_notes` (keys like `"FY 2020"`) and rerun step 4 with `--replace`. Nothing else has changed, so that
     is safe.
   - Numbers never change. The user chose the effective tax rate on purpose.
6. **Verify:** `python3 "$SK/verify.py" --model "$M" --work "$W" --src "$SRC" --decisions "$W/analyze_decisions.json"`.
   - It checks every new number against its own maths. It also checks that every pre-existing row still has the
     same values after moving, that only this skill's rows were added, and that other tabs' MOD links followed.
   - It must report 0 failed. If not, fix the cause and rerun. Never hand-edit the output.
   - Once it passes, delete `$W/before_analyze.xlsx` (the copy it compared against): The user keeps no old model versions.
7. **Report:** the judgment calls stay in `$W/ANALYZE_JUDGMENT_CALLS.md` (the user keeps working files in `_model_work`,
   not next to the model). Your final message contains:
   - what was written (sections, years)
   - the invested-capital lines you chose, and why
   - the verification result
   - **every** judgment call and outlier flag, in plain English
   - anything unresolved
   - a reminder to open the file in Excel, where the numbers calculate

## Judgment policy

- Decide, keep going, and **always tell the user**. Every call is a cell comment **and** a line in the judgment-calls
  file. The worst outcome is a call the user never hears about.
- **Never change a number to fix an outlier.** Explain it.
- **Methodology is fixed** (house defaults). Don't change it without asking:
  - % 2 year compounds
  - growth uses `this ÷ last − 1` even across a loss
  - ROIC, ROE, ROA and the days metrics use **average** balances (reconfirmed 2026-11-06)
  - invested capital = operating assets − non-interest-bearing current liabilities, with and without cash
    (2026-11-06; replaced NOWC + fixed assets and debt + equity − cash)
  - NOPAT uses each year's **effective** tax rate
  - EBITDA = operating income + cash-flow D&A
