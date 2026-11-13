import openpyxl
from openpyxl.utils import column_index_from_string as CI
from periods import parse_period, Periods


def test_parse_period():
    assert parse_period("Q1 16") == (1, 2016, False)
    assert parse_period("Q4 26E") == (4, 2026, True)
    assert parse_period(2016) == (0, 2016, False)
    assert parse_period("2026E") == (0, 2026, True)
    assert parse_period(None) is None and parse_period("Units") is None and parse_period(90) is None


def test_compare_columns(mod_path):
    p = Periods(openpyxl.load_workbook(mod_path)["MOD"])
    col = CI
    assert p.yoy(col("P")) == col("J")                      # Q1 23 vs Q1 22
    assert p.two_year(col("P")) == col("D")                 # Q1 23 vs Q1 21
    assert p.yoy(col("N")) == col("H")                      # 2022 vs 2021
    assert p.qoq(col("J")) == col("G")                      # Q1 looks back to last year's Q4 (macro CompareCol)
    assert p.qoq(col("K")) == col("J")
    assert p.qoq(col("N")) is None                          # FY columns get no qoq
    assert p.yoy(col("D")) is None                          # first year has no comparison
    assert p.yoy(col("X")) == col("R")                      # Q3 24E vs Q3 23 (estimate compares to reported)


def test_ttm_and_averages(mod_path):
    p = Periods(openpyxl.load_workbook(mod_path)["MOD"])
    col = CI
    assert p.ttm(col("K")) == [col("K"), col("J"), col("G"), col("F")]   # Q2 22 + Q1 22 + Q4 21 + Q3 21
    assert p.ttm(col("F")) is None                                       # Q3 21: fewer than 4 quarters of history
    assert p.ttm(col("N")) == [col("N")]                                 # FY = the year itself (TTMRow macro)
    assert p.prev_end(col("J")) == col("G")                              # quarter -> prior quarter-end
    assert p.prev_end(col("N")) == col("H")                              # FY -> prior FY-end
    assert p.prev_end(col("H")) is None


def test_fiscal_year_lookups(mod_path):
    p = Periods(openpyxl.load_workbook(mod_path)["MOD"])
    col = CI
    assert p.fy_col(col("J")) == col("N") and p.fy_col(col("V")) == col("Z")
    assert p.is_est(col("Z")) and not p.is_est(col("V"))
    assert p.latest_reported_fy() == col("T")
    assert p.label(col("T")) == "FY 2023" and p.label(col("X")) == "Q3 24E"
