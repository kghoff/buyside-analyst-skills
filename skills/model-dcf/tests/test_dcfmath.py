"""dcfmath: revenue is the forecast plan's revenue identity (any shape: here units x price + other revenue), MOD years
reproduce MOD, each factor's growth fades to its own long-run rate after MOD, costs hold MOD's last year."""
import pytest

from dcfmath import defaults, identity, prepare, run, to_scn, value_only

MOD2 = {"rev": [5000.0, 5500.0], "gp": [3100.0, 3465.0], "opex": [1900.0, 2000.0], "tax_rate": [0.2, 0.21],
        "da": [250.0, 275.0], "capex": [350.0, 385.0], "wc": [-50.0, -60.0]}


def _factors():
    """Year 0 = 2026E: average units (2.0 -> 3.0) x price 1500 + other 750 = 4500; MOD 2027E-2028E reproduces 5000,
    5500 (k = 2)."""
    return [{"name": "Units", "average": True, "long_run": 0.03, "level_prev": 2.0, "level0": 3.0, "mod": [4.0, 5.0]},
            {"name": "Price", "average": False, "long_run": -0.01, "level_prev": 1500.0, "level0": 1500.0,
             "mod": [4200 / 3.5, 4600 / 4.5]},
            {"name": "Other revenue", "average": False, "long_run": 0.0, "level_prev": 700.0, "level0": 750.0,
             "mod": [800.0, 900.0]}]


def _ctx2():
    return {"k": 2, "year0": "2026E", "rev0": 4500.0, "gm0": 0.6, "opex0": 1800.0, "net_debt": 0.0, "shares": 100.0,
            "history": [{"year": "2025", "rev": 4000.0}], "mod": dict(MOD2), "factors": _factors(),
            "terms": [[0, 1], [2]]}


def _flat_ctx():
    """No MOD years (k = 0 is not allowed by to_scn; run() is fed directly): one factor, revenue = 4500."""
    return {"k": 0, "year0": "2026E", "rev0": 4500.0, "gm0": 0.6, "opex0": 1000.0, "wacc": 0.08, "tv_mult": 10,
            "net_debt": 0.0, "shares": 100.0, "mod": {}, "terms": [[0]],
            "factors": [{"name": "Revenue", "average": False, "long_run": 0.0, "level_prev": 4500.0, "level0": 4500.0,
                         "mod": []}]}


def _scn(n, g=0.0, dgm=0.0):
    flat = lambda v: [v] * 30
    return {"g": [flat(g) for _ in range(n)], "dgm": flat(dgm), "opex_inc": flat(0.0), "tax": flat(0.0),
            "da_pct": flat(0.0), "capex_pct": flat(0.0), "wc_inc": flat(0.0)}


def test_flat_business_is_an_annuity_plus_terminal_multiple():
    r = run(_scn(1), _flat_ctx())
    assert r["ufcf"][0] == pytest.approx(1700) and r["ufcf"][29] == pytest.approx(1700)
    annuity = sum(1700 / 1.08 ** t for t in range(1, 31))
    assert r["ev"] == pytest.approx(annuity + 10 * 1700 / 1.08 ** 30)
    assert value_only(_scn(1), _flat_ctx()) == pytest.approx(r["ev"] / 100)


def test_identity_is_a_sum_of_products_with_averages():
    c = _ctx2()
    assert identity([3.0, 1500.0, 750.0], [2.0, 1500.0, 700.0], c) == pytest.approx(2.5 * 1500 + 750)


def test_mod_years_reproduce_mod_and_later_years_grow_each_factor_at_its_input():
    """2027-2028 come from MOD's driver rows, so revenue and operating income are the user's forecast exactly; after that
    revenue follows the factors."""
    ctx = _ctx2()
    d = defaults(ctx, {"Units": {"2029E": 0.10}, "Price": {"2029E": -0.02}, "Other revenue": {"2029E": 0.05}})
    c = prepare(ctx, d)
    r = run(to_scn(d, c), c)
    assert r["rev"][:2] == pytest.approx([5000, 5500]) and r["oi"][:2] == pytest.approx([1200, 1465])
    assert r["capex"][1] == pytest.approx(385) and r["wc"][1] == pytest.approx(-60)
    assert r["rev"][2] == pytest.approx((5.0 + 5.5) / 2 * (4600 / 4.5) * 0.98 + 900 * 1.05)


def test_defaults_fade_each_factor_to_its_own_long_run_over_ten_years():
    """The long-run rates come from the forecast plan (the user owns them); the fade is a straight line, then holds."""
    d = defaults(_ctx2())
    last = {"Units": 5.0 / 4.0 - 1, "Price": (4600 / 4.5) / (4200 / 3.5) - 1, "Other revenue": 900 / 800 - 1}
    lr = {"Units": 0.03, "Price": -0.01, "Other revenue": 0.0}
    dgm_last = (3465 / 5500 - 3100 / 5000) * 10000
    for y, s in (("2029E", 0.1), ("2033E", 0.5), ("2038E", 1.0), ("2056E", 1.0)):
        for n in last:
            assert d[n][y] == pytest.approx(last[n] + (lr[n] - last[n]) * s), (n, y)
        assert d["dgm"][y] == pytest.approx(dgm_last * (1 - s)), y
    assert "2028E" not in d["Units"] and "2028E" not in d["dgm"]       # MOD years are not inputs
    assert d["wacc"] == 0.08 and d["tv_mult"] == 10


def test_default_cost_inputs_hold_the_last_mod_year():
    d = defaults(_ctx2())
    for y in ("2029E", "2056E"):
        assert d["opex_inc"][y] == pytest.approx(100 / 500)
        assert d["tax"][y] == pytest.approx(0.21) and d["da_pct"][y] == pytest.approx(275 / 5500)
        assert d["capex_pct"][y] == pytest.approx(385 / 5500) and d["wc_inc"][y] == pytest.approx(60 / 500)


def test_kept_values_win():
    d = defaults(_ctx2(), {"Units": {"2050E": 0.01}, "tax": {"2040E": 0.25}, "wacc": 0.09})
    assert d["Units"]["2050E"] == 0.01 and d["tax"]["2040E"] == 0.25 and d["wacc"] == 0.09


def test_to_scn_names_a_missing_year():
    d = defaults(_ctx2())
    del d["dgm"]["2040E"]
    with pytest.raises(ValueError, match="dgm is missing year 2040E"):
        to_scn(d, prepare(_ctx2(), d))


def test_run_rejects_an_identity_that_misses_year0_revenue():
    c = _flat_ctx()
    c["rev0"] = 5000.0
    with pytest.raises(ValueError):
        run(_scn(1), c)
