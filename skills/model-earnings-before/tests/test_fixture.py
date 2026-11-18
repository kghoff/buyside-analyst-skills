"""The fixture has what each later test relies on: Q4 26E is the first forecast quarter and a hockey stick by
construction, ten earnings prints sit on Px Data trading days with room for the 7-day drift, and the build stays
small (the speed budget)."""
import os

import openpyxl

import make_fixture as mf


def test_shape(fixture_model):
    wb = openpyxl.load_workbook(fixture_model, read_only=True)
    assert {"MOD", "Px Data", "Px Events", "Multiples", "Consensus", "Filings Charts"} <= set(wb.sheetnames)
    assert os.path.getsize(fixture_model) < 300_000


def test_q4_26_is_a_hockey_stick_by_construction():
    s = mf.series()
    yoy = s["Q4 26E"]["rev"] / s["Q4 25"]["rev"] - 1
    yoy_prev = s["Q3 26"]["rev"] / s["Q3 25"]["rev"] - 1
    assert round(yoy, 3) == 0.12 and round(yoy_prev, 3) == 0.02


def test_prints_have_room_for_drift():
    days = mf.trading_days()
    for d in mf.reaction_days():
        assert days.index(d) + 7 < len(days)
