# tests/test_build.py
"""The tab is the agent's suggestions made visible: every judgment is a yellow cell with its anchor and reason, and
the user's own changes survive a rerun (the user owns the model). Nothing outside the Valuation tab changes."""
import json
import math
import os
import shutil
import subprocess
import sys

import openpyxl
import pytest

import build
import lo
from conftest import FIX, SCRIPTS

pytestmark = pytest.mark.slow   # starts LibreOffice (run-tests.sh --full)

YELLOW = "FFFFFF99"


def _ws(p, data_only=False):
    return openpyxl.load_workbook(p, data_only=data_only)["Valuation"]


def _cell_by_label(ws, label, col="C"):
    for row in ws.iter_rows(min_col=1, max_col=1):
        if row[0].value == label:
            return ws[f"{col}{row[0].row}"]
    raise KeyError(label)


def test_every_plan_input_is_yellow_with_its_anchor(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    ws = _ws(out)
    plan = json.load(open(os.path.join(work, "valuation_plan.json")))
    lay = json.load(open(os.path.join(work, "layout.json")))
    for key, ref in lay["inputs"].items():
        c = ws[ref]
        assert c.fill.fgColor.rgb == YELLOW, key
        assert build.plan_inputs(plan)[key]["anchor"] in c.comment.text, key
    yellow = {c.coordinate for r in ws.iter_rows() for c in r if c.fill and c.fill.fgColor.rgb == YELLOW}
    assert yellow == set(lay["inputs"].values())                     # nothing else is yellow


def test_user_change_survives_rerun(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    _promote(work)
    ref = json.load(open(os.path.join(work, "layout.json")))["inputs"]["hurdle"]
    # the user types 15% over the agent's 20% (in a fixture copy, via openpyxl: a test file, never the user's)
    wb = openpyxl.load_workbook(out)
    wb["Valuation"][ref] = 0.15
    wb.save(out)
    shutil.rmtree(os.path.join(work, "values"))
    lo.recalc(out, os.path.join(work, "values"))
    out2 = str(tmp_path / "out2.xlsx")
    build.build(out, work, "TEST", out2)
    c = _ws(out2)[json.load(open(os.path.join(work, "layout.json")))["inputs"]["hurdle"]]
    assert c.value == 0.15 and "You typed" in c.comment.text and "Agent: 0.2" in c.comment.text


def test_overall_verdict_sits_at_the_top_and_stays_the_users(model, work, tmp_path):
    """The user asked for the agent's Buy / Hold / Sell at the top (row 3, above section 0, so no row below moves).
    It is a yellow cell like every other judgment, so the user's own verdict survives a rerun."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    ws = _ws(out)
    plan = json.load(open(os.path.join(work, "valuation_plan.json")))
    assert ws["A3"].value == build.LABEL["verdict"]
    assert ws["B3"].value == plan["verdict"]["value"] and ws["B3"].fill.fgColor.rgb == YELLOW
    assert ws["H3"].value == plan["verdict"]["reason"]
    _promote(work)
    _user_types(out, work, "verdict", "Buy")
    shutil.rmtree(os.path.join(work, "values"))
    lo.recalc(out, os.path.join(work, "values"))
    out2 = str(tmp_path / "out2.xlsx")
    build.build(out, work, "TEST", out2)
    c = _ws(out2)["B3"]
    assert c.value == "Buy" and "You typed Buy" in c.comment.text


def _promote(work):
    """SKILL step 7: the record becomes inputs_written.json once OUT is copied over the model."""
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))


def _set_plan(work, key, value):
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    p["inputs"][key]["value"] = value
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))


def _user_types(path, work, key, value):
    """The user edits a yellow cell (in a test copy, via openpyxl: never the user's file)."""
    ref = json.load(open(os.path.join(work, "layout.json")))["inputs"][key]
    wb = openpyxl.load_workbook(path)
    wb["Valuation"][ref] = value
    wb.save(path)


def _input_cell(path, work, key):
    return _ws(path)[json.load(open(os.path.join(work, "layout.json")))["inputs"][key]]


def test_user_value_survives_when_agent_later_agrees_then_moves(model, work, tmp_path):
    """Run 1 the agent writes 20%, the user types 15%; run 2 the agent happens to suggest 15% too; run 3 it suggests
    18%. The 15% is still the user's: agreeing once must not hand the cell back to the agent."""
    out1, out2, out3 = (str(tmp_path / f"out{i}.xlsx") for i in (1, 2, 3))
    build.build(model, work, "TEST", out1)
    _promote(work)
    _user_types(out1, work, "hurdle", 0.15)
    _set_plan(work, "hurdle", 0.15)
    build.build(out1, work, "TEST", out2)
    _promote(work)
    _set_plan(work, "hurdle", 0.18)
    build.build(out2, work, "TEST", out3)
    c = _input_cell(out3, work, "hurdle")
    assert c.value == 0.15 and "You typed" in c.comment.text


def test_rerun_records_what_it_wrote_and_whose_it_is(model, work, tmp_path):
    """inputs_written.next.json records the value the build wrote and flags the user's cells, so the next rerun knows
    a user's value from an agent's even when they are equal; an untouched cell follows the agent's new value."""
    out, out2 = str(tmp_path / "out.xlsx"), str(tmp_path / "out2.xlsx")
    build.build(model, work, "TEST", out)
    _promote(work)
    _user_types(out, work, "hurdle", 0.15)
    _set_plan(work, "buy_rr", 2.5)
    res = build.build(out, work, "TEST", out2)
    rec = json.load(open(os.path.join(work, "inputs_written.next.json")))
    assert rec["hurdle"] == {"value": 0.15, "user": True}
    assert rec["buy_rr"] == {"value": 2.5}
    assert _input_cell(out2, work, "buy_rr").value == 2.5 and "buy_rr" not in res["user_kept"]


def test_user_formula_is_kept_as_a_formula(model, work, tmp_path):
    out, out2 = str(tmp_path / "out.xlsx"), str(tmp_path / "out2.xlsx")
    build.build(model, work, "TEST", out)
    _promote(work)
    _user_types(out, work, "hurdle", "=0.1+0.05")
    shutil.rmtree(os.path.join(work, "values"))
    lo.recalc(out, os.path.join(work, "values"))
    build.build(out, work, "TEST", out2)
    c = _input_cell(out2, work, "hurdle")
    assert c.value == "=0.1+0.05" and "You typed" in c.comment.text
    assert json.load(open(os.path.join(work, "inputs_written.next.json")))["hurdle"]["user"] is True


def test_lost_label_is_warned(model, work, tmp_path):
    """If the user renames an input's row label, the build can't find their cell; it must say so, naming the label."""
    out, out2 = str(tmp_path / "out.xlsx"), str(tmp_path / "out2.xlsx")
    build.build(model, work, "TEST", out)
    _promote(work)
    row = _input_cell(out, work, "hurdle").row
    wb = openpyxl.load_workbook(out)
    wb["Valuation"][f"A{row}"] = "My hurdle"
    wb.save(out)
    res = build.build(out, work, "TEST", out2)
    assert any("IRR hurdle" in w for w in res["warnings"]), res["warnings"]


def test_formula_without_cached_value_falls_back(model, work, tmp_path):
    """A user formula that was never recalculated has no value to do the math with: warn, use the agent's value for
    the math, and keep the user's formula in the cell."""
    out, out2 = str(tmp_path / "out.xlsx"), str(tmp_path / "out2.xlsx")
    build.build(model, work, "TEST", out)
    _promote(work)
    _user_types(out, work, "hurdle", "=0.1+0.05")
    res = build.build(out, work, "TEST", out2)                  # no recalc: the formula has no cached value
    assert _input_cell(out2, work, "hurdle").value == "=0.1+0.05"
    assert any("IRR hurdle" in w for w in res["warnings"]), res["warnings"]


def test_text_in_number_cell_falls_back(model, work, tmp_path):
    out, out2 = str(tmp_path / "out.xlsx"), str(tmp_path / "out2.xlsx")
    build.build(model, work, "TEST", out)
    _promote(work)
    _user_types(out, work, "hurdle", "fifteen")
    res = build.build(out, work, "TEST", out2)
    assert _input_cell(out2, work, "hurdle").value == "fifteen"
    assert any("IRR hurdle" in w for w in res["warnings"]), res["warnings"]
    used, _, _ = build.resolve_inputs(out, json.load(open(os.path.join(work, "valuation_plan.json"))),
                                      json.load(open(os.path.join(work, "inputs_written.json"))))
    assert build.val(used["hurdle"]) == 0.2


def test_missing_record_treats_differences_as_the_users(model, work, tmp_path):
    """No inputs_written.json (deleted, say) but the tab exists: model-dcf's rule, a missing record means the cell is
    the user's wherever it differs from the agent, and the build says so."""
    out, out2 = str(tmp_path / "out.xlsx"), str(tmp_path / "out2.xlsx")
    build.build(model, work, "TEST", out)
    os.remove(os.path.join(work, "inputs_written.next.json"))     # never promoted: no record
    _user_types(out, work, "hurdle", 0.15)
    res = build.build(out, work, "TEST", out2)
    assert _input_cell(out2, work, "hurdle").value == 0.15 and "hurdle" in res["user_kept"]
    assert _input_cell(out2, work, "buy_rr").value == 2.0 and "buy_rr" not in res["user_kept"]
    assert any("inputs_written.json" in w for w in res["warnings"]), res["warnings"]


def test_growth_cagr_mirrors_valmath_on_negative_ends(model, work, tmp_path):
    """A CAGR from a loss is meaningless; Excel's (end/start)^(1/n) would still give a number when both ends are
    negative, so the sheet must return #N/A exactly where valmath.cagr returns None."""
    cp = os.path.join(work, "context.json")
    c = json.load(open(cp))
    g = c["metrics"]["growth"]["oi"]
    g["start"], g["end"] = -abs(g["start"]), -abs(g["end"])
    json.dump(c, open(cp, "w"))
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    e = lay["ref"]["cagr.oi"].replace("$", "")
    r = e[1:]
    assert lay["expected"][e] is None
    assert lay["formula_text"][e] == f"IF(AND(B{r}>0,C{r}>0),(C{r}/B{r})^(1/D{r})-1,NA())"


def test_labels_are_unique_and_found_on_the_tab(model, work, tmp_path):
    """Inputs are found on a rerun by their column-A text, so each one must appear exactly once."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    ws = _ws(out)
    a = [c.value for r in ws.iter_rows(min_col=1, max_col=1) for c in r if c.value is not None]
    lay = json.load(open(os.path.join(work, "layout.json")))
    for key, ref in lay["inputs"].items():
        assert a.count(build.label_of(key)) == 1, key
        assert ws[f"A{ws[ref].row}"].value == build.label_of(key) and ws[ref].column_letter == build.col_of(key)


def _close(got, want):
    if want is None:
        return got is None or (isinstance(got, str) and got.startswith("#"))
    if isinstance(want, str):
        return got == want
    return isinstance(got, (int, float)) and math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-9)


def test_sections_recalculate_to_expected(model, work, tmp_path):
    """Every checked formula and link recalculates (LibreOffice) to what valmath and context.json say, including the
    normalized-earnings section."""
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    year = json.load(open(os.path.join(work, "context.json")))["metrics"]["growth"]["eps"]["end_ref"]
    from modmap import ModMap
    fy = ModMap(model).forecast_years()[-1]
    p["normalization"] = {"year": fy,
                          "margin": {"value": 0.18, "anchor": year, "anchor_value": 1, "reason": "test margin"},
                          "multiple": {"value": 25.0, "anchor": "Multiples!B7", "anchor_value": 34.1, "reason": "t"},
                          "years": {"value": 3, "anchor": "Multiples!B7", "anchor_value": 34.1, "reason": "t"}}
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    assert {"normalization.margin", "normalization.multiple", "normalization.years"} <= set(lay["inputs"])
    ws = _ws(lo.recalc(out, str(tmp_path / "rc")), data_only=True)
    bad = {ref: (ws[ref].value, want) for ref, want in lay["expected"].items() if not _close(ws[ref].value, want)}
    assert bad == {} and len(lay["expected"]) >= 20


def test_tab_sits_after_multiples(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    names = openpyxl.load_workbook(out, read_only=True).sheetnames
    assert names[names.index("Multiples") + 1] == "Valuation"


def test_rr_and_tree_recalculate_to_valmath(model, work, tmp_path):
    """The sheet's formulas and valmath agree after LibreOffice recalculates (the spec's 'recompute in Python')."""
    import verify
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    r = verify.compare(out, work)
    assert r["failed"] == [] and r["errors"] == [] and r["checked"] > 80, r


def _blended(work):
    lay = json.load(open(os.path.join(work, "layout.json")))
    e, ref = lay["expected"], {k: v.replace("$", "") for k, v in lay["ref"].items()}
    row = int(ref["blended_risk"][1:])
    return e[ref["price"]], e[ref["blended_reward"]], e[ref["blended_risk"]], e[f"B{row + 1}"], e[f"B{row + 2}"]


def _blended_recalc(out, work, tmp_path, name):
    """(price, blended reward price, blended risk price, reward %, risk %) as LibreOffice recalculates them."""
    lay = json.load(open(os.path.join(work, "layout.json")))
    ref = {k: v.replace("$", "") for k, v in lay["ref"].items()}
    ws = _ws(lo.recalc(out, str(tmp_path / name)), data_only=True)
    row = int(ref["blended_risk"][1:])
    return tuple(ws[c].value for c in (ref["price"], ref["blended_reward"], ref["blended_risk"], f"B{row + 1}",
                                       f"B{row + 2}"))


def test_short_switch_flips(model, work, tmp_path):
    """A short makes money toward the risk price and loses toward the reward price, so reward % and risk % swap
    meaning; the sheet's switch formulas must follow the yellow position cell."""
    import verify
    out = str(tmp_path / "long.xlsx")
    build.build(model, work, "TEST", out)
    price, rw, rk, up, down = _blended_recalc(out, work, tmp_path, "rl")
    assert up == pytest.approx(rw / price - 1) and down == pytest.approx(1 - rk / price)
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    p["inputs"]["position"]["value"] = "short"
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    r = verify.compare(out, work)
    assert r["failed"] == [] and r["errors"] == [], r
    price2, rw2, rk2, up2, down2 = _blended_recalc(out, work, tmp_path, "rs")
    assert (price2, rw2, rk2) == pytest.approx((price, rw, rk))       # same prices, only the switch moved
    assert up2 == pytest.approx((price - rk) / price) and down2 == pytest.approx((rw - price) / price)
    assert up != pytest.approx(down)                                  # so the swap below is visible
    assert up2 == pytest.approx(down) and down2 == pytest.approx(up)


def test_ladder_has_seven_rungs_around_today(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    ws = _ws(out)
    steps = [c.value for r in ws.iter_rows(min_col=1, max_col=1) for c in r if isinstance(c.value, float)
             and -0.16 < c.value < 0.16 and c.number_format.startswith("+0%")]
    assert steps == pytest.approx([-.15, -.10, -.05, 0, .05, .10, .15])


def test_dcf_scenarios_are_grey_blue_and_sourced(model, work, tmp_path):
    """The scenario values are typed from scenario_eval (model-dcf's own math), so each is blue on grey and its note
    names the round that produced it."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    ws = _ws(out)
    vps = ws[lay["ref"]["dcf_base"].replace("$", "")]
    res = json.load(open(os.path.join(work, "scenarios_result_1.json")))
    assert vps.value == pytest.approx(res["base"]["value_per_share"])
    assert vps.fill.fgColor.rgb == "FFD9D9D9" and vps.font.color.rgb == "FF0000FF"
    assert vps.comment.text.startswith("scenario_eval round 1, ")


def test_pairing_is_in_the_formula_text(model, work, tmp_path):
    """P/E prices equity from EPS alone; EV/EBITDA must take off net debt and divide by shares (chapter 11.2)."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    ft, ref = lay["formula_text"], lay["ref"]
    nd, sh = ref["nd"], ref["sh"]
    pe, ev = ft[ref["reward_px.pe"].replace("$", "")], ft[ref["reward_px.ev_ebitda"].replace("$", "")]
    assert nd not in pe and sh not in pe
    assert nd in ev and sh in ev


def test_only_valuation_parts_change(model, work, tmp_path):
    import verify
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    assert verify.changed_parts(model, out) == []


def _row_of(ws, label):
    return next(c.row for r in ws.iter_rows(min_col=1, max_col=1) for c in r if c.value == label)


def test_anchored_tree_target_keeps_all_three_reasons(model, work, tmp_path):
    """An anchored tree target, its probability and the story each carry a reason; the user must see all three."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    t = next(x for x in json.load(open(os.path.join(work, "valuation_plan.json")))["tree"] if "link" not in x["target"])
    h = _ws(out)[f"H{_row_of(_ws(out), t['name'])}"].value
    assert h == f"Target: {t['target']['reason'].rstrip('.')}; Probability: {t['prob']['reason'].rstrip('.')}; " \
        f"Story: {t['story']}"


def test_double_path_words_follow_the_multiple(model, work, tmp_path):
    """With EV/EBITDA primary, the route to a double is multiple expansion or metric growth, not P/E or EPS."""
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    for m in p["multiples"]:
        m["role"] = "primary" if m["kind"] == "ev_ebitda" else "secondary"
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    ws = _ws(out)
    ref = next(f"B{c.row}" for r in ws.iter_rows(min_col=1, max_col=1) for c in r
               if isinstance(c.value, str) and c.value.endswith("-year double path"))
    f = lay["formula_text"][ref]
    assert "multiple expansion" in f and "metric growth" in f and "P/E" not in f and "EPS" not in f
    assert lay["expected"][ref] in ("multiple expansion", "metric growth", "both", "no double path (price falls)")
