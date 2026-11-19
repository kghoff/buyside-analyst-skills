import release
import make_fixture as mf


def _lines(variant="normal"):
    return release.parse_text(mf.release_md(variant), "rel.md")


def _get(rel, label):
    return next(l for l in rel["lines"] if l["label"] == label)


def test_statement_kinds_are_told_apart_so_lines_search_the_right_section():
    rel = _lines()
    kinds = {_get(rel, x)["kind"] for x in ("Revenue",)} | {_get(rel, "Total assets")["kind"]}
    assert kinds == {"is", "bs"}
    assert _get(rel, "Net cash provided by operating activities")["kind"] == "cf"
    assert _get(rel, "GAAP gross profit")["kind"] == "recon"
    assert _get(rel, "Units (thousands)")["kind"] == "other"


def test_values_keep_dollar_signs_parentheses_and_dashes_straight():
    rel = _lines()
    assert _get(rel, "Revenue")["values"] == [140.0, 120.0, 380.0, 350.0]
    assert _get(rel, "Purchases of property and equipment")["values"] == [-21.0, -16.0]
    assert _get(rel, "Restructuring")["values"] == [0.0, 0.0, 0.0, 0.0]


def test_thousands_are_scaled_to_millions_but_per_share_is_not():
    """A release in thousands must land in a millions model as millions; EPS is never scaled."""
    rel = _lines("thousands")
    rev = _get(rel, "Revenue")
    assert rev["factor"] == 0.001 and rev["values"][0] * rev["factor"] == 140.0
    assert _get(rel, "Diluted net income per share")["factor"] == 1.0


def test_decimals_set_the_match_tolerance():
    rel = _lines()
    assert _get(rel, "Revenue")["decimals"] == 1 and _get(rel, "Diluted net income per share")["decimals"] == 2
    assert abs(release.tolerance(_get(rel, "Revenue")) - 0.05) < 1e-6


def test_cash_flow_table_is_marked_year_to_date():
    rel = _lines()
    t = rel["tables"][_get(rel, "Net cash provided by operating activities")["table"]]
    assert t["ytd"] is True and rel["tables"][_get(rel, "Revenue")["table"]]["ytd"] is False


def test_every_line_cites_its_file_and_line_number():
    rel = _lines()
    l = _get(rel, "Revenue")
    assert l["file"] == "rel.md" and mf.release_md().split("\n")[l["line"] - 1].startswith("| Revenue |")


# Small 10-Q style tables for the review fixes (the synthetic release stays as the other suites expect it).
TENQ_IS = "\n".join([
    "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS", "",
    "| Three Months Ended September 30, | Nine Months Ended September 30, |", "| --- | --- |",
    "| (In millions, except per share data) | 2026 |  | 2025 |  | 2026 |  | 2025 |",
    "| Net sales | $ | 1,200.5 |  |  | $ | 1,100.2 |  |  | $ | 3,500.0 |  |  | $ | 3,200.0 |  |",
    "| Restructuring | — |  |  | — |  |  | — |  |  | — |  |",
    "| Net loss | (30.4) |  |  | (12.1) |  |  | (50.0) |  |  | (20.0) |  |",
    "| Basic and diluted net loss per share | $ | (0.12) |  |  | $ | (0.05) |  |  | $ | (0.20) |  |  | $ | (0.08) |  |",
    "| Shares used to compute diluted net loss per share | 390.1 |  |  | 392.0 |  |  | 391.0 |  |  | 393.0 |  |",
    "| Net income used for diluted EPS | 30.4 |  |  | 12.1 |  |  | 50.0 |  |  | 20.0 |  |",
    ""])


def test_a_negative_in_one_cell_must_not_shift_the_current_quarter_onto_last_year():
    """'(3,133.4)' in one cell was dropped, so values[0] became last year's number and the model got the wrong quarter."""
    md = "(In millions)\n\n| | Sep 30, 2026 | | Dec 31, 2025 |\n| --- | --- |\n" \
         "| Treasury stock, at cost | (3,133.4) |  |  | (2,084.8) |  |\n| Total assets | 9,000.0 |  |  | 8,000.0 |  |\n"
    l = _get(release.parse_text(md, "q.md"), "Treasury stock, at cost")
    assert l["values"] == [-3133.4, -2084.8] and l["decimals"] == 1


def test_a_number_cell_that_cannot_be_read_drops_the_row_loudly_rather_than_sliding_columns():
    """Skipping one unreadable cell would move every later value one column left; the row is dropped and reported."""
    md = "(In millions)\n\n| | 2026 | | 2025 |\n| --- | --- |\n| Revenue | 1.2.3 |  | 100.0 |\n| Net income | 5.0 |  | 4.0 |\n"
    rel = release.parse_text(md, "q.md")
    assert all(l["label"] != "Revenue" for l in rel["lines"])
    assert rel["tables"][0]["bad"] == [5]


def test_scale_in_the_header_row_is_read_so_a_thousands_10q_is_not_taken_as_millions():
    """10-Qs print '(In thousands...)' as the first header cell, not above the table."""
    rel = release.parse_text(TENQ_IS.replace("In millions", "In thousands"), "q.md")
    t = rel["tables"][0]
    assert t["scale"] == 0.001 and t["scale_known"] is True


