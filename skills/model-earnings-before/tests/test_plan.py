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


def test_line_anchored_input_needs_the_number(p, ctx):
    """anchors.py checks an input's number on its line; a quote alone can never pass there, so say so here."""
    p["inputs"]["up_pe"] = {"value": 18.0, "anchor": "filings.md:12", "quote": "a 22x multiple",
                            "reason": "Below the 22x five-year median: a beat restores some multiple but not all."}
    assert any("inputs.up_pe: needs the anchor_value" in m for m in plan.check(p, ctx)), plan.check(p, ctx)


@pytest.mark.parametrize("edit,needle", [
    (lambda p: p["points"].update(last_quarter=["a bare string"]), "points.last_quarter[0]"),
    (lambda p: p.update(setup=["long"]), "setup: must be"),
    (lambda p: p["setup"].update(previews="long"), "setup.previews: missing"),
    (lambda p: p.update(risks=[1, 2]), "risks: must be"),
    (lambda p: p["risks"].update(liquidity=3), "risks.liquidity"),
    (lambda p: p.update(inputs=[1]), "inputs: must be"),
    (lambda p: p.update(points=["x"]), "points: must be"),
    (lambda p: p.update(key_metric="revenue"), "key_metric"),
    (lambda p: p.update(call="beat"), "call"),
    (lambda p: p.update(stance="add"), "stance"),
])
def test_malformed_plan_is_a_problem_not_a_crash(p, ctx, edit, needle):
    q = copy.deepcopy(p)
    edit(q)
    msgs = plan.check(q, ctx)
    assert any(needle in m for m in msgs), msgs
