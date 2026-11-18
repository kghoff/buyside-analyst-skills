# skills/model-short/tests/test_plan.py
"""plan.py enforces chapter 12's discipline on the agent: every row answered with a reason, judgment ticks anchored
to a line, code's ticks overridden only with a real reason, a verdict that differs from the rule explained."""
import copy
import json
import os

import pytest

import plan as P


@pytest.fixture(scope="module")
def ctx(work_base):
    return json.load(open(os.path.join(work_base, "context.json")))


@pytest.fixture
def good(work_base):
    return json.load(open(os.path.join(work_base, "short_plan.json")))


def test_example_plan_passes(good, ctx):
    assert P.check(good, ctx) == []


def test_every_row_needs_a_tick_and_a_reason(good, ctx):
    del good["ticks"]["hope"]
    good["ticks"]["miss"]["reason"] = "short"
    p = P.check(good, ctx)
    assert any("ticks.hope: missing" in x for x in p) and any("ticks.miss" in x and "reason" in x for x in p)


def test_judgment_tick_needs_a_line_anchor_with_a_quote(good, ctx):
    g = copy.deepcopy(good)
    g["ticks"]["pricing"].pop("anchor")
    assert any("ticks.pricing" in x and "anchor" in x for x in P.check(g, ctx))
    g = copy.deepcopy(good)
    g["ticks"]["pricing"].pop("quote")
    assert any("ticks.pricing" in x and "quote" in x for x in P.check(g, ctx))


def test_overriding_code_needs_twelve_words(good, ctx):
    good["ticks"]["capex"] = {"tick": "no", "reason": "Capex is growth capex, not maintenance."}
    assert any("ticks.capex" in x and "code says yes" in x for x in P.check(good, ctx))


def test_inputs_types_buckets_and_verdict(good, ctx):
    g = copy.deepcopy(good)
    del g["inputs"]["dream_pe"]
    g["type"]["value"] = "Momentum crash"
    g["inputs"]["reward_pe"].pop("anchor_value")
    p = P.check(g, ctx)
    assert any("inputs.dream_pe: missing" in x for x in p)
    assert any("type" in x and "Momentum crash" in x for x in p)
    assert any("inputs.reward_pe" in x and "anchor_value" in x for x in p)


def test_verdict_against_the_rule(good, ctx):
    g = copy.deepcopy(good)
    g["verdict"] = {"value": "Alpha short", "reason": "Feels right."}
    assert any("rule says Filler short" in x for x in P.check(g, ctx))
    g["verdict"]["reason"] = ("A dated guide cut is coming at the analyst day next month, which the catalyst field "
                              "missed, so this is an alpha short not a filler.")
    assert P.check(g, ctx) == []
