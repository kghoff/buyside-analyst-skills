"""plan.py rejects a plan the tab cannot show honestly: an unknown SFOT value or react call, a reason too thin to
act on, a call note with no quote, a long-term target on a line that is not in MOD, or a missing played_out on the
T+7 rerun (the whole point of the rerun)."""
import copy
import json
import os

import pytest

import context
import make_fixture as mf
import plan

HERE = os.path.dirname(__file__)
EX = json.load(open(os.path.join(HERE, "fixtures", "plan_example.json")))
CTX = {"quarter": "Q4 26", "mode": "first", "drift_ready": True, "topics": list(EX["call_notes"]),
       "mod_keys": ["INCOME STATEMENT | Revenue", "INCOME STATEMENT | Operating Income"]}


def test_example_passes():
    assert plan.check(EX, CTX) == []


def test_example_passes_against_the_fixture_context(model, fixture_research, tmp_path):
    """The example must fit the context the agent is really given (its topics, quarter and MOD keys), or it teaches
    a shape that fails on the first real run."""
    w = str(tmp_path / "w")
    os.makedirs(w)
    json.dump(mf.YAHOO, open(os.path.join(w, "yahoo_after.json"), "w"))
    ctx = context.run(model, w, "TEST", values=model, research=fixture_research, today="2027-02-28")
    assert set(EX["call_notes"]) == set(ctx["topics"])
    assert plan.check(EX, ctx) == []


def test_assignment_lists_every_enum():
    """The assignment quotes plan.py's lists; a value added to one and not the other makes the agent fail."""
    a = open(os.path.join(HERE, "..", "references", "after_assignment.md")).read()
    b = open(os.path.join(HERE, "..", "references", "after_brief.md")).read()
    for v in plan.PATTERNS + plan.CALLS + plan.SFOT_V + plan.CHECK + plan.GUIDE + plan.PLAYED:
        assert v in a, v
    for v in plan.PATTERNS:
        assert v in b, v


def test_bad_values_are_named():
    p = copy.deepcopy(EX)
    p["sfot"]["tone"]["value"] = "great"
    p["react"]["call"] = "buy"
    p["react"]["reason"] = "looks good"
    probs = plan.check(p, CTX)
    assert any(x.startswith("sfot.tone") for x in probs)
    assert any(x.startswith("react.call") for x in probs)
    assert any(x.startswith("react.reason") for x in probs)


def test_call_note_needs_a_quote():
    p = copy.deepcopy(EX)
    first = next(k for k, v in p["call_notes"].items() if v)
    p["call_notes"][first][0].pop("quote")
    assert any(x.startswith(f"call_notes.{first}[0]") for x in plan.check(p, CTX))


def test_topics_must_match_exactly():
    """The Call Notes tab has one row per context topic: a missing or invented topic has nowhere honest to go."""
    p = copy.deepcopy(EX)
    p["call_notes"].pop("Tone")
    p["call_notes"]["Weather"] = []
    probs = plan.check(p, CTX)
    assert any("'Tone' is missing" in x for x in probs) and any("'Weather'" in x for x in probs)


def test_lt_target_must_name_mod_lines():
    p = copy.deepcopy(EX)
    p["lt_target"]["num"] = "INCOME STATEMENT | Nothing"
    assert any(x.startswith("lt_target") for x in plan.check(p, CTX))


def test_no_lt_target_is_fine():
    assert plan.check({**EX, "lt_target": None}, CTX) == []


def test_guidance_catalysts_controversies_need_text():
    """Rows the tab and the note print must say something: an unnamed guidance item or blank catalyst is a gap."""
    p = copy.deepcopy(EX)
    p["guidance"][0]["item"] = ""
    p["catalysts"] = [{"text": "", "when": "May"}]
    p["controversies"] = "one big one"
    probs = plan.check(p, CTX)
    assert any(x.startswith("guidance[0].item") for x in probs)
    assert any(x.startswith("catalysts[0]") for x in probs)
    assert any(x.startswith("controversies") for x in probs)


def test_rerun_needs_played_out():
    p = copy.deepcopy(EX)
    p["played_out"] = None
    assert any(x.startswith("played_out") for x in plan.check(p, {**CTX, "mode": "rerun"}))


@pytest.mark.parametrize("mode,ready", [("first", True), ("rerun", False)])
def test_played_out_not_asked_before_t_plus_7(mode, ready):
    """Before T+7 there is no drift to judge, so asking for played_out would force a guess."""
    assert plan.check({**EX, "played_out": None}, {**CTX, "mode": mode, "drift_ready": ready}) == []
