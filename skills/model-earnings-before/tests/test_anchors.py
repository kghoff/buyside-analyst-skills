# skills/model-earnings-before/tests/test_anchors.py
"""Every anchored number and quote is really where the plan says: a made-up cell value or a quote that isn't on the
cited line is caught before anything is written."""
import json
import os

import anchors
from conftest import RESEARCH

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "plan_example.json")


def _ctx(work):
    return json.load(open(os.path.join(work, "context.json")))


def test_example_anchors_hold(fixture_model, work):
    assert anchors.check(json.load(open(FIX)), fixture_model, RESEARCH, _ctx(work)) == []


def test_wrong_cell_value_and_wrong_quote_fail(fixture_model, work):
    p = json.load(open(FIX))
    p["inputs"]["up_pe"]["anchor_value"] = 25.0
    p["points"]["since_last_print"][0]["quote"] = "demand is collapsing"
    probs = anchors.check(p, fixture_model, RESEARCH, _ctx(work))
    assert any(x.startswith("inputs.up_pe: Multiples!$H$7 holds 22") for x in probs)
    assert any(x.startswith("points.since_last_print[0]:") for x in probs)
