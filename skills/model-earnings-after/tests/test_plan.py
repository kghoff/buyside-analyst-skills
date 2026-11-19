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
       "mod_keys": ["INCOME STATEMENT | Revenue", "INCOME STATEMENT | Operating Income"],
       "docs": {"transcript": mf.TRANSCRIPT, "release": mf.RELEASE, "preview": mf.PREVIEW}}


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


@pytest.mark.parametrize("mode", ["first", "rerun"])
def test_played_out_needed_once_the_drift_is_in(mode):
    """Once T+7 has closed the drift is there to judge, on the T+7 rerun or on a first run made after T+7: a
    first run late in the season must not skip the question."""
    p = copy.deepcopy(EX)
    p["played_out"] = None
    assert any(x.startswith("played_out") for x in plan.check(p, {**CTX, "mode": mode, "drift_ready": True}))


@pytest.mark.parametrize("mode", ["first", "rerun"])
def test_played_out_not_asked_before_t_plus_7(mode):
    """Before T+7 there is no drift to judge, so asking for played_out would force a guess."""
    assert plan.check({**EX, "played_out": None}, {**CTX, "mode": mode, "drift_ready": False}) == []


def test_percent_target_is_one_fraction():
    """The pace math compares the target with Operating Income / Revenue, a fraction: a 20 typed for 20% would read
    as 2,000%, and a target that differs from the number printed in the source is not the company's target."""
    for tgt, av in ((20, 20), (0.20, 20), (0.25, 0.20)):
        p = copy.deepcopy(EX)
        p["lt_target"]["target"], p["lt_target"]["anchor_value"] = tgt, av
        assert any(x.startswith("lt_target") for x in plan.check(p, CTX)), (tgt, av)
    p = copy.deepcopy(EX)
    p["lt_target"]["year"] = True                           # a bool is not a year
    assert any(x.startswith("lt_target") for x in plan.check(p, CTX))


def test_quotes_need_four_words():
    p = copy.deepcopy(EX)
    p["call_notes"]["Tone"][0]["quote"] = "feel better"
    assert any(x.startswith("call_notes.Tone[0]") and "4 words" in x for x in plan.check(p, CTX))


def test_call_items_cite_the_call_documents():
    """SFOT, call notes and guidance summarize this print: a broker note or an old call is not what was said."""
    p = copy.deepcopy(EX)
    p["sfot"]["tone"]["anchor"] = "Sellside Research/_md/broker.md:4"
    p["guidance"][0]["anchor"] = "Earnings Calls/_md/2026 Q3 TEST call.md:4"
    probs = plan.check(p, CTX)
    assert any(x.startswith("sfot.tone") and "call's own documents" in x for x in probs)
    assert any(x.startswith("guidance[0]") and "call's own documents" in x for x in probs)
    p = copy.deepcopy(EX)
    p["lt_target"]["anchor"] = "Investor Day/_md/2025 investor day.md:12"     # any file under R is fine here
    assert plan.check(p, CTX) == []


def test_surprise_names_its_comparison():
    """'Revenue was strong' is not a surprise; a surprise is against a number (frozen forecast, consensus...)."""
    p = copy.deepcopy(EX)
    p["sfot"]["surprise"]["reason"] = "Revenue was strong across every region and every product this quarter."
    assert any(x.startswith("sfot.surprise") and "versus what" in x for x in plan.check(p, CTX))


def test_silent_sfot_row_is_allowed():
    """A call that never mentions tone or outlook gets a neutral row saying so, not a forced quote."""
    p = copy.deepcopy(EX)
    p["sfot"]["outlook"] = {"value": "neutral", "anchor": "none",
                            "reason": "The call and the release were silent on guidance for the coming year."}
    assert plan.check(p, CTX) == []
    p["sfot"]["outlook"]["value"] = "positive"
    assert any(x.startswith("sfot.outlook") for x in plan.check(p, CTX))


def test_counts_and_guidance_text():
    p = copy.deepcopy(EX)
    p["call_notes"]["Tone"] = p["call_notes"]["Tone"] * 4
    p["guidance"][0]["now"] = ""
    probs = plan.check(p, CTX)
    assert any("at most 3 points" in x for x in probs) and any(x.startswith("guidance[0].now") for x in probs)


def test_malformed_plan_is_listed_not_crashed():
    """The agent fixes what plan.py lists; a crash tells it nothing."""
    assert plan.check("not a plan", CTX)[0].startswith("plan:")
    p = copy.deepcopy(EX)
    p["sfot"] = "all positive"
    p["call_notes"]["Tone"] = ["a string"]
    p["call_notes"]["Capital allocation"] = "buybacks"
    p["guidance"] = [None]
    p["lt_target"] = "20%"
    p["checkpoint"] = "green"
    p["react"] = None
    p["catalysts"] = None
    p["controversies"] = [3]
    probs = plan.check(p, CTX)
    for k in ("sfot", "call_notes.Tone[0]", "call_notes.Capital allocation", "guidance[0]", "lt_target",
              "checkpoint", "react.call", "catalysts", "controversies"):
        assert any(x.startswith(k) for x in probs), k
