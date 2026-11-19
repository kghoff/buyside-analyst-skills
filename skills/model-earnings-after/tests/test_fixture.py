"""The fixture must look like a real after-print model, or every other test proves nothing: band 7 froze Q4 26E
before the print, MOD now has Q4 26 actuals that differ from it, Px Data runs past T+7, and the research folder has
the transcript, the release, a pre-print Valuation Note and model-update's pre-print snapshot."""
import datetime as dt
import json
import os

import openpyxl
from openpyxl.utils import get_column_letter

import make_fixture as mf


def test_band7_froze_the_quarter_before_the_print(fixture_model):
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["Earnings"]
    heads = [r[0].value for r in ws.iter_rows(max_col=1) if r[0].value]
    assert any(str(h).startswith("7. FROZEN FORECAST: Q4 26E, frozen 2026-11-18") for h in heads)


def test_mod_has_actuals_that_differ_from_the_freeze(fixture_model):
    """The after-print math needs actuals that are not the forecast: model-update's snapshot holds the pre-print
    Q4 26E column, MOD now holds Q4 26 actuals, revenue 4% above the snapshot."""
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["MOD"]
    heads = [c.value for c in next(ws.iter_rows(min_row=2, max_row=2))]
    assert "Q4 26" in heads and "Q4 26E" not in heads
    col = get_column_letter(heads.index("Q4 26") + 1)
    snap = json.load(open(os.path.join(os.path.dirname(fixture_model), "_model_work", "update", mf.Q,
                                       "values.json")))["MOD"]
    assert snap[f"{col}2"] == mf.QE
    rev_row = next(int(k[1:]) for k, v in snap.items() if k.startswith("B") and v == "Revenue")
    assert abs(ws[f"{col}{rev_row}"].value / snap[f"{col}{rev_row}"] - mf.ACTUAL_X["rev"]) < 1e-9


def test_px_data_runs_past_t_plus_7(fixture_model):
    """The T+7 rerun measures drift: Px Data needs more than 7 trading days after the reaction day."""
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["Px Data"]
    days = [r[0].value for r in ws.iter_rows(min_row=5, max_col=1) if isinstance(r[0].value, dt.datetime)]
    assert sum(d.date() > mf.REACTION_DAY for d in days) > 7


def test_research_folder(fixture_research):
    for p in (mf.TRANSCRIPT, mf.RELEASE, mf.VALNOTE, mf.PREVIEW):
        assert os.path.isfile(os.path.join(fixture_research, p)), p
