"""The plan check enforces the chapter's rules and the user's: 1-3 multiples, P/E first unless ruled out, never one
in isolation without saying why, weights that sum to 1, every judgment visible and anchored."""
import copy
import json
import os
import subprocess
import sys

import plan
from conftest import FIX, SCRIPTS

OK = json.load(open(os.path.join(FIX, "plan_example.json")))


def problems(mut, context=None):
    p = copy.deepcopy(OK)
    mut(p)
    return plan.check(p, context or {})


def test_example_is_valid():
    assert plan.check(OK, {}) == []


def test_weights_must_sum_to_one():
    assert any("sum" in x for x in problems(lambda p: p["inputs"]["weight.pe"].update(value=0.9)))


def test_four_multiples_refused():
    assert problems(lambda p: p["multiples"].extend([{"kind": "ev_gp", "role": "floor", "reason": "r"},
                                                     {"kind": "ev_rev", "role": "floor", "reason": "r"}]))


def test_unknown_kind_refused():
    """Code fixes which metric pairs with which value (valmath.METRIC); an EV/EPS mix-up is refused, not computed."""
    assert any("ev_eps" in x for x in problems(lambda p: p["multiples"].append(
        {"kind": "ev_eps", "role": "floor", "reason": "r"})))


def test_exactly_one_primary():
    assert any("primary" in x for x in problems(lambda p: p["multiples"][1].update(role="primary")))


def test_no_pe_needs_a_reason():
    def drop_pe(p):
        p["multiples"] = [{"kind": "ev_ebitda", "role": "primary", "reason": "EBITDA is cleaner"}]
        p["notes"].append("One multiple: the only one that applies.")
    assert any("P/E" in x for x in problems(drop_pe))


def test_no_pe_with_reason_and_single_note_is_ok():
    def drop_pe(p):
        p["multiples"] = [{"kind": "ev_ebitda", "role": "primary", "reason": "P/E is ruled out: one-off tax items."}]
        for k in [k for k in p["inputs"] if k.endswith(".pe")]:
            del p["inputs"][k]
        p["inputs"]["weight.ev_ebitda"]["value"] = 1.0
        p["notes"].append("One multiple: EV/EBITDA is the only one the Street and the company use.")
    assert problems(drop_pe) == []


def test_single_multiple_needs_a_note():
    """The user: one multiple in isolation is where mistakes are made, so one alone must say why."""
    def single(p):
        p["multiples"] = p["multiples"][:1]
        for k in [k for k in p["inputs"] if k.endswith(".ev_ebitda")]:
            del p["inputs"][k]
        p["inputs"]["weight.pe"]["value"] = 1.0
    assert any("one multiple" in x.lower() for x in problems(single))

    def with_note(note):
        return lambda p: (single(p), p["notes"].append(note))
    # The rule is a notes entry that starts "One multiple:", so the agent knows exactly what to write.
    assert problems(with_note("one MULTIPLE: EV/EBITDA is how every holder and the company frame it.")) == []
    assert any("One multiple:" in x for x in problems(with_note("Using only one multiple here.")))
    assert any("One multiple:" in x for x in problems(with_note("Why one multiple: it is the only one used.")))


def test_missing_input_for_a_kind():
    assert any("risk_metric.ev_ebitda" in x for x in problems(lambda p: p["inputs"].pop("risk_metric.ev_ebitda")))


def test_missing_house_key():
    assert any("hurdle" in x for x in problems(lambda p: p["inputs"].pop("hurdle")))


def test_empty_reason_refused():
    assert any("reason" in x for x in problems(lambda p: p["inputs"]["multiple_3y.pe"].update(reason=" ")))


def test_judgment_anchor_only_where_allowed():
    assert problems(lambda p: p["inputs"]["reward_multiple.pe"].update(anchor="judgment"))


def test_judgment_reason_needs_twelve_words():
    assert any("12 words" in x for x in problems(lambda p: p["inputs"]["weight.pe"].update(reason="Because P/E.")))


