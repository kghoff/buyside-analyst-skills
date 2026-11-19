"""Code answers everything numbers can answer before the agent reads a word: the actual against the freeze line by
line (placeholders flagged, not scored), the move in sigmas, the estimates before and now, and the valuation before
and after. The stop messages name the skill to run, because the user fixes the order, not the code.

The fixture has no cached formula values (openpyxl saved it), so values=model reads formulas as None: these tests
assert only what comes from typed cells."""
import json
import os
import subprocess
import sys

import openpyxl
import pytest

import context
import make_fixture as mf

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "context.py")


def _run(model, research, w, **kw):
    return context.run(model, w, "TEST", values=model, research=research, today="2027-02-28", **kw)


@pytest.fixture
def work(tmp_path):
    w = str(tmp_path / "w")
    os.makedirs(w)
    json.dump(mf.YAHOO, open(os.path.join(w, "yahoo_after.json"), "w"))
    return w


@pytest.fixture
def ctx(model, fixture_research, work):
    return _run(model, fixture_research, work)


def _edit(path, fn):
    """A changed copy of the test workbook (openpyxl save is fine here: never a user's model)."""
    wb = openpyxl.load_workbook(path)
    fn(wb)
    wb.save(path)


def test_quarter_and_surprise(ctx):
    """The surprise is signed against the frozen line: revenue came in 4% above, operating income 3% below."""
    assert ctx["quarter"] == "Q4 26" and ctx["quarter_e"] == "Q4 26E"
    rev = next(r for r in ctx["frozen"]["rows"] if r["label"].endswith("| Revenue"))
    assert rev["surprise"] == pytest.approx(0.04, abs=1e-9) and rev["result"] == "beat"
    assert rev["mod_ref"] == "'MOD'!$AP$3" and rev["frozen_ref"] == "$B$109"
    oi = next(r for r in ctx["frozen"]["rows"] if r["label"].endswith("| Operating Income"))
    assert oi["surprise"] == pytest.approx(-0.03, abs=1e-9) and oi["result"] == "miss"


def test_placeholder_is_flagged_not_scored(ctx):
    """A line model-update left as a forecast placeholder holds no actual yet: scoring it would grade the forecast
    against itself."""
    u = next(r for r in ctx["frozen"]["rows"] if r["label"] == mf.PLACEHOLDER_KEY)
    assert u["placeholder"] and u["surprise"] is None and u["result"] is None
    assert not next(r for r in ctx["frozen"]["rows"] if r["label"].endswith("| Revenue"))["placeholder"]


def test_move_and_drift(ctx):
    """The move is read in daily sigmas from the 252 returns before the reaction day (the print itself excluded),
    and the drift fills once T+7 is in Px Data."""
    m = ctx["move"]
    assert m["release_day"] == str(mf.RELEASE_DAY) and m["reaction_day"] == str(mf.REACTION_DAY)
    assert m["day"] == pytest.approx(mf.DAY_MOVE) and m["idio"] == pytest.approx(mf.IDIO)
    assert m["daily_sigma"] < 0.01 and m["sigma_n"] == 252          # the 8% print is not in its own sigma
    assert m["sigmas"] == pytest.approx(mf.DAY_MOVE / m["daily_sigma"])
    assert m["sigma_formula"].startswith("IFERROR(STDEV('Px Data'!$D$")
    assert m["drift"] is not None and ctx["drift_ready"] and "'Px Data'!$B$" in m["drift_formula"]
    assert m["open"] == 55.0 and m["gap"] is None        # the fixture's Yahoo has no previous close


def test_no_drift_before_t_plus_7(model, fixture_research, work):
    """Before seven trading days have passed the drift is None and the rerun question is not asked."""
    def cut(wb):
        px = wb["Px Data"]
        rows = [r for r in range(5, px.max_row + 1) if px.cell(r, 1).value]
        for r in rows[-5:]:
            for c in range(1, 5):
                px.cell(r, c).value = None
    _edit(model, cut)
    c = _run(model, fixture_research, work)
    assert c["move"]["drift"] is None and not c["drift_ready"]


def test_valuation_before_and_after(ctx):
    """Before = the last note dated before the release; after = the Valuation tab; IRR now = the after 3-year
    price over the latest close."""
    v = ctx["valuation"]
    assert v["before"]["values"]["IRR"]["value"] == pytest.approx(0.112)
    assert v["after"]["cells"]["IRR"]["value"] == pytest.approx(0.139)
    assert "IRR" in v["labels"] and not any("rerun /model-valuation" in w for w in ctx["warnings"])
    i = ctx["irr_now"]
    assert i["value"] == pytest.approx((140.0 / i["price"]) ** (1 / 3) - 1)
    assert len(ctx["fade"]) == 7 and ctx["fade"][0]["irr"] == pytest.approx(i["value"])


def test_stale_valuation_tab_warns(model, fixture_research, work):
    """A Valuation tab from before the reaction day is not the after-print valuation."""
    _edit(model, lambda wb: wb["Valuation"].__setitem__("A1", "TEST valuation (model-valuation, 2026-11-17)"))
    c = _run(model, fixture_research, work)
    assert any("rerun /model-valuation" in w for w in c["warnings"])


def test_estimates_before_from_update_snapshot(ctx):
    """'Before' is model-update's pre-print snapshot, so the change is the print's own effect on the year."""
    rev = next(e for e in ctx["estimates"] if e["label"].endswith("| Revenue"))
    assert rev["fy"]["period"] == "2026" and rev["fy1"]["period"] == "2027E"
    assert rev["fy"]["before"] is not None and rev["fy1"]["before"] is not None
    assert rev["fy"]["before_src"]["kind"] == "snapshot" and rev["fy"]["ref"] == "'MOD'!$AQ$3"
    assert rev["fy"]["now"] == pytest.approx(rev["fy"]["before"] + rev["fy"]["delta_q"], rel=1e-9)


