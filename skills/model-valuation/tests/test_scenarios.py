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


@pytest.mark.parametrize("fade, err", [
    ({"from": 0.2, "to": 0.05, "over": 0}, "over"), ({"from": 0.2, "to": 0.05, "over": 2.5}, "over"),
    ({"from": 0.2, "to": 0.05, "over": "3"}, "over"), ({"from": "0.2", "to": 0.05, "over": 2}, "from"),
    ({"from": 0.2, "to": None, "over": 2}, "to")])
def test_bad_fade_refused(fade, err):
    """A bad fade is the skill's ValueError naming the input (the agent reads it and fixes its try), not a crash."""
    with pytest.raises(ValueError, match=f"Revenue.*{err}"):
        scenarios.expand({"Revenue": fade}, BASE, YEARS, ["Revenue", "dgm", "wacc", "tv_mult"])


def _run(*args, check=True):
    return subprocess.run([sys.executable, "-I", EVAL, *args], capture_output=True, text=True, check=check)


@pytest.fixture(scope="module")
def dcf(fixture_model, tmp_path_factory):
    d = str(tmp_path_factory.mktemp("dcf") / "dcf.json")
    w = tmp_path_factory.mktemp("work")
    _run("context", "--model", fixture_model, "--out", d, "--work", str(w))
    assert not (w / "dcf_stale").exists()           # a stale check's recalc is cleaned out of the work dir
    return d, json.load(open(d))


def test_context_matches_dcf_tab(dcf):
    """The bridge reads the same inputs and value the DCF tab shows; the tab's cells are found by layout, not hardcoded."""
    _, c = dcf
    assert c["value_per_share"] == pytest.approx(67.92, abs=0.05)
    assert "stale" not in c
    assert c["refs"]["vps"].startswith("DCF!$C$") and c["refs"]["price"].startswith("DCF!$C$")
    assert c["names"][-2:] == ["wacc", "tv_mult"] and "dgm" in c["names"]
    assert c["input_years"][-1].startswith(str(int(c["ctx"]["year0"][:4]) + 30))
    assert c["fade_years"] == 10                    # model-dcf's own fade length, passed on (not hardcoded here)


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


def test_typecheck_types_every_input(fixture_model, dcf, tmp_path):
    """Each case changes WACC, the terminal multiple and a driver, with the value eval gives for exactly those inputs:
    the tab only matches if typecheck really typed all three, so a typecheck that skips one is caught."""
    d, c = dcf
    drv = c["names"][0]
    y0 = c["input_years"][0]
    cases = {"base": {"inputs": {}},
             "bull": {"inputs": {"wacc": c["inputs"]["wacc"] - 0.01, "tv_mult": c["inputs"]["tv_mult"] + 3,
                                 drv: {"years": {y0: c["inputs"][drv][y0] + 0.05}}}},
             "bear": {"inputs": {"wacc": c["inputs"]["wacc"] + 0.01, "tv_mult": c["inputs"]["tv_mult"] - 2,
                                 drv: {"from": c["inputs"][drv][y0] - 0.03, "to": 0.0, "over": 5}}}}
    t = tmp_path / "try.json"
    t.write_text(json.dumps({"cases": cases}))
    r = str(tmp_path / "r.json")
    _run("eval", "--dcf", d, "--try", str(t), "--ntm-eps", "2.5", "--ntm1-eps", "3.0", "--out", r)
    got = json.load(open(r))
    for n in ("bull", "bear"):          # each change moves the value: the check below means something
        assert abs(got[n]["value_per_share"] - c["value_per_share"]) > 1
    plan = {"scenarios": {"final": {n: {"value_per_share": got[n]["value_per_share"], "inputs": cases[n]["inputs"]}
                                    for n in scenarios.CASES}}}
    pp = tmp_path / "plan.json"
    pp.write_text(json.dumps(plan))
    p = _run("typecheck", "--after", fixture_model, "--dcf", d, "--plan", str(pp), "--work", str(tmp_path / "w"),
             check=False)
    rep = json.loads(p.stdout)
    assert rep == {"checked": 3, "problems": []} and p.returncode == 0


def test_typecheck_catches_wrong_value(fixture_model, dcf, tmp_path):
    """A plan value the tab doesn't reproduce is flagged."""
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
