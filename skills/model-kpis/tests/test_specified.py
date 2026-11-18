"""'Specified items' reconciliations (Abbott): one table per period, the line items down the rows, three columns across
(As Reported (GAAP) | Specified Items | As Adjusted), plus a 'Details of Specified Items' table that splits each line's
adjustment by category. Without this reader the extractor found no reconciliations at all for such a company."""
from ng_extract import specified_candidates

SUMMARY_Q3_26 = """Non-GAAP Reconciliation of Financial Information

Third Quarter Ended September 30, 2026 and 2025

|  | 3Q26 |
| --- | --- |
|  | As Reported (GAAP) |  | Specified Items |  | As Adjusted |  |  |
| Intangible Amortization | $ | 841 |  |  | $ | (841) |  |  | $ | — |  |  |  |
| Gross Margin | 6,544 |  |  | 904 |  |  | 7,448 |  |  |  |
| R&D | 920 |  |  | (28) |  |  | 892 |  |  |  |
| SG&A | 4,266 |  |  | (761) |  |  | 3,505 |  |  |  |
| Other (income) expense, net | (164) |  |  | 4 |  |  | (160) |  |  |  |
| Earnings before taxes | 1,231 |  |  | 1,689 |  |  | 2,920 |  |  |  |
| Taxes on Earnings | 311 |  |  | 132 |  |  | 443 |  |  |  |
| Net Earnings | 920 |  |  | 1,557 |  |  | 2,477 |  |  |  |
| Diluted Earnings per Share | $ | 0.53 |  |  | $ | 0.89 |  |  | $ | 1.42 |  |  |  |

Specified items reflect intangible amortization expense of $841 million.

|  | 3Q25 |
| --- | --- |
|  | As Reported (GAAP) |  | Specified Items |  | As Adjusted |  |  |
| Intangible Amortization | $ | 420 |  |  | $ | (420) |  |  | $ | — |  |  |  |
| Gross Margin | 6,000 |  |  | 450 |  |  | 6,450 |  |  |  |
| Earnings before taxes | 2,000 |  |  | 548 |  |  | 2,548 |  |  |  |
| Taxes on Earnings | 300 |  |  | 60 |  |  | 360 |  |  |  |
| Net Earnings | 1,700 |  |  | 488 |  |  | 2,188 |  |  |  |
| Diluted Earnings per Share | $ | 0.97 |  |  | $ | 0.28 |  |  | $ | 1.25 |  |  |  |

|  | 9M26 |
| --- | --- |
|  | As Reported (GAAP) |  | Specified Items |  | As Adjusted |  |  |
| Gross Margin | 19,000 |  |  | 2,500 |  |  | 21,500 |  |  |  |
| Net Earnings | 2,925 |  |  | 3,864 |  |  | 6,789 |  |  |  |

Details of Specified Items

Third Quarter Ended September 30, 2026

(in millions, except per share data)

|  | Acquisition or Divestiture- related (a) |  | Restructuring and Cost Reduction Initiatives (b) |  | Intangible Amortization |  | Other (c) |  | Total Specifieds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gross Margin | $ | 10 |  |  | $ | 29 |  |  | $ | 841 |  |  | $ | 24 |  |  | $ | 904 |  |
| R&D | (7) |  |  | (5) |  |  | — |  |  | (16) |  |  | (28) |  |
| SG&A | (47) |  |  | (20) |  |  | — |  |  | (694) |  |  | (761) |  |
| Other (income) expense, net | (8) |  |  | (1) |  |  | — |  |  | 13 |  |  | 4 |  |
| Earnings before taxes | $ | 72 |  |  | $ | 55 |  |  | $ | 841 |  |  | $ | 721 |  |  | 1,689 |  |
| Taxes on Earnings (d) |  |  |  |  |  |  |  |  | 132 |  |
| Net Earnings |  |  |  |  |  |  |  |  | $ | 1,557 |  |
| Diluted Earnings per Share |  |  |  |  |  |  |  |  | $ | 0.89 |  |
"""

