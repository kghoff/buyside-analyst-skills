# DXCM example

A full run of the skills on DexCom (DXCM), as of the Q3 2026 results.

| File | What it is |
|---|---|
| `DXCM_model.xlsx` | The company model: 10 years of quarterly and annual statements with the analysis, non-GAAP and KPI history, and a driver-based forecast (all on the MOD tab), plus the price-history, filings-research charts, industry, DCF and consensus tabs. |
| `DXCM Filings Research Report.pdf` | The filings research report (about 100 pages): what the company's own documents say, the three key drivers and how to forecast them. |

## How they were built

The skills ran in this order:

1. `collect-documents`: every 10-K, 10-Q, earnings release, call transcript, deck and proxy, saved as Markdown.
2. `model-historicals`: the income statement, balance sheet and cash flow on the MOD tab.
3. `model-ratios`: growth, margins, ROIC, leverage and free cash flow under each statement.
4. `model-kpis`: the non-GAAP reconciliations and key operating metrics.
5. `model-price-history`: the Px Data, Px Events and Idio Chart tabs.
6. `research-filings`: the PDF report, and the Filings Charts tab and stock tables in the model.
7. `research-street`: outside views checked against the company's claims (the report is not included here).
8. `model-forecast`: the quarterly 3-statement forecast on the MOD tab.
9. `model-industry`: the Industry P&L and Industry Comparison tabs.
10. `model-dcf`: the 30-year DCF tab.
11. `model-consensus`: the Consensus tab.

The Research, CAPM, DCF Cheat Sheet and G8 Rebate Watch tabs were built by hand, not by the skills.

## What is left out

- **Per-broker estimates are blank on purpose.** In a normal run, `model-consensus` types each broker's own EPS and
  revenue estimates from their reports. Those reports are paid research, so the example keeps the free ratings,
  price targets and consensus figures and leaves the per-broker estimate columns empty.
- **The street research report is not included.** It quotes paid broker research at length.
- A few forecast notes in the model, and one figure in the report, cite short excerpts from broker reports, with
  the firm and date.
