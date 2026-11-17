# tests/test_valmath.py
"""Chapter 11's worked examples. If any of these change, the tab teaches a different method than the course."""
import math

import pytest

import valmath as V


def r(x, n=1):
    return round(x, n)


def test_abt_row_pe():                      # 10/25/22: $98 / $4.58 = 21.4x
    assert r(V.multiple_now("pe", 98, 4.58)) == 21.4


def test_reward_risk_and_ladder():          # 20x * $4.00 = $80; 13x * $2.65 = $34.45; at $50: 60.0% / (31.1%) / 1.9x
    reward = V.price_from_multiple("pe", 20, 4.00)
    risk = V.price_from_multiple("pe", 13, 2.65)
    assert (reward, r(risk, 2)) == (80.0, 34.45)
    up, down, rr = V.reward_risk(50, reward, risk)
    assert (r(up * 100), r(down * 100), r(rr)) == (60.0, 31.1, 1.9)
    lad = V.ladder(reward, risk, entries=[57, 46])
    assert [(e, r(u * 100), r(d * 100), r(x)) for e, u, d, x in lad] == [(57, 40.4, 39.6, 1.0), (46, 73.9, 25.1, 2.9)]


def test_ladder_default_steps_are_minus_15_to_plus_15():
    lad = V.ladder(80, 34.45, price=50)
    assert [e for e, *_ in lad] == pytest.approx([42.5, 45, 47.5, 50, 52.5, 55, 57.5])


def test_short_flips_reward_and_risk():     # a short gains if the stock falls to the risk price
    up, down, _ = V.reward_risk(50, 80, 34.45, short=True)
    assert (r(up * 100), r(down * 100)) == (31.1, 60.0)


def test_irr_3_year_double():               # $1.00 -> $1.33, 10x -> 15x: $10 -> ~$20, a 26% IRR
    s = V.irr_split(1.00, 1.33, 10, 15, 3)
    assert r(s["irr"] * 100, 0) == 26
    assert r(s["growth"] * 100, 1) == 10.0 and r(s["rerate"] * 100, 1) == 14.5
    assert V.double_path(10, 15, 1.00, 1.33) == "both"
    assert V.double_path(10, 20, 1.00, 1.00) == "P/E expansion"
    assert V.double_path(40, 40, 1.00, 2.00) == "EPS growth"


def test_normalized_price():                # 20x * $1.24 = $24.80 -> $16.31 at 15% over 3 years
    p, d = V.normalized(20, 1.24, 0.15, 3)
    assert (r(p, 2), r(d, 2)) == (24.80, 16.31)


def test_reverse_pe():                      # $438.75 / 45x = $9.75 of earnings power
    assert V.reverse_pe(438.75, 45) == 9.75


def test_probability_tree():                # $68.39, 36.8%
    ev, ret = V.tree([(100, .1), (90, .1), (80, .5), (34.45, .2), (25, .1)], price=50)
    assert (r(ev, 2), r(ret * 100)) == (68.39, 36.8)
    with pytest.raises(ValueError):
        V.tree([(100, .5), (50, .4)], price=50)


def test_leverage_distorts_pe_not_ev_ebitda():   # 16.7x vs 12.1x on the same business; EV/EBITDA 10x for both
    assert r(V.multiple_now("pe", 10, 0.60)) == 16.7
    assert r(V.multiple_now("pe", 5, 0.4125)) == 12.1
    a = V.multiple_now("ev_ebitda", 10, 10, net_debt=0, shares=10)
    b = V.multiple_now("ev_ebitda", 5, 10, net_debt=50, shares=10)
    assert a == b == 10.0
    assert V.price_from_multiple("ev_ebitda", 10, 10, net_debt=50, shares=10) == 5.0   # EV bridge to equity


def test_pairing_is_fixed():
    assert V.METRIC == {"pe": "eps", "fcf_yield": "fcf", "ev_rev": "rev", "ev_gp": "gp", "ev_ebitda": "ebitda"}
    assert V.LEVERED == {"pe", "fcf_yield"}


def test_reward_to_vol_and_one_sigma():     # 40% reward on 20% vol = 2.0x
    assert V.reward_to_vol(0.40, 0.20) == 2.0
    assert V.inside_one_sigma(0.15, 0.30, 12) is True       # a 15% risk case on a 30%-vol stock is too gentle
    assert V.inside_one_sigma(0.35, 0.30, 12) is False


def test_verdict():
    assert [V.verdict(x, 2, 3) for x in (1.9, 2.0, 3.0)] == ["below hurdle", "buy", "table-pound"]


def test_annual_vol():
    closes = [100 * math.exp(0.01 * (i % 2)) for i in range(253)]   # alternating +-1% log moves
    assert r(V.annual_vol(closes), 3) == r(0.01 * 252 ** 0.5 * (252 / 251) ** 0.5, 3)


def test_gap_flag():                        # DCF vs multiple target: over 25% apart is flagged, not averaged away
    assert V.gap(130, 100) is True and V.gap(120, 100) is False
