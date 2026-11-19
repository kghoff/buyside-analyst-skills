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
                                   "tenq": 52.5, "file": "q.md", "lineno": rep["differences"][0]["lineno"],
                                   "can_take": True}]
    assert state["tenq_checked"] is False


def test_taking_the_10q_value_changes_only_the_listed_cell(model, tmp_path):
    p, st = _print_night(model, tmp_path)
    ws, rep, state = _tenq(p, st, take=["L6"], tmp_path=tmp_path)
    assert ws["L6"].value == 52.5 and state["tenq_checked"] is True


def test_rows_moved_between_print_night_and_the_10q_stop_the_rerun_before_it_writes(model, tmp_path):
    """state.json names waiting cells, placeholders and typed subtotals by cell. If the user ran /model-forecast in
    between and it inserted a row, every ref below it points one line off and the 10-Q would type numbers (and put
    saved formulas) into the wrong lines. Each saved key is checked against today's row first; a move stops the run."""
    import pytest
    from xlsx import Package
    from xledit import insert_rows
    p, st = _print_night(model, tmp_path)
    state = json.load(open(st))
    assert state["typed_subtotals"] and all(t["key"] for t in state["typed_subtotals"])
    pkg = Package(p)
    insert_rows(pkg, "MOD", 5, 1)                     # a /model-forecast row insert after print night
    pkg.finish()
    moved = str(tmp_path / "moved.xlsx")
    pkg.save(moved)
    with pytest.raises(SystemExit) as e:
        _tenq(moved, st, tmp_path=tmp_path)
    assert "MOD rows moved since print night" in str(e.value) and "/model-forecast" in str(e.value)
    assert not (tmp_path / "t.xlsx").exists()


def test_a_typed_subtotal_difference_is_not_offered_as_a_take(model, tmp_path):
    """A typed subtotal never takes the filing's number: its formula comes back once its parts are filled, so offering
    'take the 10-Q value' for it would be a choice that does nothing. can_take tells SKILL.md to leave it out."""
    p, st = _print_night(model, tmp_path)
    v = mf.values()
    v.update({"L4": 140, "L6": 52, "L14": 80, "L18": 36, "L19": 67})
    res = match.match(release.parse_text(mf.tenq_md(), "q.md"), modmap.ModMap(p), v, "Q3 26")
    state = json.load(open(st))
    state["release_values"]["L17"] = 999.0           # the release's printed total disagrees with the 10-Q's
    json.dump(state, open(st, "w"))
    rep = actuals.fill_tenq(p, res, str(tmp_path / "t.xlsx"), st, ["L17"])
    d = [x for x in rep["differences"] if x["ref"] == "L17"]
    assert d and d[0]["can_take"] is False and "L17" in rep["restored"]
