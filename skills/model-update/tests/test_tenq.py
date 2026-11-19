import json

import openpyxl

import actuals
import match
import modmap
import release
import make_fixture as mf


def _print_night(model, tmp_path):
    rel = release.parse_text(mf.release_md("combined"), "rel.md")
    res = match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E")
    res["leftover"] = []
    out, st = str(tmp_path / "p.xlsx"), str(tmp_path / "state.json")
    actuals.build(model, "Q3 26E", res, out, st)
    return out, st


def _tenq(path, st, take=None, tmp_path=None):
    v = mf.values()
    v.update({"L4": 140, "L6": 52, "L14": 80, "L18": 36, "L19": 67})
    rel = release.parse_text(mf.tenq_md(), "q.md")
    res = match.match(rel, modmap.ModMap(path), v, "Q3 26")
    out = str(tmp_path / "t.xlsx")
    rep = actuals.fill_tenq(path, res, out, st, take)
    return openpyxl.load_workbook(out)["MOD"], rep, json.load(open(st))


def test_the_10q_fills_waiting_cells_and_restores_the_subtotal(model, tmp_path):
    p, st = _print_night(model, tmp_path)
    ws, rep, state = _tenq(p, st, tmp_path=tmp_path)
    assert ws["L15"].value == 16.0 and ws["L16"].value == 7.0
    assert ws["L17"].value == "=SUM(L14:L16)" and state["awaiting"] == []


def test_a_release_number_the_10q_disagrees_with_is_asked_not_overwritten(model, tmp_path):
    p, st = _print_night(model, tmp_path)
    ws, rep, state = _tenq(p, st, tmp_path=tmp_path)
    assert ws["L6"].value == 52.0
    assert rep["differences"] == [{"ref": "L6", "key": "INCOME STATEMENT | Cost of sales", "release": 52.0,
                                   "tenq": 52.5, "file": "q.md", "lineno": rep["differences"][0]["lineno"]}]
    assert state["tenq_checked"] is False


def test_taking_the_10q_value_changes_only_the_listed_cell(model, tmp_path):
    p, st = _print_night(model, tmp_path)
    ws, rep, state = _tenq(p, st, take=["L6"], tmp_path=tmp_path)
    assert ws["L6"].value == 52.5 and state["tenq_checked"] is True