def test_estimates_fall_back_to_band_7(model, fixture_research, work):
    """Without the snapshot, this year's 'before' is band 7's frozen FY and next year's is unknown."""
    os.remove(os.path.join(os.path.dirname(model), "_model_work", "update", "Q4 26", "values.json"))
    rev = next(e for e in _run(model, fixture_research, work)["estimates"] if e["label"].endswith("| Revenue"))
    assert rev["fy"]["before_src"]["kind"] == "band 7" and rev["fy1"]["before"] is None


def test_topics_with_and_without_a_forecast_plan(model, fixture_research, work, tmp_path):
    """The Call Notes get one row per forecast driver; no plan means no driver rows and a warning, not a stop."""
    c = _run(model, fixture_research, work)
    assert not any(t.startswith("Driver: ") for t in c["topics"]) and c["topics"][0] == "Guidance (near-term)"
    assert any("forecast plan" in w for w in c["warnings"])
    fp = str(tmp_path / "forecast_plan.json")
    json.dump({"revenue_identity": {"terms": [{"factors": [{"key": mf.PLACEHOLDER_KEY, "name": "Units"}]}]}},
              open(fp, "w"))
    c = _run(model, fixture_research, work, forecast_plan=fp)
    assert "Driver: Units" in c["topics"] and c["topics"].index("Driver: Units") == 2
    assert any(e["kind"] == "driver" and e["label"] == mf.PLACEHOLDER_KEY for e in c["estimates"])


def test_docs_mode_and_house(ctx, model, fixture_research, work):
    """The agent gets relative paths to read; a saved plan for the same quarter makes this a rerun; the in-line
    band is the house 1% until the tab holds the user's own."""
    assert ctx["docs"]["transcript"] == mf.TRANSCRIPT and ctx["docs"]["release"] == mf.RELEASE
    assert ctx["docs"]["preview"] == mf.PREVIEW
    assert ctx["mode"] == "first" and ctx["house"] == {"in_line": 0.01} and ctx["history"] == []
    assert "INCOME STATEMENT | Revenue" in ctx["mod_keys"]
    assert os.path.exists(os.path.join(work, "context.md")) and os.path.exists(os.path.join(work, "context.json"))
    json.dump({"quarter": "Q4 26"}, open(os.path.join(work, "after_plan.json"), "w"))

    def band9(wb):
        ws = wb["Earnings"]
        ws["A131"], ws["A133"], ws["B133"] = "9. ACTUAL VS FROZEN: Q4 26", "In-line band (±, for the beat / miss column)", 0.02
    _edit(model, band9)
    c = _run(model, fixture_research, work)
    assert c["mode"] == "rerun" and c["house"]["in_line"] == 0.02


def test_stop_when_actuals_missing(model, fixture_research, tmp_path):
    def back(wb):
        for c in wb["MOD"][2]:
            if c.value == "Q4 26":
                c.value = "Q4 26E"
    _edit(model, back)
    with pytest.raises(SystemExit, match="/model-update"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_when_band_7_froze_another_quarter(model, fixture_research, tmp_path):
    _edit(model, lambda wb: wb["Earnings"].__setitem__(
        "A107", "7. FROZEN FORECAST: Q3 26E, frozen 2026-08-01 (values: model-earnings-after compares)"))
    with pytest.raises(SystemExit, match="Q3 26E.*Q4 26"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_without_band_7(model, fixture_research, tmp_path):
    _edit(model, lambda wb: wb["Earnings"].__setitem__("A107", "notes"))
    with pytest.raises(SystemExit, match="/model-earnings-before"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_without_the_release_in_px_events(model, fixture_research, tmp_path):
    def drop(wb):
        ev = wb["Px Events"]
        for r in range(1, ev.max_row + 1):
            if ev.cell(r, 1).value == mf.Q:
                for c in range(1, 18):
                    ev.cell(r, c).value = None
    _edit(model, drop)
    with pytest.raises(SystemExit, match="/model-price-history"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_when_px_data_ends_before_the_reaction_day(model, fixture_research, tmp_path):
    def cut(wb):
        px = wb["Px Data"]
        for r in range(5, px.max_row + 1):
            d = px.cell(r, 1).value
            if d is not None and d.date() >= mf.REACTION_DAY:
                for c in range(1, 5):
                    px.cell(r, c).value = None
    _edit(model, cut)
    with pytest.raises(SystemExit, match="/model-price-history"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_without_a_transcript(model, fixture_research, tmp_path):
    import shutil
    root = str(tmp_path / "TEST")
    shutil.copytree(fixture_research, root)
    os.remove(os.path.join(root, mf.TRANSCRIPT))
    with pytest.raises(SystemExit, match="transcript.py ingest"):
        _run(model, root, str(tmp_path / "w"))


def test_quarter_only(model, tmp_path):
    """SKILL.md asks for the quarter and reaction day before the transcript and Yahoo steps: model only, no
    recalculation, no research folder."""
    p = subprocess.run([sys.executable, SCRIPT, "--model", model, "--work", str(tmp_path / "w"), "--ticker", "test",
                        "--quarter-only"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {"quarter": "Q4 26", "quarter_e": "Q4 26E", "reaction_day": str(mf.REACTION_DAY)}
    assert not os.path.exists(str(tmp_path / "w" / "values"))
