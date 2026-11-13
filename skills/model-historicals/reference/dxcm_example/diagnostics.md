# Diagnostics

## A. Segments (any change = STOP and ask the user)

**No change detected**

| 10-K | segment counts mentioned | first mention |
|---|---|---|
| 2014 | one | Segment Reporting and Geographic Information

An operating segment is identified as a component of a business that has discrete financial informat |
| 2015 | one | Segment Reporting and Geographic Information

An operating segment is identified as a component of a business that has discrete financial informat |
| 2016 | one | Segment Reporting and Geographic Information

An operating segment is identified as a component of a business that has discrete financial informat |
| 2017 | one | Segment Reporting and Geographic Information

An operating segment is identified as a component of a business that has discrete financial informat |
| 2018 | one | Business Segment and Geographic Information

Reportable Segments

An operating segment is identified as a component of a business that has discrete financial in |
| 2019 | one | Reportable Segments

An operating segment is identified as a component of a business that has discrete financial informat |
| 2020 | one | Reportable Segments

An operating segment is identified as a component of a business that has discrete financial informat |
| 2021 | one | Reportable Segments

An operating segment is identified as a component of a business that has discrete financial informat |
| 2022 | one | Reportable Segments

An operating segment is identified as a component of a business that has discrete financial informat |
| 2023 | one | ovember 2023, the FASB issued Accounting Standards Update (ASU) 2023-07, Segment Reporting (Topic 280): Improvements to Reportable Segment Disclosures |
| 2024 | one | rds Board, or FASB, issued Accounting Standards Update, or ASU, 2023-07, Segment Reporting (Topic 280): Improvements to Reportable Segment Disclosures |
| 2025 | one | We manage our business on a global consolidated basis within one operating and one reportable segment, which is consistent with how our chief operating decision |

## B. Stock splits (share counts restated in later filings)

| Restated in | Period | Item | Originally | Restated | Ratio |
|---|---|---|---|---|---|
| Q2 22 | Q2 21 | Shares basic | 96.7 | 386.9 | 4.00x |
| Q2 22 | Q2 21 | Shares diluted | 99.6 | 427.1 | 4.29x |
| Q3 22 | Q3 21 | Shares basic | 96.9 | 387.4 | 4.00x |
| Q3 22 | Q3 21 | Shares diluted | 100.5 | 430.3 | 4.28x |
| FY 22 | FY 21 | Shares basic | 96.7 | 386.9 | 4.00x |
| FY 22 | FY 21 | Shares diluted | 100.1 | 428.8 | 4.28x |
| Q1 23 | Q1 22 | Shares basic | 97.2 | 388.9 | 4.00x |
| Q1 23 | Q1 22 | Shares diluted | 107.2 | 428.7 | 4.00x |

First filing with split-adjusted comparatives: **Q2 22** (ratio 4.00x). Every period whose own filing came before it needs its share counts multiplied. Suggested decisions.json entry:

```json
"share_splits": [{"through_period": "Q1 22", "factor": 4, "note": "<n>-for-1 split; pre-split share counts multiplied so EPS is comparable"}]
```

## C. Restatements / reclassifications (a later filing shows different numbers for a period)

Default policy: keep each period **as originally filed** (internally consistent quarters). Decide case by case and log it.

| Period | Item | As originally filed | In later filing | Later filing |
|---|---|---|---|---|
| Q1 21 | Net income | 40.3 | 56.5 | Q1 22 |
| FY 21 | Total assets | 4863.6 | 4933.3 | Q1 22 |
| FY 21 | Total liabilities | 2612.1 | 2891.2 | Q1 22 |
| FY 21 | Equity | 2251.5 | 2042.1 | Q1 22 |
| Q2 21 | Net income | 62.9 | 78.4 | Q2 22 |
| FY 21 | Total assets | 4863.6 | 4933.3 | Q2 22 |
| FY 21 | Total liabilities | 2612.1 | 2891.2 | Q2 22 |
| FY 21 | Equity | 2251.5 | 2042.1 | Q2 22 |
| Q3 21 | Net income | 70.9 | 87.3 | Q3 22 |
| FY 21 | Total assets | 4863.6 | 4933.3 | Q3 22 |
| FY 21 | Total liabilities | 2612.1 | 2891.2 | Q3 22 |
| FY 21 | Equity | 2251.5 | 2042.1 | Q3 22 |
| FY 21 | Net income | 154.7 | 216.9 | FY 22 |
| FY 21 | Total assets | 4863.6 | 4933.3 | FY 22 |
| FY 21 | Total liabilities | 2612.1 | 2891.2 | FY 22 |
| FY 21 | Equity | 2251.5 | 2042.1 | FY 22 |

