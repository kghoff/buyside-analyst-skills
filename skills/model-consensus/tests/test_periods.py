# tests/test_periods.py
from datetime import date

import periods
from conftest import snap


def test_december_year_end():
    assert periods.qlabel(date(2026, 12, 31), 12) == "Q4 26"
    assert periods.qlabel(date(2027, 3, 31), 12) == "Q1 27"
    assert periods.fylabel(date(2027, 12, 31), 12) == "FY 27"


def test_april_year_end_names_the_year_by_its_end():
    # a fiscal year ending April 2027 is FY 27; its Q2 ends in October 2026
    assert periods.fylabel(date(2027, 4, 24), 4) == "FY 27"
    assert periods.qlabel(date(2026, 10, 24), 4) == "Q2 27"
    assert periods.qlabel(date(2026, 7, 25), 4) == "Q1 27"


def test_june_and_september_year_ends():
    assert periods.qlabel(date(2026, 9, 30), 6) == "Q1 27"
    assert periods.qlabel(date(2026, 12, 27), 9) == "Q1 27"


def test_52_53_week_years_ending_early_in_a_month_count_as_the_prior_month():
    # a December year that ends on 2 January belongs to the year before
    assert periods.fylabel(date(2027, 1, 2), 12) == "FY 26"
    assert periods.qlabel(date(2027, 1, 2), 12) == "Q4 26"


def test_fye_month_from_a_real_snapshot():
    assert periods.fye_month(snap("DXCM")) == 12
    assert periods.fye_month(snap("MDT")) == 4


def test_a_period_that_is_not_a_quarter_end_fails_loudly():
    # mid-January is not a quarter end of a December year; guessing a quarter would mislabel the estimate column
    import pytest
    with pytest.raises(ValueError, match="not a quarter end"):
        periods.qlabel(date(2026, 1, 15), 12)