# 2016-2019 layout: 'AsReported(GAAP)' run together, negatives split '(483 | )', continuing-operations labels,
# an extra adjusted line (debt extinguishment) between SG&A and pre-tax earnings
SUMMARY_Q4_19 = """|  | 4Q19 |  |
| --- | --- | --- |
|  |  | AsReported(GAAP) |  |  |  | SpecifiedItems |  |  |  | AsAdjusted |  |  |  | % toSales |  |
| Intangible Amortization | $ | 483 |  |  | $ | (483 | ) |  |  | — |  |  |  |  |  |
| Gross Margin |  | 4,397 |  |  |  | 545 |  |  |  | 4,942 |  |  |  | 59.4 | % |
| Debt extinguishment costs |  | 63 |  |  |  | (63 | ) |  |  | — |  |  |  |  |  |
| Earnings from Continuing Operations before taxes |  | 1,240 |  |  |  | 714 |  |  |  | 1,954 |  |  |  |  |  |
| Tax expense on Earnings from Continuing Operations |  | 191 |  |  |  | 58 |  |  |  | 249 |  |  |  |  |  |
| Earnings from Continuing Operations |  | 1,049 |  |  |  | 656 |  |  |  | 1,705 |  |  |  |  |  |
| Diluted Earnings per Share from Continuing Operations | $ | 0.59 |  |  | $ | 0.36 |  |  | $ | 0.95 |  |  |  |  |  |
"""

S = {"path": "Press Releases/_md/2026 Q3 X release.md", "type": "release"}
# the model's gross profit is sales - cost of sales; the company's 'Gross Margin' is after intangible amortization
MODEL = {("gross profit", "Q3 26"): 7385.0, ("gross profit", "Q3 25"): 6420.0, ("gross profit", "Q4 19"): 4880.0}
model_of = lambda metric, per: MODEL.get((metric, per))


def by(cands, metric, period):
    return next(c for c in cands if c["metric"] == metric and c["period"] == period)


def test_each_table_is_a_period_from_its_own_header_and_year_to_date_is_skipped():
    cands, unresolved = specified_candidates(SUMMARY_Q3_26, S, "Q3 26", model_of)
    assert {(c["period"], c["vintage"]) for c in cands} == {("Q3 26", "current"), ("Q3 25", "comparative")}
    assert not unresolved


def test_net_income_bridge_uses_the_detail_categories_and_the_tax_on_them():
    cands, _ = specified_candidates(SUMMARY_Q3_26, S, "Q3 26", model_of)
    ni = by(cands, "non-gaap net income", "Q3 26")
    assert ni["start"] == 920 and ni["end"] == 2477 and ni["start_metric"] == "net income"
    items = {lab: v for lab, v, _ in ni["items"]}
    # pre-tax by category from the details table, then the tax on specified items as a deduction
    assert items == {"Acquisition or Divestiture-related": 72, "Restructuring and Cost Reduction Initiatives": 55,
                     "Intangible Amortization": 841, "Other": 721, "Tax effect of specified items": -132}


def test_gross_profit_starts_where_the_model_does_and_never_adds_amortization_twice():
    cands, _ = specified_candidates(SUMMARY_Q3_26, S, "Q3 26", model_of)
    gp = by(cands, "non-gaap gross profit", "Q3 26")
    # the company's GAAP gross margin 6,544 + its amortization line 841 = the model's gross profit 7,385;
    # the amortization category is then already in the start, so only the other categories bridge to 7,448
    assert gp["start"] == 7385 and gp["end"] == 7448
    assert {lab: v for lab, v, _ in gp["items"]} == {"Acquisition or Divestiture-related": 10,
                                                     "Restructuring and Cost Reduction Initiatives": 29, "Other": 24}
    # no details table for the comparative column: one 'specified items' line, less the amortization
    gp25 = by(cands, "non-gaap gross profit", "Q3 25")
    assert gp25["start"] == 6420 and sum(v for _, v, _ in gp25["items"]) == 6450 - 6420


def test_adjusted_eps_is_the_as_adjusted_column():
    cands, _ = specified_candidates(SUMMARY_Q3_26, S, "Q3 26", model_of)
    assert by(cands, "reported non-gaap eps", "Q3 26")["value"] == 1.42