def test_house_anchor_only_on_house_keys():
    assert problems(lambda p: p["inputs"]["risk_multiple.pe"].update(anchor="house"))


def test_bad_anchor_shape_refused():
    assert problems(lambda p: p["inputs"]["reward_multiple.pe"].update(anchor="the Multiples tab"))


def test_research_line_anchor_accepted():
    assert problems(lambda p: p["inputs"]["reward_multiple.pe"].update(
        anchor="Filings Research/TEST_filings.md:123")) == []


def test_ntm_anchor_kinds():
    """The risk metric is usually an NTM sum, which sits in no single cell; ntm: / ntm1: / y3: anchors name it."""
    assert problems(lambda p: p["inputs"]["risk_metric.pe"].update(anchor="y3:eps")) == []
    assert problems(lambda p: p["inputs"]["risk_multiple.pe"].update(anchor="ntm1:ebitda")) == []
    assert any("not a cell" in x for x in problems(lambda p: p["inputs"]["risk_metric.pe"].update(anchor="ntm:oi")))
    assert any("not a cell" in x for x in problems(lambda p: p["inputs"]["risk_metric.pe"].update(anchor="ntm2:eps")))
    assert any("anchor_value" in x for x in problems(lambda p: p["inputs"]["risk_metric.pe"].pop("anchor_value")))


def test_cell_anchor_needs_anchor_value():
    assert problems(lambda p: p["inputs"]["reward_multiple.pe"].pop("anchor_value"))


def test_multiple_must_be_positive():
    assert problems(lambda p: p["inputs"]["risk_multiple.pe"].update(value=-3.0))


def test_fcf_yield_is_a_yield():
    """An FCF yield typed as 5 (meaning 5%) would value the stock at a 500% yield; it must be a fraction."""
    def fy(p, v):
        p["multiples"].append({"kind": "fcf_yield", "role": "floor", "reason": "cash floor"})
        p["inputs"]["weight.ev_ebitda"]["value"] = 0.3
        p["inputs"]["weight.fcf_yield"] = {"value": 0.1, "anchor": "judgment",
                                           "reason": "A small weight because the cash yield only sets a floor here today."}
        for k, x in (("reward_multiple", v), ("risk_multiple", 0.04), ("multiple_3y", 0.04)):
            p["inputs"][f"{k}.fcf_yield"] = {"value": x, "anchor": "Multiples!B7", "anchor_value": 34.1, "reason": "r"}
        p["inputs"]["risk_metric.fcf_yield"] = {"value": 900.0, "anchor": "MOD!$BV$615", "anchor_value": 900.0,
                                                "reason": "r"}
    assert problems(lambda p: fy(p, 0.03)) == []
    assert any("yield" in x for x in problems(lambda p: fy(p, 5.0)))


def test_position_long_or_short():
    assert any("position" in x for x in problems(lambda p: p["inputs"]["position"].update(value="neutral")))


def test_scenarios_ordered():
    assert problems(lambda p: p["scenarios"]["final"]["bull"].update(value_per_share=0))


def test_scenarios_need_all_cases_and_rounds():
    assert any("bear" in x for x in problems(lambda p: p["scenarios"]["final"].pop("bear")))
    assert any("round" in x for x in problems(lambda p: p["scenarios"].update(rounds=[])))
    assert any("round" in x for x in problems(lambda p: p["scenarios"]["rounds"].extend([{"round": 3}] * 4)))


def test_tree_probabilities_sum_to_one():
    assert problems(lambda p: p["tree"][0]["prob"].update(value=0.99))


def test_tree_rows_four_to_five():
    assert any("4-5" in x for x in problems(lambda p: p.update(tree=p["tree"][:3])))
    assert any("4-5" in x for x in problems(lambda p: p["tree"].extend(p["tree"][:2])))


def test_tree_link_must_be_known():
    assert any("link" in x for x in problems(lambda p: p["tree"][0].update(target={"link": "dcf_moon"})))


