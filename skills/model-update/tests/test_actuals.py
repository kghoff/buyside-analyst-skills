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


def _build(model, tmp_path, variant="normal", restate=False, grid=None):
    out, state = str(tmp_path / "out.xlsx"), str(tmp_path / "state.json")
    rep = actuals.build(model, "Q3 26E", _match(model, variant), out, state, restate=restate,
                        grid=mf.preprint() if grid is None else grid)
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


ORANGE = "FFC65911"


def test_unprinted_lines_keep_the_forecast_only_as_a_flagged_placeholder(model, tmp_path):
    """A blank waiting cell broke every forecast formula reading it (Q4 25 rebuild: 35 -> 1,753 error cells), but a
    forecast number that looks like an actual would be read as reported. So it stays, as a VALUE (never the forecast
    formula), in orange, with a note saying it is a placeholder and what will replace it, and listed in state.json."""
    ws, rep, st = _build(model, tmp_path, "combined")
    assert ws["L15"].value == 15.5 and ws["L16"].value == 6.5
    assert ws["L15"].font.color.rgb == ORANGE
    assert ws["L15"].comment.text == "Update: forecast placeholder (15.5), awaiting 10-Q; not reported"
    assert {"ref": "L15", "key": "ASSETS: | Other current assets", "kind": "10-Q", "value": 15.5} in st["placeholders"]
    assert "L15" not in st["release_values"] and {a["ref"] for a in st["awaiting"]} >= {"L15", "L16"}


def test_a_placeholder_never_replaces_a_printed_value(model, tmp_path):
    """The pre-print grid has a forecast for every line; only the lines the release did NOT print may keep it."""
    ws, rep, st = _build(model, tmp_path, "combined")
    assert ws["L4"].value == 140.0 and ws["L4"].font.color.rgb == "FF0000FF"
    assert not {p["ref"] for p in st["placeholders"]} & set(st["release_values"])


def test_a_waiting_cell_with_no_pre_print_value_stays_blank(model, tmp_path):
    """No forecast to keep (an empty or error cell before the print): nothing is invented."""
    g = {k: v for k, v in mf.preprint().items() if k != "L16"}
    ws, rep, st = _build(model, tmp_path, "combined", grid=g)
    assert ws["L16"].value is None and ws["L15"].value == 15.5
    assert "L16" in {a["ref"] for a in st["awaiting"]} and "L16" not in {p["ref"] for p in st["placeholders"]}
    assert rep["waiting_read_elsewhere"]["L16"] == ["M16"] and "L15" not in rep["waiting_read_elsewhere"]


def test_a_typed_text_forecast_is_kept_as_text_and_an_error_is_not_kept(model, tmp_path):
    """A ratio row typed 'n.a' keeps 'n.a' (blanking it changed what the user's model showed); an error value is no
    forecast to keep."""
    g = dict(mf.preprint(), L15="n.a", L16="#DIV/0!")
    ws, rep, st = _build(model, tmp_path, "combined", grid=g)
    assert ws["L15"].value == "n.a" and ws["L15"].font.color.rgb == ORANGE and ws["L16"].value is None


def test_a_subtotal_over_a_waiting_line_is_typed_and_restorable(model, tmp_path):
    """Total assets would add forecast placeholders; the release PRINTS it, so type the printed total until the 10-Q
    gives the parts."""
    ws, _, st = _build(model, tmp_path, "combined")
    assert ws["L17"].value == 103.0
    assert st["typed_subtotals"] == [{"ref": "L17", "formula": "SUM(L14:L16)", "key": "ASSETS: | Total assets"}]


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
