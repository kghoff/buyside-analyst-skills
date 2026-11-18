# skills/model-short/tests/test_shortmath.py
"""The chapter's own exhibits as test cases: if the math stops reproducing Brett's numbers, these fail."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import shortmath as sm  # noqa: E402

A = pytest.approx


def test_subpar_algorithm_path_exhibit_30():
    # EPS $1.00 growing 3% a year at a constant 25x: $25.00, 25.75, 26.52, 27.32, 28.14
    prices = [round(p, 2) for _, p in sm.roll_path(1.0, 0.03, 25.0)]
    assert prices == [25.00, 25.75, 26.52, 27.32, 28.14]


def test_roll_irr_is_growth_plus_dividend_and_wedge_against_hurdle():
    assert sm.roll_irr(0.03, 0.0) == A(0.03)
    assert sm.wedge(0.08, sm.roll_irr(0.03, 0.01)) == A(0.04)       # > 0: a filler-short candidate
    assert sm.roll_irr(None, 0.01) is None and sm.wedge(0.08, None) is None


def test_print_risk_move_exhibit_39():
    # EPS misses 5% ($1.00 -> $0.95) and the P/E slips 20x -> 19x: $20.00 -> $18.05
    assert sm.print_move(-0.05, 20.0, 1.0) == A(18.05 / 20 - 1)


def test_var_sizing_exhibit_34_entry_and_press():
    s = sm.var_size(1000.0, 50.0, 0.50, 500.0)               # $1bn fund, 50 bps, risk case +50%
    assert (s["budget"], s["max_pos"], s["pct_book"]) == (A(5.0), A(10.0), A(0.02))
    assert sm.rr(0.70, 0.50) == A(1.4)
    assert round(sm.rr(0.80, 0.30), 1) == 2.7                  # after the squeeze: better R/R, half the budget gone


def test_p_fcf_elan_vs_zts():
    assert round(sm.p_fcf(30.0, 0.256)) == 117 and round(sm.p_fcf(30.0, 0.947)) == 32


def test_risk_case_takes_the_largest_and_roll_forward_is_a_risk():
    c = sm.risk_cases(10.0, dream_price=14.0, ntm_growth=0.30, takeout=0.25)
    assert c == {"dream": A(0.4), "roll": A(0.30), "takeout": A(0.25)}
    assert sm.risk_of(c) == A(0.4)
    assert sm.risk_of({"dream": None, "roll": 0.3, "takeout": None}) == A(0.3)   # 30% growth, no crack: lose 30%


def test_reward_is_the_fall_to_the_reward_price():
    assert sm.reward(20.0, 10.0) == A(0.5) and sm.reward(20.0, None) is None


def test_borrow_drag_and_crowding():
    assert sm.borrow_drag(0.30, 0.0) == A(0.30)                # 30% borrow eats a 30% fall (chapter: $10 -> $7)
    assert sm.borrow_drag(None, 0.01) is None
    assert sm.crowded(0.12, 0.10) == "crowded" and sm.crowded(0.02, 0.10) == "not crowded"
    assert sm.crowded(None, 0.10) == "n/a"


def _ticks(f=0, e=0, v=0):
    """f / e / v rows ticked yes in each dimension, the rest no."""
    out, n = {}, {"F": f, "E": e, "V": v}
    for rid, dim, _, _ in sm.ROWS:
        out[rid] = "yes" if n[dim] > 0 else "no"
        n[dim] -= 1
    return out


def test_a_dimension_passes_at_half_its_rows():
    p = sm.passes(_ticks(5, 2, 2))
    assert p == {"F": True, "E": True, "V": True}
    assert sm.passes(_ticks(4, 1, 1)) == {"F": False, "E": False, "V": False}
    t = _ticks(5, 2, 2)
    t["decel"] = "unknown"                                    # ? does not count as a tick
    assert sm.passes(t)["F"] is False


def test_verdict_rule_top_to_bottom():
    assert sm.verdict(_ticks(5, 2, 2), True, 1.4, -0.1) == "Alpha short"
    assert sm.verdict(_ticks(5, 2, 2), False, 1.4, -0.1) == "Watchlist"          # no catalyst: not alpha
    assert sm.verdict(_ticks(5, 2, 2), True, 1.3, -0.1) == "Watchlist"           # R/R under 1.4x
    assert sm.verdict(_ticks(1, 0, 2), False, None, 0.02) == "Filler short"      # wedge > 0, V passes, one F tick
    assert sm.verdict(_ticks(0, 0, 2), False, None, 0.02) == "No short"          # filler needs a fundamentals tick
    assert sm.verdict(_ticks(5, 0, 2), False, None, -0.02) == "Watchlist"
    assert sm.verdict(_ticks(2, 1, 1), True, 3.0, 0.05) == "No short"


def test_code_ticks_follow_the_thresholds():
    t = sm.code_ticks({"decel": -0.02, "incr": 0.10, "opm": 0.20, "peak_ratio": 0.5, "capex_da": 1.6,
                       "acq_cfo": 0.1, "fcf_conv": 0.65, "revision": 0.0, "price": 50, "dcf_base": 60,
                       "peer_pct": 0.7, "pe_pct": None, "wedge": 0.01})
    assert t == {"decel": "yes", "incr_margin": "yes", "capex": "yes", "leaky": "no", "fcf": "yes",
                 "revisions": "no", "vs_dcf": "no", "vs_peers": "yes", "vs_history": "unknown", "vs_algo": "yes"}


def test_rows_types_buckets_match_the_chapter():
    assert [d for _, d, _, _ in sm.ROWS].count("F") == 9
    assert [d for _, d, _, _ in sm.ROWS].count("E") == 4
    assert [d for _, d, _, _ in sm.ROWS].count("V") == 4
    assert len(sm.BUCKETS) == 9 and "Subpar algorithm" in sm.TYPES and "Fraud" in sm.TYPES


def test_a_guarded_metric_gives_a_question_mark():
    """context.py returns None for a ratio over a loss or a fall (fcf_conv, incr); the row is then ?, never a tick.
    A guarded peak ratio (loss-making peak) leaves the incremental-vs-TTM test alone."""
    t = sm.code_ticks({"incr": None, "opm": 0.10, "fcf_conv": None})
    assert t["incr_margin"] == "unknown" and t["fcf"] == "unknown"
    t = sm.code_ticks({"incr": 0.05, "opm": 0.10, "peak_ratio": None})
    assert t["incr_margin"] == "yes"
