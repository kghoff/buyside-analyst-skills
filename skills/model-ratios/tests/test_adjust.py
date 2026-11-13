import json
import openpyxl
from openpyxl.utils import column_index_from_string as CI
from adjust import ytd_values, adj_cell, period_ends, quarter_days, list_cf_lines
from periods import Periods

FILINGS = {
    "Q1 22": {"tables": {"CF": [["Capitalized software development costs", [-1.0, -0.5]], ["Other", [2.0, 1.0]]]}},
    "Q2 22": {"tables": {"CF": [["Capitalized software development costs", [-3.0, -1.0]]]}},
    "Q3 22": {"tables": {"CF": [["Capitalized software development costs", [-6.0, -2.0]]]}},
    "FY 22": {"tables": {"CF": [["Capitalized software development costs", [-10.0, -4.0, -1.0]]]}},
    "Q1 23": {"tables": {"CF": [["Other", [1.0, 1.0]]]}},
}


def test_ytd_values_sum_matching_lines_and_default_to_zero():
    v = ytd_values(FILINGS, r"capitalized software")
    assert v["Q2 22"] == -3.0 and v["FY 22"] == -10.0 and v["Q1 23"] == 0.0


def test_quarters_follow_model_base_ytd_rules(mod_path):
    p = Periods(openpyxl.load_workbook(mod_path)["MOD"])
    v = ytd_values(FILINGS, r"capitalized software")
    r = 200
    assert adj_cell(v, p, CI("J"), r) == -1.0                               # Q1 typed
    assert adj_cell(v, p, CI("K"), r) == "=-3-J200"                         # Q2 = 6M - Q1
    assert adj_cell(v, p, CI("L"), r) == "=-6-K200-J200"                    # Q3 = 9M - Q2 - Q1
    assert adj_cell(v, p, CI("M"), r) == "=N200-SUM(J200:L200)"             # Q4 = FY - SUM(Q1:Q3)
    assert adj_cell(v, p, CI("N"), r) == -10.0
    assert adj_cell(v, p, CI("D"), r) is None                               # no filing parsed for Q1 21
    assert adj_cell(v, p, CI("X"), r) is None                               # estimate column


def test_day_counts_from_gather_manifest(tmp_path):
    # /collect-documents labels are year-first ("TEST 2022 Q2 10-Q"); folders gathered earlier still say "TEST Q1 22 10-Q"
    m = {"items": {
        "10-K:2021-12-31": {"label": "TEST 2021 10-K"}, "10-Q:2022-03-31": {"label": "TEST Q1 22 10-Q"},
        "10-Q:2022-06-30": {"label": "TEST 2022 Q2 10-Q"}, "10-K:2022-12-31": {"label": "TEST 2022 10-K"},
        "call:2022Q1": {"label": "Q1 22 TEST call"}}}
    path = tmp_path / "_manifest.json"
    path.write_text(json.dumps(m))
    ends = period_ends(str(path))
    assert quarter_days(ends, 1, 2022) == 90          # Dec 31 -> Mar 31
    assert quarter_days(ends, 2, 2022) == 91
    assert quarter_days(ends, 3, 2022) is None        # Q3 22 10-Q not in the manifest


def test_list_cf_lines_counts_filings():
    lines = dict((lab, n) for lab, n, _ in list_cf_lines(FILINGS))
    assert lines["Capitalized software development costs"] == 4 and lines["Other"] == 2


def test_adj_cell_is_none_when_the_prior_quarter_column_is_missing(mod_path):
    wb = openpyxl.load_workbook(mod_path)
    wb["MOD"]["J2"] = None                                                   # no Q1 22 column
    p = Periods(wb["MOD"])
    v = ytd_values(FILINGS, r"capitalized software")
    assert adj_cell(v, p, CI("K"), 200) is None                             # Q2 needs Q1
    assert adj_cell(v, p, CI("L"), 200) is None                             # Q3 needs Q1 and Q2


def test_ytd_values_skip_rows_with_no_first_value():
    f = {"Q1 22": {"tables": {"CF": [["Capitalized software", [None, 1.0]], ["Capitalized software x", [-2.0]]]}}}
    assert ytd_values(f, "capitalized software")["Q1 22"] == -2.0