def test_street_refs_must_be_cells():
    assert not problems(lambda p: p.update(street={"pe": {"ntm": "Consensus!D12", "ntm1": "Consensus!E12"}}))
    assert any("street" in x for x in problems(lambda p: p.update(street={"pe": {"ntm": "about 2.9"}})))


def test_normalization_checked_when_set():
    def norm(**years):
        return {"year": "2029E",
                "margin": {"value": 0.18, "anchor": "MOD!$CB$276", "anchor_value": 0.33, "reason": "r"},
                "multiple": {"value": 25.0, "anchor": "Multiples!C6", "anchor_value": 26.2, "reason": "r"},
                "years": {"value": 3, "reason": "r", **years}}
    assert problems(lambda p: p.update(normalization=norm(anchor="Filings Research/x.md:9", anchor_value=3))) == []
    assert any("normalization.years" in x for x in problems(lambda p: p.update(normalization=norm(anchor="house"))))
    # Years to discount back are rarely printed anywhere, so they may be a judgment (with a real reason); the margin
    # and multiple may not.
    why = "Earnings normalize once the plant ramps, which the company says takes about three more years."
    assert problems(lambda p: p.update(normalization=norm(anchor="judgment", reason=why))) == []
    assert any("12 words" in x for x in problems(lambda p: p.update(normalization=norm(anchor="judgment"))))
    n = norm(anchor="judgment", reason=why)
    n["margin"].update(anchor="judgment", reason=why)
    assert any("normalization.margin" in x for x in problems(lambda p: p.update(normalization=n)))
    n = norm(anchor="Filings Research/x.md:9", anchor_value=3)
    n["margin"].pop("anchor_value")
    assert any("normalization.margin" in x for x in problems(lambda p: p.update(normalization=n)))
    n = norm(anchor="Filings Research/x.md:9", anchor_value=3)
    n.pop("year")
    assert any("normalization" in x for x in problems(lambda p: p.update(normalization=n)))


def test_nm_when_ntm_eps_negative():
    """A P/E on negative earnings is not meaningful; the check says so and points to the alternatives."""
    ctx = {"metrics": {"eps": {"ntm": {"value": -0.5}}, "ebitda": {"ntm": {"value": 1672.5}}}}
    out = problems(lambda p: None, ctx)
    assert out == ["pe: NTM eps is negative or missing, so the multiple is not meaningful. Use EV/Revenue or EV/GP, "
                   "or normalized EPS."]


def test_nm_when_metric_missing():
    ctx = {"metrics": {"eps": {"ntm": {"value": 2.8856}}, "ebitda": {"ntm": {"value": None}}}}
    assert any(x.startswith("ev_ebitda: NTM ebitda") for x in problems(lambda p: None, ctx))


def test_cli(tmp_path):
    ctx = tmp_path / "context.json"
    ctx.write_text(json.dumps({"metrics": {"eps": {"ntm": {"value": 2.8856}}, "ebitda": {"ntm": {"value": 1672.5}}}}))
    run = lambda pp: subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "plan.py"), "--plan", str(pp),
                                     "--context", str(ctx)], capture_output=True, text=True)
    ok = run(os.path.join(FIX, "plan_example.json"))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    bad = copy.deepcopy(OK)
    bad["inputs"]["weight.pe"]["value"] = 0.9
    bp = tmp_path / "bad.json"
    bp.write_text(json.dumps(bad))
    r = run(bp)
    assert r.returncode == 1 and "sum" in r.stdout


# The overall verdict (the user's 2026-11-18 ask): the agent's own Buy / Hold / Sell at the top of the tab. Nothing in
# code decides it, so the plan check is the only guard: one of three words, and a reason the user can argue with.
def test_verdict_is_required():
    assert any("verdict" in x for x in problems(lambda p: p.pop("verdict")))


def test_verdict_must_be_buy_hold_or_sell():
    assert any("verdict" in x for x in problems(lambda p: p["verdict"].update(value="Strong buy")))


def test_verdict_needs_a_real_reason():
    assert any("verdict" in x for x in problems(lambda p: p["verdict"].update(reason="Looks cheap.")))
