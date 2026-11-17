"""NTM is the next four forecast quarters and NTM+1 the four after (chapter 11.5: forward quarters 5-8), read from MOD
so the tab's links equal what Python used; too short a forecast stops rather than guessing."""
import openpyxl
import pytest

import lo
import metrics
from modmap import ModMap


@pytest.fixture(scope="module")
def got(fixture_model, tmp_path_factory):
    vals = lo.recalc(fixture_model, str(tmp_path_factory.mktemp("v")))
    return metrics.collect(fixture_model, vals), vals


def _refs(formula):
    return [x.split("!")[1].replace("$", "") for x in formula.split("IF(COUNT(")[1].split(")")[0].split(",")]


def test_ntm_is_first_four_forecast_quarters(got, fixture_model):
    m, vals = got
    fq = ModMap(fixture_model).forecast_quarters()
    assert m["eps"]["ntm"]["quarters"] == fq[:4] and m["eps"]["ntm1"]["quarters"] == fq[4:8]
    ws = openpyxl.load_workbook(vals, data_only=True)["MOD"]
    for k in ("rev", "eps"):
        for b in ("ntm", "ntm1"):
            refs = _refs(m[k][b]["formula"])
            assert len(refs) == 4
            assert m[k][b]["value"] == pytest.approx(sum(ws[c].value for c in refs))


def test_every_metric_has_three_blocks(got):
    m, _ = got
    for k in ("eps", "rev", "gp", "ebitda", "fcf"):
        assert {"ntm", "ntm1", "y3"} <= set(m[k])
        assert m[k]["y3"]["value"] is not None
    assert 1 <= m["years3"] <= 3
    assert m["basis"] in ("gaap", "ng")


def test_vol_formula_is_legacy_stdev(got):
    m, _ = got
    assert m["vol"]["formula"].startswith("STDEV(LN(") and "_xlfn" not in m["vol"]["formula"]
    assert 0.05 < m["vol"]["value"] < 2


def test_growth_from_last_actual_year(got):
    m, _ = got
    for k in ("rev", "oi", "eps"):
        g = m["growth"][k]
        assert 1 <= g["years"] <= 3
        assert g["cagr"] == pytest.approx((g["end"] / g["start"]) ** (1 / g["years"]) - 1)


def test_short_forecast_stops(monkeypatch, fixture_model):
    monkeypatch.setattr(ModMap, "forecast_quarters", lambda self: ["Q1 27E", "Q2 27E"])
    with pytest.raises(SystemExit, match="at least 8 forecast quarters"):
        metrics.collect(fixture_model, fixture_model)