def test_older_layout_with_split_negatives_and_continuing_operations():
    s = {"path": "Press Releases/_md/2019 Q4 X release.md", "type": "release"}
    cands, unresolved = specified_candidates(SUMMARY_Q4_19, s, "Q4 19", model_of)
    ni = by(cands, "non-gaap net income", "Q4 19")
    assert ni["start"] == 1049 and ni["end"] == 1705 and not unresolved
    assert {lab: v for lab, v, _ in ni["items"]} == {"Specified items before tax": 714, "Tax effect of specified items": -58}
    assert by(cands, "reported non-gaap eps", "Q4 19")["value"] == 0.95


def test_continuing_operations_bridge_starts_from_the_models_net_income():
    # 2016-2020 tables start from earnings from continuing operations; the model's net income includes discontinued
    # operations. Skipping those columns left five years without adjusted EPS. The bridge now starts from the model's
    # net income and takes discontinued operations out first (the builder links that row to the model's own row).
    s = {"path": "Press Releases/_md/2019 Q4 X release.md", "type": "release"}
    model = {("net income", "Q4 19"): 1069.0, ("discontinued operations", "Q4 19"): 20.0}
    cands, _ = specified_candidates(SUMMARY_Q4_19, s, "Q4 19", lambda m, p: model.get((m, p)))
    ni = by(cands, "non-gaap net income", "Q4 19")
    assert ni["start"] == 1069 and ni["end"] == 1705
    assert ni["items"][0][:2] == ("Discontinued operations, net of tax", -20.0)
    assert ni["start"] + sum(v for _, v, _ in ni["items"]) == 1705


def test_earnings_loss_wording_still_maps():
    # Q3 17 printed 'Earnings (Loss) from Continuing Operations' and 'Diluted Earnings (Loss) per Share ...': missing
    # them dropped that quarter's net income and EPS (and with them FY17)
    txt = SUMMARY_Q4_19.replace("Earnings from Continuing", "Earnings (Loss) from Continuing").replace("Diluted Earnings per", "Diluted Earnings (Loss) per")
    s = {"path": "Press Releases/_md/2019 Q4 X release.md", "type": "release"}
    cands, _ = specified_candidates(txt, s, "Q4 19", model_of)
    assert by(cands, "non-gaap net income", "Q4 19")["end"] == 1705 and by(cands, "reported non-gaap eps", "Q4 19")["value"] == 0.95


def test_benefit_wording_and_net_earnings_from_continuing_operations():
    # Q1 19 'Tax expense (benefit) on ...' and 2016's 'Net Earnings from Continuing Operations' each dropped a quarter
    txt = SUMMARY_Q4_19.replace("| Tax expense on", "| Tax expense (benefit) on").replace("| Earnings from Continuing Operations |", "| Net Earnings from Continuing Operations |")
    s = {"path": "Press Releases/_md/2019 Q4 X release.md", "type": "release"}
    cands, _ = specified_candidates(txt, s, "Q4 19", model_of)
    assert by(cands, "non-gaap net income", "Q4 19")["end"] == 1705


def test_share_count_label_split_over_two_rows():
    # Q4 20 - Q2 22 releases print the label on two table rows with the counts on the second. Missing them left Q4 20
    # and Q1 21 non-GAAP EPS blank, which blanked a year of the price-history P/E chart (ABT, 2026-11-18).
    from ng_extract import spec_shares
    text = """|  |  |  | 4Q20 |  |  |  | 4Q19 |  |  | % Change |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Net Sales |  | $ | 10,701 |  |  | $ | 8,314 |  |  | 28.7 |  |
| Average Number of Common Shares Outstanding |  |  |  |  |  |  |  |  |  |  |  |
| Plus Dilutive Common Stock Options |  |  | 1,789 |  |  |  | 1,781 |  |  |  |  |
"""
    got = {c["period"]: (c["value"], c["line"]) for c in spec_shares(text, S, None)}
    assert got == {"Q4 20": (1789, 5), "Q4 19": (1781, 5)}
