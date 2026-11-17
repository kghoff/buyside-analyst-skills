"""NTM is the next four forecast quarters and NTM+1 the four after (chapter 11.5: forward quarters 5-8), read from MOD
so the tab's links equal what Python used; too short a forecast stops rather than guessing."""
import re

import openpyxl
import pytest

import lo
import metrics
import valmath
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
    """The tab's formula covers exactly the last 252 daily returns in Px Data, and Python's value is that formula's."""
    m, vals = got
    f = m["vol"]["formula"]
    assert f.startswith("STDEV(LN(") and "_xlfn" not in f
    col, a, b, c, d = re.fullmatch(r"STDEV\(LN\('Px Data'!\$(\w+)\$(\d+):\$\w+\$(\d+)/'Px Data'!\$\w+\$(\d+):"
                                   r"\$\w+\$(\d+)\)\)\*SQRT\(252\)", f).groups()
    a, b, c, d = map(int, (a, b, c, d))
    ws = openpyxl.load_workbook(vals, data_only=True)["Px Data"]
    closes = {r: ws[f"{col}{r}"].value for r in range(5, ws.max_row + 1)}
    last = max(r for r, v in closes.items() if isinstance(v, (int, float)))
    assert b == last and d == last - 1 and a == last - 251 and c == last - 252 and b - a + 1 == 252
    assert m["vol"]["value"] == pytest.approx(valmath.annual_vol([closes[r] for r in range(c, b + 1)]), rel=1e-12)


def test_growth_from_last_actual_year(got, fixture_model):
    """Growth starts at the year before the first forecast year, and its ends are the MOD cells the tab links to."""
    m, vals = got
    fy = ModMap(fixture_model).forecast_years()
    ws = openpyxl.load_workbook(vals, data_only=True)["MOD"]
    for k in ("rev", "oi", "eps"):
        g = m["growth"][k]
        assert g["years"] == min(3, len(fy))
        assert g["start_ref"].split("$")[1] == ModMap(fixture_model).col(str(int(fy[0][:4]) - 1))
        assert g["start"] == pytest.approx(ws[g["start_ref"][4:].replace("$", "")].value)
        assert g["end"] == pytest.approx(ws[g["end_ref"][4:].replace("$", "")].value)
        assert g["cagr"] == pytest.approx((g["end"] / g["start"]) ** (1 / g["years"]) - 1)


def test_missing_last_actual_year_stops(monkeypatch, fixture_model):
    """No MOD column for the year growth starts from: a message naming the year, not a KeyError."""
    real = ModMap.forecast_years
    monkeypatch.setattr(ModMap, "forecast_years", lambda self: ["1990E"] + real(self))
    with pytest.raises(SystemExit, match="1989"):
        metrics.collect(fixture_model, fixture_model)


def test_short_forecast_stops(monkeypatch, fixture_model):
    monkeypatch.setattr(ModMap, "forecast_quarters", lambda self: ["Q1 27E", "Q2 27E"])
    with pytest.raises(SystemExit, match="at least 8 forecast quarters"):
        metrics.collect(fixture_model, fixture_model)
