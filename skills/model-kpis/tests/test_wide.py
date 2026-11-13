"""Medtronic-style "wide" reconciliations: one table per period, metrics across the columns, stages down the rows.
These rules decide which number lands in which model cell, so each one is pinned here."""
from ng_extract import wide_cells, wide_tables, wide_candidates

HDR = ("| (in millions, except per share data) | Net Sales |  | Cost of Products Sold |  | Gross Margin Percent |  | "
       "Operating Profit |  | Operating Profit Percent |  | Income Before Income Taxes |  | Net Income attributable to Medtronic |  | "
       "Diluted EPS |  | Effective Tax Rate |")


def table(caption, rows):
    return "\n".join(["GAAP TO NON-GAAP RECONCILIATIONS", "", f"|  | {caption} |", "| --- | --- |", HDR] + rows) + "\n"


NEW = table("Three months ended July 25, 2025", [
    "| GAAP | $ | 8,578 |  |  | $ | 3,001 |  |  | 65.0 | % |  | $ | 1,445 |  |  | 16.8 | % |  | $ | 1,300 |  |  | $ | 1,040 |  |  | $ | 0.81 |  |  | 19.0 | % |",
    "| Non-GAAP adjustments: |  |  |  |",
    "| Amortization of intangible assets | — |  |  | — |  |  | — |  |  | 459 |  |  | 5.4 |  |  | 459 |  |  | 374 |  |  | 0.29 |  |  | 18.5 |  |",
    "| Restructuring and associated costs | — |  |  | (16) |  |  | 0.2 |  |  | 67 |  |  | 0.8 |  |  | 67 |  |  | 51 |  |  | 0.04 |  |  | 23.9 |  |",
    "| Other | (39) |  |  | — |  |  | (0.2) |  |  | (39) |  |  | (0.3) |  |  | (39) |  |  | (30) |  |  | (0.02) |  |  | 23.1 |  |",
    "| Non-GAAP | $ | 8,539 |  |  | $ | 2,985 |  |  | 65.0 | % |  | $ | 1,932 |  |  | 22.6 | % |  | $ | 1,787 |  |  | $ | 1,436 |  |  | $ | 1.12 |  |  | 19.6 | % |",
    "| Currency impact | (159) |  |  | (46) |  |  | (0.1) |  |  |  |  |  |  | 0.3 |  |"])
# FY2017 layout: adjustment rows leave the two margin-% columns empty; negatives split as '(10 | )'
OLD = table("Three months ended July 29, 2016", [
    "| GAAP | $ | 7,166 |  |  | $ | 2,261 |  |  | 68.4 | % |  | $ | 1,167 |  |  | 16.3 | % |  | $ | 988 |  |  | $ | 929 |  |  | $ | 0.66 |  |  | 6.0 | % |",
    "| Restructuring charges, net | — |  |  | (10 | ) |  |  |  | 104 |  |  |  |  | 104 |  |  | 79 |  |  | 0.06 |  |  | 24.0 |  |",
    "| Non-GAAP | $ | 7,166 |  |  | $ | 2,251 |  |  | 68.6 | % |  | $ | 1,271 |  |  | 17.7 | % |  | $ | 1,092 |  |  | $ | 1,008 |  |  | $ | 0.72 |  |  | 14.0 | % |"])


def test_cells_merge_dollar_signs_split_negatives_and_percent_marks():
    lab, vals = wide_cells("| Restructuring charges, net | — |  |  | (10 | ) |  | 104 | 24.0 | % |")
    assert lab == "Restructuring charges, net" and vals == [(0.0, False), (-10.0, False), (104.0, False), (24.0, True)]


def test_short_adjustment_rows_map_to_the_non_margin_columns():
    t = wide_tables(OLD)[0]
    row = dict((lab, r) for _, lab, r in t["rows"])["Restructuring charges, net"]
    # without this, 104 would land in 'gross margin percent' and every later column would shift
    assert row["cost of products sold"] == -10 and row["operating profit"] == 104 and row["net income attributable to medtronic"] == 79
    assert "gross margin percent" not in row


