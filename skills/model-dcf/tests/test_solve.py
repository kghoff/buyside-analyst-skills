"""solve.py: value per share for the user's inputs and the reverse DCF, one driver at a time, the shift added to their first
five input years after MOD (so the user can reproduce a row by typing it into five yellow cells), for today's price and
the 3-year high and low. No scenarios, blend, grid or tree."""
import pytest

import solve as S
from dcfmath import defaults, prepare, to_scn, value_only
from test_dcfmath import _ctx2


def _ctx(last=60.0):
    c = _ctx2()
    c["price"] = {"last": {"date": "2026-11-06", "value": last}, "high3y": {"date": "2024-06-03", "value": 90.0},
                  "low3y": {"date": "2025-03-03", "value": 20.0}}
    return c


def _shifted_value(d, x):
    ctx = _ctx()
    inp = S.shift(defaults(ctx), ctx, d, x)
    c = prepare(ctx, inp)
    return value_only(to_scn(inp, c), c)


def test_value_per_share_is_dcfmath_for_the_inputs():
    out = S.solve(_ctx())
    c = prepare(_ctx(), out["inputs"])
    assert out["value_per_share"] == pytest.approx(value_only(to_scn(out["inputs"], c), c))
    assert set(out) >= {"inputs", "value_per_share", "tv_share", "reverse", "kept", "defaulted", "as_of", "user",
                        "shift_years"}
    for gone in ("scenario_values", "expected_value", "grid", "implied", "implied_note"):
        assert gone not in out


def test_shift_adds_to_the_first_five_input_years_after_mod():
    """k = 2 (MOD 2027E-2028E): the shift lands on 2029E-2033E, the yellow cells the user would type into."""
    ctx = _ctx()
    inp = defaults(ctx)
    sh = S.shift(inp, ctx, "Price", 0.02)
    for y in ("2029E", "2030E", "2031E", "2032E", "2033E"):
        assert sh["Price"][y] == pytest.approx(inp["Price"][y] + 0.02)
    for y in ("2034E", "2056E"):
        assert sh["Price"][y] == inp["Price"][y]
    assert inp["Price"]["2029E"] != sh["Price"]["2029E"]          # input not mutated
    assert S.shift_years(ctx) == ["2029E", "2030E", "2031E", "2032E", "2033E"]


def test_known_root_recovered_for_each_driver_and_each_price():
    """The drivers are whatever the revenue identity names, plus the gross-margin change."""
    for d, x in (("Units", 0.02), ("Price", -0.015), ("dgm", 25.0)):
        p = _shifted_value(d, x)
        ctx = _ctx(last=p)
        r = S.solve(ctx)["reverse"]
        assert set(r) == {"last", "high3y", "low3y"}
        assert set(r["last"]) == {"price", "Units", "Price", "Other revenue", "dgm"}
        assert r["last"][d]["shift"] == pytest.approx(x, abs=1e-6 if d != "dgm" else 1e-3)
        assert r["last"][d]["value"] == pytest.approx(p, abs=1e-4)
        assert _shifted_value(d, r["last"][d]["shift"]) == pytest.approx(p, abs=1e-4)   # reproducible from the inputs


def test_price_beyond_reach_is_out_of_range():
    r = S.solve(_ctx(last=1e9))["reverse"]["last"]
    assert r["Units"]["status"] == "out of range" and r["dgm"]["status"] == "out of range"


def test_kept_and_defaulted_cover_every_input_cell():
    out = S.solve(_ctx(), kept={"Units": {"2029E": 0.12, "2030E": 0.1}, "wacc": 0.09}, kept_from="existing")
    assert out["kept"] == {"Units": ["2029E", "2030E"], "wacc": ["value"]}
    assert out["defaulted"]["Units"][0] == "2031E" and out["defaulted"]["tv_mult"] == ["value"]
    assert out["defaulted"]["tax"][0] == "2029E" and out["defaulted"]["Price"][0] == "2029E"   # MOD years are links
    assert out["inputs"]["wacc"] == 0.09 and out["kept_from"] == "existing"
