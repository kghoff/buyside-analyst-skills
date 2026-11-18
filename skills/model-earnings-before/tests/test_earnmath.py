# skills/model-earnings-before/tests/test_earnmath.py
"""The math checked against the chapter's own exhibits: if a formula is wrong, the chapter's numbers come out wrong.
The stance rule is tested at every threshold, because the rule (not the agent) decides add / hold / trim / hedge."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pytest

import earnmath as em


def test_core_formula_moves():
    # 13.1: guide cut $1.00 -> $0.75 and 20x -> 18x takes a third off; 13.2: +10% EPS and +10% P/E = +21%
    assert em.move(20.0, 18.0, 0.75) == pytest.approx(-0.325)
    assert em.move(20.0, 22.0, 1.10) == pytest.approx(0.21)
    assert em.move(0, 22.0, 1.10) is None


def test_reward_risk_and_implied_psuc_match_section_13_6_and_medp():
    assert round(em.rr(0.21, -0.0975), 1) == 2.2
    assert round(em.psuc(0.21, -0.0975), 3) == 0.317
    assert round(em.rr(0.375, -0.0975), 1) == 3.8          # MEDP Q3 22
    assert round(em.psuc(0.375, -0.0975), 3) == 0.206
    assert em.psuc(0.10, -0.10) == pytest.approx(0.5)       # coin flip
    assert round(em.psuc(0.06, -0.30), 3) == 0.833          # merger arbitrage
    assert round(em.psuc(1.00, -0.10), 3) == 0.091          # 10-to-1 biotech
    assert em.rr(-0.05, -0.10) is None and em.psuc(0.1, 0.05) is None   # not a two-sided bet


def test_two_year_stack_both_ways():
    assert round(em.stack_rates(0.05, 0.062), 3) == 0.115   # (1.050 x 1.062) - 1
    x0, x1 = 100.0, 106.2
    x2 = x1 * 1.05
    assert em.growth(x2, x0) == pytest.approx(em.stack_rates(0.05, 0.062))
    assert em.growth(5.0, -1.0) is None and em.growth(5.0, 0) is None


def test_daily_sigma_table():
    assert round(em.daily_sigma(0.25), 3) == 0.016          # medtech 1-sigma
    assert round(3 * em.daily_sigma(0.25), 3) == 0.047
    assert round(em.daily_sigma(0.60), 3) == 0.038          # biotech
    assert round(3 * em.daily_sigma(0.60), 3) == 0.113
    assert em.annual_sigma(em.daily_sigma(0.25)) == pytest.approx(0.25)


def test_hockey_stick_fires_on_the_aggressive_guide_only():
    # 13.5: Q3 22E yoy 10.0% vs 2.5%, stack 12.8% vs 7.1%, q/q -7.4% vs average -13.2%: three red flags
    assert em.hockey(0.10, 0.025, 0.128, 0.071, -0.074, -0.132) is True
    # Q2 22 of the same table: yoy up, stack down -> not a hockey stick
    assert em.hockey(0.025, 0.015, 0.071, 0.091, 0.113, 0.12) is False
    # AMZN Q4 22 guide: 13.3% q/q against 31.5% average seasonality -> conservative, not a hockey stick
    assert em.hockey(0.048, 0.147, 0.147, 0.322, 0.133, 0.315) is False
    assert em.hockey(None, 0.1, 0.1, 0.1, 0.1, 0.1) is None


def test_setup_code_row():
    H = em.HOUSE
    assert em.setup_code(0.25, -0.08, H) == "long"
    assert em.setup_code(0.85, 0.06, H) == "short"
    assert em.setup_code(0.85, -0.06, H) == "neutral"       # rich but already lagging: not a short set-up by itself
    assert em.setup_code(None, 0.06, H) == "unknown"
    assert em.net(["long", "short", "long", "neutral", "unknown"]) == 1


def test_blowup_flags():
    f = em.blowups(0.20, 10.0, 5.0, 50.0, 0.85)
    assert f == {"margins": True, "peak_pe": True, "cash": False}
    assert em.blowups(0.05, -1.0, 5.0, 50.0, 0.5)["cash"] is True          # losing money
    assert em.blowups(0.05, 1.0, -60.0, 50.0, 0.5)["cash"] is True         # burning more than the cash it has
    assert em.blowups(0.05, 1.0, -40.0, 50.0, 0.5)["cash"] is False
    assert em.blowups(0.05, 1.0, -40.0, None, 0.5)["cash"] is None
    assert em.blowups(None, None, None, None, None) == {"margins": None, "peak_pe": None, "cash": None}
    assert [em.flag_text(x) for x in (True, False, None)] == ["yes", "no", "?"]


def test_habitual_raiser_needs_three_of_the_last_four():
    assert em.habitual([0.02, 0.03, -0.01, 0.04, 0.02]) is True     # last four: 3 beats
    assert em.habitual([0.03, -0.01, -0.02, 0.04]) is False
    assert em.habitual([0.03, 0.02]) is None


H = em.HOUSE


@pytest.mark.parametrize("rr,edge,net,nb,down,implied,want", [
    (2.0, 0.10, 0, 1, -0.10, None, "add"),          # every add threshold exactly met
    (1.99, 0.10, 0, 1, -0.10, None, "hold"),
    (2.0, 0.10, -1, 1, -0.10, None, "hold"),        # set-up net short blocks add
    (2.0, 0.10, 0, 2, -0.10, None, "hedge"),        # two blow-up flags: no add, print risk without a view
    (3.0, -0.10, 2, 0, -0.10, None, "trim"),        # edge 10 pts below the implied PSUC
    (0.9, 0.0, -1, 0, -0.10, None, "trim"),         # R/R under 1 with the set-up net short
    (0.9, 0.0, 0, 0, -0.10, None, "hold"),
    (1.5, 0.05, 0, 0, -0.15, 0.10, "hedge"),        # downside 1.5x the implied move
    (1.5, 0.05, 0, 0, -0.14, 0.10, "hold"),
    (None, 0.05, 0, 0, -0.14, 0.10, None),
])
def test_stance_rule_at_each_threshold(rr, edge, net, nb, down, implied, want):
    assert em.stance(rr, edge, net, nb, down, implied, H) == want


def test_base_stats():
    s = em.base_stats([0.04, -0.06, 0.03, None])
    assert s["n"] == 3 and s["up"] == 2 and s["down"] == 1
    assert s["avg_abs"] == pytest.approx(0.13 / 3) and s["med_abs"] == pytest.approx(0.04)
    assert em.base_stats([])["avg_abs"] is None


def test_summary_uses_code_side_unless_the_plan_overrides():
    ctx = {"price": {"value": 20.0}, "house": dict(em.HOUSE), "yahoo": {"implied_move": None},
           "code": {"setup": {"value_perf": "long"}, "blowups": {"margins": False, "cash": False, "peak_pe": None}}}
    inp = {"up_eps": 1.10, "up_pe": 22.0, "down_eps": 0.95, "down_pe": 19.0, "p_beat": 0.45}
    s = em.summary(ctx, inp, {"consensus": "long"})
    assert s["up"] == pytest.approx(0.21) and s["down"] == pytest.approx(-0.0975)
    assert s["sides"]["value_perf"] == "long" and s["sides"]["view"] == "unknown"
    assert s["net"] == 2 and s["nblow"] == 0
    assert s["edge"] == pytest.approx(0.45 - 0.0975 / 0.3075)
    assert s["rule"] == "add"                      # 2.2x, edge +13 pts, net long, no flags
    s2 = em.summary(ctx, inp, {"value_perf": "short", "consensus": "short"})
    assert s2["net"] == -2 and s2["rule"] == "hold"
