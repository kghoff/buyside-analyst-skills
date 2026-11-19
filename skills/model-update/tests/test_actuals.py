import json
import os

import openpyxl

import actuals
import match
import modmap
import release
import make_fixture as mf


def _match(model, variant="normal"):
    rel = release.parse_text(mf.release_md(variant), "rel.md")
    res = match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E")
    res["leftover"] = []                       # the agent's answers are tested in test_answers
    return res


def _build(model, tmp_path, variant="normal", restate=False):
    out, state = str(tmp_path / "out.xlsx"), str(tmp_path / "state.json")
    rep = actuals.build(model, "Q3 26E", _match(model, variant), out, state, restate=restate)
    return openpyxl.load_workbook(out)["MOD"], rep, json.load(open(state))


def test_typed_lines_are_blue_with_their_source(model, tmp_path):
    ws, rep, _ = _build(model, tmp_path)
    assert ws["L4"].value == 140.0 and ws["L4"].font.color.rgb == "FF0000FF"
    assert ws["L4"].comment.text.startswith("Update: Revenue 140.0 - rel.md line")


def test_subtotals_keep_the_formula_skeleton_from_last_year(model, tmp_path):
    """The chapter's 15-minute update: copy last year's column, keep its formulas, enter the release."""
    ws, _, _ = _build(model, tmp_path)
    assert ws["L7"].value == "=L4-L6" and ws["L17"].value == "=SUM(L14:L16)" and ws["L24"].value == "=L7"


def test_analysis_rows_are_untouched(model, tmp_path):
    ws, _, _ = _build(model, tmp_path)
    assert ws["L5"].value == "=(L4/F4)-1"


def test_header_loses_its_E_and_the_year_stays_a_forecast(model, tmp_path):
    ws, _, _ = _build(model, tmp_path)
    assert ws["L2"].value == "Q3 26" and ws["N2"].value == "2026E"


def test_cash_flow_is_the_printed_ytd_less_earlier_quarters_in_blue(model, tmp_path):
    """The house form for Q2/Q3 cash flow: the printed YTD stays visible in the cell, the quarter falls out."""
    ws, rep, st = _build(model, tmp_path)
    assert ws["L22"].value == "=61-K22-J22" and ws["L22"].font.color.rgb == "FF0000FF"
    assert "YTD" in ws["L22"].comment.text and st["release_values"]["L22"] == 22.0


def test_lines_the_release_does_not_print_are_blank_never_forecast(model, tmp_path):
    """A forecast number left in an actual column would be read as reported."""
    ws, rep, st = _build(model, tmp_path, "combined")
    assert ws["L15"].value is None and ws["L16"].value is None
    assert {a["ref"] for a in st["awaiting"]} >= {"L15", "L16"}


def test_a_subtotal_over_a_waiting_line_is_typed_and_restorable(model, tmp_path):
    """Total assets would add blanks; type the printed total until the 10-Q gives the parts."""
    ws, _, st = _build(model, tmp_path, "combined")
    assert ws["L17"].value == 103.0
    assert st["typed_subtotals"] == [{"ref": "L17", "formula": "SUM(L14:L16)"}]


def test_recasts_change_history_only_with_a_yes(model, tmp_path):
    ws, _, _ = _build(model, tmp_path, "recast")
    assert ws["F4"].value == 120
    ws2, rep, _ = _build(model, tmp_path, "recast", restate=True)
    assert ws2["F4"].value == 121.0 and "recast" in ws2["F4"].comment.text


def test_other_tabs_are_byte_identical(model, tmp_path):
    from xlsx import Package
    _build(model, tmp_path)
    a, b = Package(model), Package(str(tmp_path / "out.xlsx"))
    for name, _, _, part in a.sheets():
        if name != "MOD":
            assert a.parts[part] == b.parts[part], name
