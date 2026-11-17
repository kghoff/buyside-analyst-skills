"""The agent's driver sets go through model-dcf's own math (so the scenario table matches the DCF tab exactly); the
compact forms expand like model-dcf's fades; a name model-dcf doesn't know is refused, not ignored."""
import json
import os
import subprocess
import sys

import pytest

import scenarios
from conftest import SCRIPTS

EVAL = os.path.join(SCRIPTS, "scenario_eval.py")
YEARS = ["2031E", "2032E", "2033E"]
BASE = {"Revenue": {y: 0.10 for y in YEARS}, "dgm": {y: 0.0 for y in YEARS}, "wacc": 0.08, "tv_mult": 10.0}


def test_expand_forms():
    names = ["Revenue", "dgm", "wacc", "tv_mult"]
    out = scenarios.expand({"Revenue": {"from": 0.2, "to": 0.05, "over": 2}, "dgm": 25, "wacc": 0.09}, BASE, YEARS, names)
    assert out["Revenue"] == pytest.approx({"2031E": 0.125, "2032E": 0.05, "2033E": 0.05})
    assert out["dgm"] == {y: 25 for y in YEARS} and out["wacc"] == 0.09 and out["tv_mult"] == 10.0
    part = scenarios.expand({"Revenue": {"years": {"2032E": 0.3}}}, BASE, YEARS, names)
    assert part["Revenue"] == {"2031E": 0.10, "2032E": 0.3, "2033E": 0.10}
    assert BASE["Revenue"]["2032E"] == 0.10                 # the user's inputs are never mutated


def test_unknown_name_refused():
    with pytest.raises(ValueError, match="allowed"):
        scenarios.expand({"Units": 0.1}, BASE, YEARS, ["Revenue", "dgm", "wacc", "tv_mult"])


def test_bad_year_refused():
    """A year outside the input years would be silently ignored by model-dcf's math, so it is refused here."""
    with pytest.raises(ValueError, match="2030E"):
        scenarios.expand({"Revenue": {"years": {"2030E": 0.3}}}, BASE, YEARS, ["Revenue", "dgm", "wacc", "tv_mult"])


def _run(*args, check=True):
    return subprocess.run([sys.executable, "-I", EVAL, *args], capture_output=True, text=True, check=check)


@pytest.fixture(scope="module")
def dcf(fixture_model, tmp_path_factory):
    d = str(tmp_path_factory.mktemp("dcf") / "dcf.json")
    _run("context", "--model", fixture_model, "--out", d)
    return d, json.load(open(d))


def test_context_matches_dcf_tab(dcf):
    """The bridge reads the same inputs and value the DCF tab shows; the tab's cells are found by layout, not hardcoded."""
    _, c = dcf
    assert c["value_per_share"] == pytest.approx(67.92, abs=0.05)
    assert "stale" not in c
    assert c["refs"]["vps"].startswith("DCF!$C$") and c["refs"]["price"].startswith("DCF!$C$")
    assert c["names"][-2:] == ["wacc", "tv_mult"] and "dgm" in c["names"]
    assert c["input_years"][-1].startswith(str(int(c["ctx"]["year0"][:4]) + 30))


def test_eval_matches_dcf_tab_for_unchanged_base(dcf, tmp_path):
    d, c = dcf
    t = tmp_path / "try_1.json"
    t.write_text(json.dumps({"round": 1, "final": False, "why": "x", "cases": {
        "base": {"inputs": {}, "story": "s"}, "bull": {"inputs": {"tv_mult": 14}, "story": "s"},
        "bear": {"inputs": {"wacc": 0.10}, "story": "s"}}}))
    out = str(tmp_path / "r.json")
    _run("eval", "--dcf", d, "--try", str(t), "--ntm-eps", "2.5", "--ntm1-eps", "3.0", "--out", out)
    r = json.load(open(out))
    assert r["base"]["value_per_share"] == pytest.approx(c["value_per_share"], abs=1e-9)
    assert r["bull"]["value_per_share"] > r["base"]["value_per_share"] > r["bear"]["value_per_share"]
    assert r["base"]["implied_pe_ntm"] == pytest.approx(r["base"]["value_per_share"] / 2.5)
    assert set(r["implied"]) >= {"price"}


def test_eval_requires_all_three_cases(dcf, tmp_path):
    d, _ = dcf
    t = tmp_path / "try_1.json"
    t.write_text(json.dumps({"round": 1, "cases": {"base": {"inputs": {}}}}))
    p = _run("eval", "--dcf", d, "--try", str(t), "--ntm-eps", "2.5", "--ntm1-eps", "3.0",
             "--out", str(tmp_path / "r.json"), check=False)
    assert p.returncode != 0 and "bull" in p.stderr


def test_typecheck_smoke(fixture_model, dcf, tmp_path):
    """Typing a case's inputs into the DCF tab's yellow cells gives the value eval reported; a wrong value is caught."""
    d, c = dcf
    plan = {"scenarios": {"final": {
        "base": {"value_per_share": c["value_per_share"], "inputs": {}},
        "bull": {"value_per_share": c["value_per_share"] + 5, "inputs": {"wacc": 0.07}},   # wrong on purpose
        "bear": {"value_per_share": c["value_per_share"], "inputs": {}}}}}
    pp = tmp_path / "plan.json"
    pp.write_text(json.dumps(plan))
    p = _run("typecheck", "--after", fixture_model, "--dcf", d, "--plan", str(pp), "--work", str(tmp_path / "w"),
             check=False)
    rep = json.loads(p.stdout)
    assert rep["checked"] == 3 and p.returncode == 1
    assert len(rep["problems"]) == 1 and "bull" in rep["problems"][0]
