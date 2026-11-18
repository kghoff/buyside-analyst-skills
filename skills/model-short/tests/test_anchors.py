# skills/model-short/tests/test_anchors.py
"""Never type a number that isn't printed in a source: every anchored number and quote is checked on its cell or line."""
import copy
import json
import os

import anchors
from conftest import RESEARCH


def _run(plan, work):
    ctx = json.load(open(os.path.join(work, "context.json")))
    return anchors.check(plan, ctx["values"], RESEARCH, ctx)


def test_example_holds(work):
    assert _run(json.load(open(os.path.join(work, "short_plan.json"))), work) == []


def test_wrong_cell_value_and_wrong_line_number_fail(work):
    p = json.load(open(os.path.join(work, "short_plan.json")))
    g = copy.deepcopy(p)
    g["inputs"]["reward_pe"]["anchor_value"] = 25.0
    assert any("reward_pe" in x and "holds 22" in x for x in _run(g, work))
    g = copy.deepcopy(p)
    g["inputs"]["takeout_premium"]["anchor"] = "Filings/test_10q.md:4"
    assert any("takeout_premium" in x and "does not print" in x for x in _run(g, work))


def test_quotes_must_be_on_their_line(work):
    p = json.load(open(os.path.join(work, "short_plan.json")))
    p["smoke"][0]["quote"] = "auditor resigned"
    p["ticks"]["pricing"]["quote"] = "Price increases of 3%"
    out = _run(p, work)
    assert any("smoke[0]" in x for x in out) and any("ticks.pricing" in x for x in out)


def test_a_changed_house_input_names_the_house_default(work):
    p = json.load(open(os.path.join(work, "short_plan.json")))
    p["inputs"]["hurdle"]["value"] = 0.10
    out = _run(p, work)
    assert any(x.startswith("hurdle: the house default is 0.08") for x in out), out
    assert not any("chapter 11" in x for x in out)
