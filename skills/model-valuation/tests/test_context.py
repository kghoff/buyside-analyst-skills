"""The agent anchors on cell refs, so the dumps must carry them; missing prerequisites name the skill to run."""
import json
import os
import re

import openpyxl
import pytest

import context
from modmap import ModMap


def test_dump_carries_refs(model, tmp_path):
    w = str(tmp_path / "w")
    context.run(model, w, "TEST", research_dir=str(tmp_path / "none"))
    md = open(os.path.join(w, "context.md")).read()
    assert "C7=81.755" in md and "WEEKLY DATA" not in md.split("## Multiples")[1].split("##")[0]
    ctx = json.load(open(os.path.join(w, "context.json")))
    assert ctx["house"]["hurdle"] == 0.20 and ctx["dcf"]["refs"]["price"] == "DCF!$C$18"
    assert ctx["brief"]["missing"]                       # no research folder: listed, not silent
    # build.py and anchors.py reuse this recalculated copy instead of recalculating again
    assert ctx["values"] == os.path.join(w, "values", "TEST_model.xlsx") and os.path.exists(ctx["values"])
    assert set(ctx) == {"ticker", "metrics", "dcf", "dumps", "brief", "reports", "house", "last_plan", "values"}


def test_missing_tabs_named(model, tmp_path):
    wb = openpyxl.load_workbook(model)
    del wb["Multiples"]
    wb.save(model)
    with pytest.raises(SystemExit, match="/model-multiples"):
        context.run(model, str(tmp_path / "w"), "TEST", research_dir=str(tmp_path))


def test_mod_metrics_carry_each_quarter_and_year_cell(model, tmp_path):
    """The risk metric is anchored to MOD; the agent can only cite a MOD cell it has seen, so every quarter behind
    NTM / NTM+1 / year 3 and every forecast-year cell is listed as ref=value, in the form anchors.py accepts."""
    w = str(tmp_path / "w")
    ctx = context.run(model, w, "TEST", research_dir=str(tmp_path / "none"))
    sec = open(os.path.join(w, "context.md")).read().split("## MOD metrics")[1].split("\n## ")[0]
    vals = openpyxl.load_workbook(ctx["values"], data_only=True)["MOD"]
    mm = ModMap(model)
    for k in ("eps", "rev", "gp", "ebitda", "fcf"):
        assert f"### {k}" in sec
        for b in ("ntm", "ntm1", "y3"):
            for ref in re.findall(r"MOD!\$[A-Z]+\$\d+", ctx["metrics"][k][b]["formula"].split(",NA()")[0]):
                assert f"{ref}=" in sec, (k, b, ref)
    fy_lines = [x.split(": ", 1)[1].split(" | ") for x in sec.splitlines() if re.match(r"- \d{4}", x)]
    assert fy_lines and all(len(set(x)) == len(x) for x in fy_lines)        # each cell once
    eps_row = int(re.search(r"\$(\d+)", ctx["metrics"]["eps"]["ntm"]["formula"]).group(1))
    for fy in mm.forecast_years():
        ref = f"MOD!${mm.col(fy)}${eps_row}"
        assert f"{ref}={context._fmt(vals[ref[4:].replace('$', '')].value)}" in sec, fy


def _set_dcf(model, cells):
    wb = openpyxl.load_workbook(model)       # a test copy only
    for ref, v in cells.items():
        wb["DCF"][ref] = v
    wb.save(model)


def _dcf_rows(model):
    """model-dcf's layout for this model, from its own process (its modules share names with ours)."""
    import subprocess
    import sys
    from conftest import DCF
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); import context, build;"
            "c = context.build(sys.argv[2]); R = build.layout(c)['rows'];"
            "print(json.dumps({'g0': R['g0'], 'vps': R['vps'], 'years': R['years'], 'col': build.tcol(c['k'] + 1)}))")
    return json.loads(subprocess.run([sys.executable, "-c", code, DCF, model], check=True, capture_output=True,
                                     text=True).stdout)


@pytest.mark.parametrize("why, edit", [
    # the tab was built for other revenue drivers: its growth row is not the current plan's
    ("Customers growth", lambda R: {f"B{R['g0']}": "Customers growth, % yoy"}),
    # the tab was built when the forecast ended another year: the input years sit in other columns
    ("column", lambda R: {f"{R['col']}{R['years']}": "1999E"}),
])
def test_old_dcf_layout_stops(model, tmp_path, why, edit):
    """An older DCF tab puts drivers or years in other cells; build and typecheck would type the scenarios into the
    wrong ones, so model-valuation stops (a warning was not enough) and says which skills to rerun, in order."""
    _set_dcf(model, edit(_dcf_rows(model)))
    w = str(tmp_path / "w")
    with pytest.raises(SystemExit, match=rf"DCF tab is out of date \(.*{why}.*\)\. Rerun /model-dcf, then rerun "
                                         r"/model-valuation\."):
        context.run(model, w, "TEST", research_dir=str(tmp_path / "none"))
    assert not os.path.exists(os.path.join(w, "context.json"))      # the agent never sees a context built on it


def test_stale_dcf_value_stops(model, tmp_path):
    """The DCF tab shows a value its inputs no longer give (e.g. MOD changed since /model-dcf ran): the scenarios
    would not match the tab, so model-valuation stops."""
    _set_dcf(model, {f"C{_dcf_rows(model)['vps']}": 1.0})
    with pytest.raises(SystemExit, match=r"out of date \(the tab shows \$1\.00 a share but its inputs give \$\d+\.\d\d\)"
                                         r"\. Rerun /model-dcf"):
        context.run(model, str(tmp_path / "w"), "TEST", research_dir=str(tmp_path / "none"))
