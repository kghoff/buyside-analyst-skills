# tests/test_aftermath.py
"""Every number the tab and the note show comes from these functions, and the tab's formulas compute the same
things (verify.py proves it). The chapter's worked numbers pin them: a misread formula fails here first."""
import pytest

import aftermath as am


def test_fading_moves_irr_33pct():
    # 13.7 "Fading Moves": $20 -> $40 in 3 years is 26.0%; after a 15% sell-off ($17) it is 33.0%
    assert am.irr(20, 40) == pytest.approx(0.2599, abs=1e-4)
    assert am.irr(17, 40) == pytest.approx(0.3300, abs=1e-4)


def test_fade_table_matches_the_chapter():
    t = am.fade_table(20.0, 40.0)
    assert [round(x["irr"], 3) for x in t] == [0.260, 0.282, 0.305, 0.330, 0.357, 0.387, 0.419]
    assert t[3]["price"] == pytest.approx(17.0)


def test_ten_pct_move_at_25pct_vol_is_about_six_sigma():
    # 13.6 "Signal or Noise?": 25% annual vol -> 1.6% a day; a 10% drop is roughly six sigma
    d = am.daily_sigma(0.25)
    assert d == pytest.approx(0.01575, abs=1e-4)
    assert am.sigmas(-0.10, d) == pytest.approx(-6.35, abs=0.01)


def test_surprise_reads_costs_with_their_sign():
    # costs are stored negative: -45 against a forecast of -50 is a 10% beat, not a miss
    assert am.surprise(105.0, 100.0) == pytest.approx(0.05)
    assert am.surprise(-45.0, -50.0) == pytest.approx(0.10)
    assert am.surprise(5.0, 0.0) is None


def test_result_in_line_band():
    assert am.result(0.005, 0.01) == "in line"
    assert am.result(0.02, 0.01) == "beat"
    assert am.result(-0.02, 0.01) == "miss"
    assert am.result(None, 0.01) is None


def test_long_term_pace_from_the_chapter_table():
    # 13.7 "Tracking Long-Term Guidance": 11% in 2021, +100 bps a year, 15% target in 2024 -> run rate 14%
    p = am.lt_pace(now_value=0.11, now_year=2021, slope=0.01, target=0.15, target_year=2024)
    assert p["run_rate"] == pytest.approx(0.14)
    assert p["needed_per_year"] == pytest.approx(0.04 / 3)
    assert p["status"] == "behind pace"
    assert am.lt_pace(0.11, 2021, 0.02, 0.15, 2024)["status"] == "on pace"


def test_trend_is_average_annual_change_over_three_years():
    assert am.trend({2018: 0.08, 2019: 0.09, 2020: 0.10, 2021: 0.11}, 2021) == pytest.approx(0.01)
    assert am.trend({2021: 0.11}, 2021) is None


def test_target_change_minus_move_flags_under_reaction():
    # 13.6 "Adjusting the Price Target": stock +15%, target +21% -> under-reaction of 6 pts
    assert am.gap(0.21, 0.15) == pytest.approx(0.06)


def test_growth_needs_a_positive_base():
    # growth off a loss reads backwards (-2 -> 5 would show -350%), so it is None, as in model-earnings-before
    assert am.growth(5, -2) is None
    assert am.growth(110, 100) == pytest.approx(0.10)


def test_lt_pace_for_a_target_below_today():
    # a target to come down (cost ratio): falling at least as fast as needed is on pace
    assert am.lt_pace(0.15, 2021, -0.02, 0.10, 2024)["status"] == "on pace"
    assert am.lt_pace(0.15, 2021, -0.01, 0.10, 2024)["status"] == "behind pace"


def test_lt_pace_with_no_time_left_is_unknown():
    assert am.lt_pace(0.11, 2024, 0.01, 0.15, 2024)["status"] == "?"
    assert am.lt_pace(0.11, 2025, 0.01, 0.15, 2024)["status"] == "?"


def test_result_boundary_is_in_line():
    assert am.result(0.01, 0.01) == "in line"


def test_irr_needs_positive_prices():
    assert am.irr(0, 40) is None
    assert am.irr(20, -1) is None
