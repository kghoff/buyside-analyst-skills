"""The agent anchors on cell refs, so the dumps must carry them; missing prerequisites name the skill to run."""
import json
import os

import openpyxl
import pytest

import context


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
