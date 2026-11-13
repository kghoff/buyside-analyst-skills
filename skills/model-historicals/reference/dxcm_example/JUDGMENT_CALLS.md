# DXCM model - judgment calls

Model: DXCM_model.xlsx | FY2016-FY2025 + 3 reported quarter(s) of 2026

## Decisions

- ASU 2020-06 (convertible notes, adopted 2022 full-retrospective): kept 2020-2021 as originally filed so each year's quarters sum to the year; 2022+ on the new basis (the user approved for DXCM).
- **Value override:** FY 21 GWI = 26.5+31.5 - 10-K combined 'Intangibles and other assets'; 2022 10-K splits Dec-21 into intangibles 31.5 + other 10.5
- **Value override:** FY 21 OTHA = 10.5 - see above
- **Template rows:** 28 optional rows not reported by this company were left out - ACCR, ACQEXP, CAPSW, DEFREVLT, DISCOPS, DIV, DIVEST, DTL, EQAFF_AT, GA, GAINOP, IMPAIR, ISDA, LITIG, LTINV, MEZZ, NCI_IS, NCTL, NI_COMMON, OCA, OTHOPEX, PENSION, PREFDIV, RESTR, SM, TAXPAY, W_OTHAL, W_TAX
- **Stock split:** share counts through Q1 22 x4 - 4-for-1 split June 2022; pre-split share counts x4 so EPS is comparable
- **Q4 share source:** Q4 17 - no Q4 release with share counts for Q4 17; used 2018 Q4 DXCM release 2019-02-21 EX-99.01.md (prior-year column)

## Filing lines mapped to a broader model row

| Stmt | Filing line | Model row | Type | Periods |
|---|---|---|---|---|
| BS | Intangibles and other assets, net | OTHA | fallback | Q3 21 - Q3 21 (1) |
| BS | decisions.json override | GWI | override | FY 21 - FY 21 (2) |
| BS | decisions.json override | OTHA | override | FY 21 - FY 21 (1) |
| CF | Accretion and amortization related to marketable securities, net | OTHNC | fallback | Q1 16 - Q3 16 (3) |
| CF | Collaborative research and development fee | OTHNC | fallback | FY 21 - FY 23 (3) |
| CF | Loss on extinguishment of debt | OTHNC | fold | Q2 20 - FY 23 (8) |
| CF | Non-cash collaborative research and development fee through issuance of common stock | OTHNC | fallback | FY 18 - FY 20 (3) |
| CF | Non-cash research and development charge through issuance of common stock | OTHNC | fallback | Q3 16 - FY 17 (3) |
| CF | Payments for taxes related to net share settlement of equity awards | STOCK | fold | Q1 26 - Q3 26 (3) |
| CF | Payments on acquisition related contingent consideration liability | OTHFIN | fold | Q2 18 - Q3 19 (3) |
| CF | Purchases of non-marketable equity securities | OTHINV | fallback | FY 24 - Q3 26 (6) |
| CF | Restricted cash | W_OTHAL | fallback | Q2 16 - FY 17 (4) |