def test_blank_lines_do_not_push_the_scale_caption_out_of_reach():
    md = "(In thousands)\n" + "\n" * 12 + "| | 2026 | | 2025 |\n| --- | --- |\n| Revenue | 1,000 |  | 900 |\n"
    assert release.parse_text(md, "q.md")["tables"][0]["scale"] == 0.001


def test_a_table_with_no_scale_inherits_the_previous_tables_and_with_none_is_flagged_unknown():
    """Continuation tables carry no '(In ...)'; a file with no scale at all must be flagged so the user is warned."""
    tbl = "| | 2026 | | 2025 |\n| --- | --- |\n| {} | 1,000 |  | 900 |\n"
    rel = release.parse_text("(In thousands)\n\n" + tbl.format("Revenue") + "\nSome text.\n\n" + tbl.format("Other"), "q.md")
    assert [(t["scale"], t["scale_known"]) for t in rel["tables"]] == [(0.001, True), (0.001, True)]
    t = release.parse_text(tbl.format("Revenue"), "q.md")["tables"][0]
    assert t["scale"] == 1.0 and t["scale_known"] is False


def test_year_header_rows_are_not_data_lines():
    """'(In millions...) | 2026 | 2025' as a line would match a model row that happens to hold 2,026."""
    rel = release.parse_text(TENQ_IS, "q.md")
    assert all(not l["label"].startswith("(In") for l in rel["lines"])
    assert all(not all(1990 <= v <= 2100 for v in l["values"]) for l in rel["lines"])
    yrs = "| | 2026 | | 2025 |\n| --- | --- |\n| Fiscal year | 2026 |  | 2025 |\n| Revenue | 2,026.0 |  | 1,999.0 |\n"
    assert [l["label"] for l in release.parse_text(yrs, "q.md")["lines"]] == ["Revenue"]


def test_share_counts_and_income_used_for_eps_are_scaled_only_eps_itself_is_not():
    """Share counts and 'net income used for diluted EPS' are in the table's units; only per-share amounts are not."""
    rel = release.parse_text(TENQ_IS.replace("In millions", "In thousands"), "q.md")
    assert _get(rel, "Basic and diluted net loss per share")["factor"] == 1.0
    assert _get(rel, "Shares used to compute diluted net loss per share")["factor"] == 0.001
    assert _get(rel, "Net income used for diluted EPS")["factor"] == 0.001


def test_net_sales_and_net_loss_companies_are_still_income_statements():
    """A 'Net sales' / 'Net loss' company must search the income statement, not fall to 'other'."""
    rel = release.parse_text(TENQ_IS, "q.md")
    assert _get(rel, "Net sales")["kind"] == "is"
    cap = "## Consolidated Statements of Earnings\n\n| | 2026 | | 2025 |\n| --- | --- |\n| Sales | 10.0 |  | 9.0 |\n"
    assert release.parse_text(cap, "q.md")["lines"][0]["kind"] == "is"


def test_a_dash_only_row_gets_the_tables_precision_not_a_half_unit_tolerance():
    """Decimals 0 on a '—' row meant +/-0.5 million: a 0.3 model value would wrongly match zero."""
    rel = release.parse_text(TENQ_IS, "q.md")
    assert _get(rel, "Restructuring")["decimals"] == 1


def _lay(md):
    rel = release.parse_text(md, "q.md")
    return rel["tables"][0]["layout"], [(l["cur_i"], l["prior_i"]) for l in rel["lines"]]


def test_the_current_and_prior_columns_come_from_the_header_years():
    """Most releases print this year first; some print last year first. The header says which."""
    assert _lay("(In millions)\n\n| | 2026 | | 2025 |\n| --- | --- |\n| Revenue | 140.0 |  | 120.0 |\n") == ("years", [(0, 1)])
    assert _lay("(In millions)\n\n| | 2025 | | 2026 |\n| --- | --- |\n| Revenue | 120.0 |  | 140.0 |\n") == ("years", [(1, 0)])


def test_the_quarter_columns_are_found_whichever_group_comes_first():
    """'Nine Months | Three Months': the quarter is columns 2-3, not the year-to-date columns 0-1."""
    md = ("(In millions)\n\n|  | Nine Months Ended Sep 30, |  | Three Months Ended Sep 30, |\n| --- | --- | --- |\n"
          "|  | 2026 |  | 2025 |  | 2026 |  | 2025 |\n| Revenue | 380.0 |  | 350.0 |  | 140.0 |  | 120.0 |\n")
    assert _lay(md) == ("years", [(2, 3)])


def test_segment_columns_and_year_to_date_only_tables_have_no_layout():
    """Six values under two years are segment columns; an income statement with only nine-month columns has no
    quarter in it. Either way the matcher must not read values[0] / values[1] as current / prior."""
    seg = ("(In millions)\n\n|  | Three Months Ended Sep 30, |\n| --- | --- |\n| 2026 |  | 2025 |\n"
           "| (In millions) | US |  | Intl |  | Total |  | US |  | Intl |  | Total |\n"
           "| Revenue | 100.0 |  | 40.0 |  | 140.0 |  | 85.0 |  | 35.0 |  | 120.0 |\n")
    assert _lay(seg)[1] == [(None, None)]
    ytd = ("(In millions)\n\n|  | Nine Months Ended Sep 30, |\n| --- | --- |\n|  | 2026 |  | 2025 |\n"
           "| Revenue | 380.0 |  | 350.0 |\n| Net income | 30.0 |  | 20.0 |\n")
    assert _lay(ytd) == ("unknown", [(None, None), (None, None)])
