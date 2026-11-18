# skills/model-earnings-before/tests/test_plan.py
"""plan.py keeps the agent honest: every side, score and case is explained and anchored, the cases straddle today's
price, and the stance is the rule's, not the agent's preference (the user, not the agent, may override it)."""
import copy
import json
import os

import pytest

import plan

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "plan_example.json")


@pytest.fixture
def ctx(work):
    return json.load(open(os.path.join(work, "context.json")))


@pytest.fixture
def p():
    return json.load(open(FIX))


def test_example_passes(p, ctx):
    assert plan.check(p, ctx) == []


def test_stance_must_follow_the_rule(p, ctx):
    p["stance"]["value"] = "add"
    (msg,) = plan.check(p, ctx)
    assert msg.startswith("stance: the rule says hold")


def test_cases_must_straddle_the_price(p, ctx):
    p["inputs"]["down_pe"]["value"] = 30.0
    assert any("downside case below" in m for m in plan.check(p, ctx))


@pytest.mark.parametrize("edit,needle", [
    (lambda p: p["setup"].pop("consensus"), "setup.consensus: missing"),
    (lambda p: p["setup"]["previews"].update(side="bullish"), "setup.previews: side must be"),
    (lambda p: p["setup"]["previews"].pop("anchor"), "setup.previews: a long or short side needs an anchor"),
    (lambda p: p["key_metric"].pop("quote"), "key_metric: a line anchor needs the quote"),
    (lambda p: p["risks"]["liquidity"].update(score=6), "risks.liquidity: score"),
    (lambda p: p["inputs"]["p_beat"].update(value=1.5), "inputs.p_beat: must be between 0 and 1"),
    (lambda p: p["inputs"]["p_beat"].update(reason="even odds"), "inputs.p_beat: a judgment needs a reason"),
    (lambda p: p["call"].update(guide="up"), "call.guide"),
    (lambda p: p["points"].update(since_last_print=[]), "points.since_last_print: there are documents"),
    (lambda p: p.update(quarter="Q1 27E"), "quarter: the plan is for"),
    (lambda p: p.update(judgment_calls=[]), "judgment_calls"),
])
def test_each_rule_has_a_plain_english_problem(p, ctx, edit, needle):
    q = copy.deepcopy(p)
    edit(q)
    assert any(needle in m for m in plan.check(q, ctx)), plan.check(q, ctx)


def test_code_row_override_needs_a_longer_reason(p, ctx):
    code = ctx["code"]["setup"]["value_perf"]
    other = "long" if code != "long" else "short"
    p["setup"]["value_perf"] = {"side": other, "reason": "I disagree with the code here."}
    assert any("setup.value_perf: overriding code" in m for m in plan.check(p, ctx))