def test_gross_profit_counts_net_sales_adjustments_and_rounding_is_left_for_main():
    s = {"path": "x.md", "type": "release"}
    cands, unresolved = wide_candidates(NEW, s, "Q1 26", lambda p: {"Q1 26": 8578.0, "Q1 25": 7900.0}.get(p))
    gp = next(c for c in cands if c["metric"] == "non-gaap gross profit")
    assert gp["period"] == "Q1 26" and gp["vintage"] == "current"
    assert gp["start"] == 8578 - 3001 and gp["end"] == 8539 - 2985
    # 'Other' cut net sales by 39 with no cost change: gross profit falls 39; restructuring cost (16) adds 16
    assert dict((lab, v) for lab, v, _ in gp["items"]) == {"Restructuring and associated costs": 16.0, "Other": -39.0}
    oi = next(c for c in cands if c["metric"] == "non-gaap operating income")
    assert sum(v for _, v, _ in oi["items"]) == 1932 - 1445          # margin-% column never mixed into the amounts
    eps = next(c for c in cands if c["metric"] == "reported non-gaap eps")
    assert eps["value"] == 1.12


def test_period_is_the_closest_revenue_match_not_the_first():
    # Q4 FY18 and Q4 FY19 revenue were $2M apart at Medtronic; the prior-year table must not land on Q4 FY19
    s = {"path": "x.md", "type": "release"}
    cands, _ = wide_candidates(NEW, s, "Q1 26", lambda p: {"Q1 26": 8580.0, "Q1 25": 8578.0}.get(p))
    assert {c["period"] for c in cands} == {"Q1 25"}


def test_loss_quarter_headers_still_map():
    # Q3 FY18 (U.S. Tax Act charge): the columns read 'Net (Loss) Income attributable to Medtronic' and 'Diluted
    # (LPS) EPS'; missing them left that quarter's non-GAAP net income and EPS blank in the model
    txt = NEW.replace("Net Income attributable to Medtronic", "Net (Loss) Income attributable to Medtronic").replace("Diluted EPS", "Diluted (LPS) EPS")
    t = wide_tables(txt)[0]
    assert "net income attributable to medtronic" in t["metrics"] and "diluted eps" in t["metrics"]


def test_loss_quarter_uses_the_footnote_share_count():
    # GAAP diluted shares equal basic in a loss quarter; non-GAAP EPS divides by the larger diluted count the footnote
    # states. Using 1,354.0 instead of 1,364.5 made Q3 FY18 non-GAAP EPS $1.18 vs the reported $1.17.
    from ng_extract import wide_shares
    txt = ("| Basic weighted average shares outstanding | 1,354.0 |  | 1,372.2 |\n"
           "| Diluted weighted average shares outstanding | 1,354.0 |  | 1,383.1 |\n"
           "| (2) | GAAP diluted LPS ... Non-GAAP diluted EPS for the respective period is calculated using diluted weighted "
           "average shares of 1,364.5 million as the Company had non-GAAP net income for the period. |\n")
    out = wide_shares(txt, {"path": "x.md", "type": "release"}, "Q3 18")
    cur = [c for c in out if c["period"] == "Q3 18"]
    assert len(cur) == 1 and cur[0]["value"] == 1364.5
    assert any(c["period"] == "Q3 17" and c["value"] == 1383.1 for c in out)


def test_footnote_about_the_prior_year_quarter_is_ignored():
    # the Q3 FY19 release repeats the Q3 FY18 footnote; its own quarter was profitable (diluted > basic)
    from ng_extract import wide_shares
    txt = ("| Basic weighted average shares outstanding | 1,345.0 |  | 1,354.0 |\n"
           "| Diluted weighted average shares outstanding | 1,356.0 |  | 1,354.0 |\n"
           "| (2) | Non-GAAP diluted EPS for the respective period is calculated using diluted weighted average shares of 1,364.5 million |\n")
    out = wide_shares(txt, {"path": "x.md", "type": "release"}, "Q3 19")
    assert [c["value"] for c in out if c["period"] == "Q3 19"] == [1356.0]
