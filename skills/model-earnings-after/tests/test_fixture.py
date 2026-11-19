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


def _snapshot(fixture_model):
    return json.load(open(os.path.join(os.path.dirname(fixture_model), "_model_work", "update", mf.Q,
                                       "values.json")))["MOD"]


def _state(fixture_model):
    return json.load(open(os.path.join(os.path.dirname(fixture_model), "_model_work", "update", mf.Q,
                                       "state.json")))


def _col(snap, head):
    return next(k[:-1] for k, v in snap.items() if v == head and k[:-1].isalpha() and k[-1] == "2")


def _row(snap, label):
    return next(int(k[1:]) for k, v in snap.items() if k.startswith("B") and k[1:].isdigit() and v == label)


def test_fy_column_rolled_with_the_quarter(fixture_model):
    """model-update rolls the FY column on a Q4 print: FY 2026 = the pre-print FY plus the Q4 change, header 2026.
    The after-print math reads the year from this column, so it must carry the actual Q4."""
    snap = _snapshot(fixture_model)
    q, fy, r = _col(snap, mf.QE), _col(snap, mf.FYE), _row(snap, "Revenue")
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["MOD"]
    assert ws[f"{fy}2"].value == mf.FY and snap[f"{fy}2"] == mf.FYE
    assert abs(ws[f"{fy}{r}"].value - (snap[f"{fy}{r}"] + ws[f"{q}{r}"].value - snap[f"{q}{r}"])) < 1e-9
    assert ws[f"{q}{r}"].value != snap[f"{q}{r}"]


def test_state_names_one_placeholder_and_the_fy_column(fixture_model):
    """The placeholder is model-update's not-yet-reported Units cell in the printed quarter: the after-print
    comparison must skip it, so its ref must point at exactly that cell."""
    snap, st = _snapshot(fixture_model), _state(fixture_model)
    q, fy = _col(snap, mf.QE), _col(snap, mf.FYE)
    assert [p["ref"] for p in st["placeholders"]] == [f"{q}{_row(snap, 'Units')}"]
    assert st["fy_column"] == fy and st["column"] == q
    assert st["typed_subtotals"] == [] and st["release_values"] == []


def test_px_events_has_the_print(fixture_model):
    """The reaction is read from Px Events: released after the close, reacted the next trading day."""
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["Px Events"]
    rows = [r for r in ws.iter_rows(min_row=5, values_only=True) if r[0] == mf.Q]
    assert len(rows) == 1
    r = rows[0]
    assert r[8].date() == mf.RELEASE_DAY and r[12].date() == mf.REACTION_DAY and r[9] == "Earnings"
    assert (mf.REACTION_DAY - mf.RELEASE_DAY).days == 1 and mf.REACTION_DAY.weekday() < 5
    assert r[13] == mf.DAY_MOVE and r[16] == mf.IDIO


def test_valuation_tab_has_the_after_values(fixture_model):
    """The after-print target change compares the note's before values with these tab values."""
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["Valuation"]
    got = {r[0]: r[1] for r in ws.iter_rows(min_row=2, max_col=2, values_only=True) if r[0]}
    for lab, (_, after) in mf.VALUATION.items():
        assert got.get(lab) == after, lab


def test_valuation_note_has_the_before_values(fixture_research):
    """The note parser finds the before values under model-valuation's headings, printed as that skill prints them."""
    text = open(os.path.join(fixture_research, mf.VALNOTE)).read()
    for h in ("## 1 The recommendation", "## 2 Targets and risk/reward", "## 3 Three-year IRR"):
        assert f"\n{h}\n" in f"\n{text}", h
    v = {k: b for k, (b, _) in mf.VALUATION.items()}
    for lab in ("P/E: reward price", "P/E: risk price", "IRR: price now", "IRR: price in 3 years"):
        assert f"| {lab} | ${v[lab]:.2f} |" in text, lab
    assert f"| P/E: reward / risk | {v['P/E: reward / risk']:.1f}x |" in text
    assert f"| IRR | {v['IRR'] * 100:.1f}% |" in text
    assert f"| IRR: years | {v['IRR: years']} |" in text
    assert (f"- **Blended**: reward " in text and f"(to ${v['Blended reward price']:.2f})" in text
            and f"(to ${v['Blended risk price']:.2f})" in text
            and f"reward / risk {v['Blended reward / risk']:.1f}x" in text)


def test_px_data_runs_past_t_plus_7(fixture_model):
    """The T+7 rerun measures drift: Px Data needs more than 7 trading days after the reaction day."""
    ws = openpyxl.load_workbook(fixture_model, read_only=True)["Px Data"]
    days = [r[0].value for r in ws.iter_rows(min_row=5, max_col=1) if isinstance(r[0].value, dt.datetime)]
    assert sum(d.date() > mf.REACTION_DAY for d in days) > 7


def test_research_folder(fixture_research):
    for p in (mf.TRANSCRIPT, mf.RELEASE, mf.VALNOTE, mf.PREVIEW):
        assert os.path.isfile(os.path.join(fixture_research, p)), p
