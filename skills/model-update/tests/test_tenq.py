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
    rep = actuals.fill_tenq(path, "Q3 26", res, out, st, take)
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


def test_q4_turns_the_year_column_into_actuals(tmp_path):
    """On a Q4 print the fiscal year closes: its header loses the E and its cells follow last year's formulas."""
    import make_fixture as mf2
    p = mf2.model(str(tmp_path / "m.xlsx"))
    wb = openpyxl.load_workbook(p)
    ws = wb["MOD"]
    ws["L2"] = "Q3 26"
    for r in range(4, 28):
        if isinstance(ws[f"L{r}"].value, str) and r not in (5, 7, 9, 17, 20, 24, 26):
            ws[f"L{r}"] = 1.0
    wb.save(p)
    res = {"matched": [], "combined": [], "diffs": [], "leftover": [], "ambiguous": []}
    out = str(tmp_path / "o.xlsx")
    actuals.build(p, "Q4 26E", res, out, str(tmp_path / "s.json"))
    w = openpyxl.load_workbook(out)["MOD"]
    assert w["M2"].value == "Q4 26" and w["N2"].value == "2026" and w["N4"].value == "=SUM(J4:M4)"