## D. Accounting standards each 10-K says were adopted

Read the 'Recently adopted' note for any ASU that lines up with a restatement in C.

| ASU | 10-K years mentioning adoption | snippet |
|---|---|---|
| 2016-02 | 2019 | See Note 6, “Leases and Other Commitments” for more information on the impact of our adoption of ASU 2016-02 and related disclosures |
| 2016-09 | 2017, 2018 | As discussed under "Recent Accounting Guidance", we adopted ASU 2016-09, Compensation - Stock Compensation (Topic 718) (“ASU 2016-09”) in the first quarter of 2017 and elected to account for forfeitures as they occur wit |
| 2016-13 | 2020 | Our adoption of ASU 2016-13 at the beginning of the first quarter of 2020 did not have a significant impact on our consolidated financial statements |
| 2016-16 | 2018 | deferred tax assets, our adoption of the provisions of ASU 2016-16 in 2018 did not have a significant impact on our financial statements |
| 2017-04 | 2020 | Our adoption of ASU 2017-04 at the beginning of the first quarter of 2020 did not have a significant impact on our consolidated financial statements |
| 2017-12 | 2019 | Our adoption of ASU 2017-12 at the beginning of the first quarter of 2019 did not have a significant impact on our consolidated financial statements |
| 2018-07 | 2018 | We elected to early adopt ASU 2018-07 in the third quarter of 2018 and our adoption of this guidance did not have a significant impact on our financial statements |
| 2018-13 | 2020 | Our adoption of ASU 2018-13 at the beginning of the first quarter of 2020 did not have a significant impact on our consolidated financial statements |
| 2018-15 | 2020 | Our adoption of ASU 2018-15 at the beginning of the first quarter of 2020 did not have a significant impact on our consolidated financial statements |
| 2019-12 | 2021 | Our adoption of ASU 2019-12 at the beginning of the first quarter of 2021 did not have a significant impact on our consolidated financial statements |
| 2020-06 | 2022 | Since we adopted ASU 2020-06 using the full retrospective approach, we were required to apply the guidance to all convertible debt instruments we had outstanding as of January 1, 2020 |
| 2021-08 | 2023 | We adopted ASU 2021-08 in the first quarter of 2023 and there was no impact to our consolidated financial statements |
| 2023-07 | 2024 | We adopted ASU 2023-07 in the fourth quarter of 2024 on a retrospective basis, reflecting the application of the new standard in each prior reporting period |
| 2023-09 | 2025 | F-37 * * * The reconciliation between our effective tax rate on income from continuing operations and the statutory rate, after the adoption of ASU 2023-09 on a prospective basis, is as follows: | | Twelve Months EndedDe |

## E. Income-statement line changes between 10-Ks

- **15**: added ['income tax expense']; removed ['income tax expense (benefit)', 'interest and other income']
- **16**: added ['interest income', 'other expense']; removed -
- **17**: added ['cost of sales', 'other income (expense)']; removed ['development and other cost of sales', 'other expense', 'product cost of sales', 'total cost of sales']
- **18**: added ['collaborative research and development fee', 'income from equity investments', 'interest and other income (expense), net', 'revenue']; removed ['development grant and other revenue', 'interest income', 'other income (expense)', 'product revenue', 'total revenue']
- **19**: added ['income (loss) before income taxes', 'income (loss) from equity investments', 'interest and other income, net', 'net income (loss)', 'operating income (loss)']; removed ['income from equity investments', 'interest and other income (expense), net', 'loss before income taxes', 'net loss', 'operating loss']
- **20**: added ['income tax expense (benefit)', 'loss on extinguishment of debt']; removed ['income tax expense']
- **21**: added ['income before income taxes', 'interest and other income (expense), net', 'net income', 'operating income']; removed ['income (loss) before income taxes', 'interest and other income, net', 'net income (loss)', 'operating income (loss)']
- **22**: added ['amortization of intangible assets', 'income from equity investments']; removed ['income (loss) from equity investments']
- **23**: added ['income tax expense', 'other income (expense), net']; removed ['amortization of intangible assets', 'income from equity investments', 'income tax expense (benefit)', 'interest and other income (expense), net', 'interest expense', 'loss on extinguishment of debt']
- **24**: added -; removed ['collaborative research and development fee']
- **25**: added ['other income, net']; removed ['other income (expense), net']
