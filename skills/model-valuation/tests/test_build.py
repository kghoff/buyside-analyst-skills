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

YELLOW = "FFFFFF99"


@pytest.fixture
def work(model, tmp_path):
    """W with context.json, dcf_ctx.json, the example plan and a scenario result, as the skill leaves them."""
    w = tmp_path / "w"
    w.mkdir()
    subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "context.py"), "--model", model, "--work", str(w),
                    "--ticker", "TEST", "--research-dir", str(tmp_path / "none")], check=True)
    shutil.copy(os.path.join(FIX, "plan_example.json"), w / "valuation_plan.json")
    # scenario result for round 1 from the example plan's final cases
    plan = json.load(open(w / "valuation_plan.json"))
    t = {"round": 1, "final": True, "why": "x", "cases": {k: {"inputs": v["inputs"], "story": v["story"]}
                                                          for k, v in plan["scenarios"]["final"].items()}}
    (w / "scenarios_try_1.json").write_text(json.dumps(t))
    c = json.load(open(w / "context.json"))
    subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "scenario_eval.py"), "eval", "--dcf",
                    str(w / "dcf_ctx.json"), "--try", str(w / "scenarios_try_1.json"),
                    "--ntm-eps", str(c["metrics"]["eps"]["ntm"]["value"]),
                    "--ntm1-eps", str(c["metrics"]["eps"]["ntm1"]["value"]),
                    "--out", str(w / "scenarios_result_1.json")], check=True)
    return str(w)


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
        assert plan["inputs"][key]["anchor"] in c.comment.text, key
    yellow = {c.coordinate for r in ws.iter_rows() for c in r if c.fill and c.fill.fgColor.rgb == YELLOW}
    assert yellow == set(lay["inputs"].values())                     # nothing else is yellow


def test_user_change_survives_rerun(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
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


def test_untouched_inputs_follow_the_agent_on_rerun(model, work, tmp_path):
    """A cell still holding what the last build wrote is the agent's, so a new plan value replaces it; the record keeps
    the agent's value (not the user's), so a user's change stays theirs on every later rerun."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    p["inputs"]["buy_rr"]["value"] = 2.5
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))
    used, changed = build.resolve_inputs(out, p, json.load(open(os.path.join(work, "inputs_written.json"))),
                                         os.path.join(work, "values", "nothing.xlsx"))
    assert used["buy_rr"] == 2.5 and changed == {}
    assert json.load(open(os.path.join(work, "inputs_written.json")))["hurdle"] == 0.2


def test_labels_are_unique_and_found_on_the_tab(model, work, tmp_path):
    """Inputs are found on a rerun by their column-A text, so each one must appear exactly once."""
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    ws = _ws(out)
    a = [c.value for r in ws.iter_rows(min_col=1, max_col=1) for c in r if c.value is not None]
    lay = json.load(open(os.path.join(work, "layout.json")))
    for key, ref in lay["inputs"].items():
        assert a.count(build.LABEL[key]) == 1, key
        assert ws[f"A{ws[ref].row}"].value == build.LABEL[key] and ws[ref].column_letter == build.col_of(key)


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


@pytest.mark.skip(reason="Task 10")
def test_only_valuation_parts_change(model, work, tmp_path):
    import verify
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    assert verify.changed_parts(model, out) == []
