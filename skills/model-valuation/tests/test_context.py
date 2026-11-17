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
