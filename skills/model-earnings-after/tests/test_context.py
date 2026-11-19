"""Code answers everything numbers can answer before the agent reads a word: the actual against the freeze line by
line (placeholders flagged, not scored), the move in sigmas, the estimates before and now, and the valuation before
and after. The stop messages name the skill to run, because the user fixes the order, not the code.

The fixture has no cached formula values (openpyxl saved it), so values=model reads formulas as None: these tests
assert only what comes from typed cells."""
import datetime as dt
import json
import os
import shutil
import statistics
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


def test_consensus_from_the_preview_grid(ctx):
    """The after-print note compares the print with what the Street expected before it: band 6 holds the Yahoo mean
    for revenue and EPS (typed, with its source note); the blank margin rows are not consensus."""
    c = ctx["consensus"]
    assert c["where"] == "earnings"
    assert [(r["label"], r["q"]) for r in c["rows"]] == [("Revenue", 140), ("EPS", 0.62)]
    assert c["rows"][0]["q_ref"].startswith("'Earnings'!$C$")
    assert "Yahoo snapshot 2026-11-01" in c["source"]


def test_consensus_tab_block_and_skeleton(model):
    """With band 6 empty, model-consensus's empty skeleton gives no consensus at all (never a 0), and the Consensus
    tab's block is read once the user typed a number there."""
    def clear(wb):
        for row in wb["Earnings"].iter_rows(min_col=3, max_col=5):
            for c in row:
                if c.comment and "Consensus tab mean row" in c.comment.text:
                    c.value = None
    _edit(model, clear)
    assert context.consensus(model, model, "Q4 26") == {"where": None, "rows": [], "source": None}

    def typed(wb):
        ws = wb["Consensus"]
        ws[f"C{next(c.row for c in ws['B'] if c.value == 'EPS')}"] = 0.6
    _edit(model, typed)
    c = context.consensus(model, model, "Q4 26")
    assert c["where"] == "consensus" and [(x["label"], x["q"]) for x in c["rows"]] == [("EPS", 0.6)]


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


def _px(path):
    """Px Data's daily rows straight from the workbook: [(row, date, close, return)], independent of context.py."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = [(r[0].row, r[0].value.date(), r[1].value, r[3].value) for r in wb["Px Data"].iter_rows(min_row=1)
           if isinstance(r[0].value, dt.datetime) and r[1].value is not None]
    wb.close()
    return out


def test_move_and_drift(ctx, model):
    """The move is read in daily sigmas from exactly the 252 returns before the reaction day (the print itself
    excluded: it would inflate its own yardstick); run-up is T-8 to T-1 and drift T to T+7, as in the preview."""
    m = ctx["move"]
    assert m["release_day"] == str(mf.RELEASE_DAY) and m["reaction_day"] == str(mf.REACTION_DAY)
    assert m["day"] == pytest.approx(mf.DAY_MOVE) and m["idio"] == pytest.approx(mf.IDIO)
    px = _px(model)
    i = next(k for k, x in enumerate(px) if x[1] == mf.REACTION_DAY)
    win = px[i - 252:i]
    assert m["daily_sigma"] == pytest.approx(statistics.stdev(x[3] for x in win), rel=1e-12) and m["sigma_n"] == 252
    assert m["sigma_formula"] == f"IFERROR(STDEV('Px Data'!$D${win[0][0]}:$D${win[-1][0]}),NA())"
    assert m["sigmas"] == pytest.approx(mf.DAY_MOVE / m["daily_sigma"])
    ref = lambda k: f"'Px Data'!$B${px[k][0]}"   # noqa: E731
    assert m["run_up_formula"] == f"IFERROR({ref(i - 1)}/{ref(i - 8)}-1,NA())"
    assert m["run_up"] == pytest.approx(px[i - 1][2] / px[i - 8][2] - 1, rel=1e-12)
    assert m["drift_formula"] == f"IFERROR({ref(i + 7)}/{ref(i)}-1,NA())"
    assert m["drift"] == pytest.approx(px[i + 7][2] / px[i][2] - 1, rel=1e-12) and ctx["drift_ready"]
    assert m["drift_day"] == px[i + 7][1].isoformat()
    assert m["open"] == 55.0 and m["gap"] is None        # the fixture's Yahoo has no previous close


def _keep_days_after(model, n):
    """Px Data cut to n trading days after the reaction day."""
    def cut(wb):
        px = wb["Px Data"]
        rows = [r for r in range(1, px.max_row + 1) if isinstance(px.cell(r, 1).value, dt.datetime)]
        k = next(j for j, r in enumerate(rows) if px.cell(r, 1).value.date() == mf.REACTION_DAY)
        for r in rows[k + n + 1:]:
            for c in range(1, 5):
                px.cell(r, c).value = None
    _edit(model, cut)


def test_drift_needs_exactly_t_plus_7(model, fixture_research, work):
    """Seven trading days after the reaction day are enough for the drift; six are not, and once T+7 is due the
    user is told to refresh Px Data rather than left with a silent blank."""
    _keep_days_after(model, 7)
    c = _run(model, fixture_research, work)
    assert c["drift_ready"] and c["move"]["drift"] is not None
    _keep_days_after(model, 6)
    c = _run(model, fixture_research, work)
    assert c["move"]["drift"] is None and not c["drift_ready"] and c["move"]["drift_formula"] is None
    assert any("rerun /model-price-history for the drift" in w for w in c["warnings"])
    c = context.run(model, work, "TEST", values=model, research=fixture_research, today="2027-02-19")
    assert not any("for the drift" in w for w in c["warnings"])          # T+7 (2027-02-22) not due yet


def test_valuation_before_and_after(ctx):
    """Before = the last note dated before the release; after = the Valuation tab; IRR now = the after 3-year
    price over the latest close."""
    v = ctx["valuation"]
    assert v["before"]["values"]["IRR"]["value"] == pytest.approx(0.112)
    assert v["after"]["cells"]["IRR"]["value"] == pytest.approx(0.139)
    assert v["multiples"] == ["P/E"] and "IRR" in v["labels"]
    i = ctx["irr_now"]
    assert i["value"] == pytest.approx((140.0 / i["price"]) ** (1 / 3) - 1)
    assert len(ctx["fade"]) == 7 and ctx["fade"][0]["irr"] == pytest.approx(i["value"])


def test_valuation_fresh_only_with_a_note_since_the_print(ctx, model, fixture_research, work, tmp_path):
    """model-valuation's tab title has no date, but it writes a dated note every run: no note since the reaction
    day means the tab may still hold the pre-print valuation."""
    assert any("may predate the print" in w and "rerun /model-valuation" in w for w in ctx["warnings"])
    root = str(tmp_path / "TEST")
    shutil.copytree(fixture_research, root)
    open(os.path.join(root, "Valuation", "2027-02-24 TEST Valuation Note.md"), "w").write("x")
    c = _run(model, root, work)
    assert c["valuation"]["after"]["fresh_note"] == "Valuation/2027-02-24 TEST Valuation Note.md"
    assert not any("may predate the print" in w for w in c["warnings"])
    assert c["valuation"]["before"]["path"] == mf.VALNOTE        # the after-print note is never the 'before'


def test_multiples_union_note_then_tab(model, fixture_research, work):
    """A multiple the after tab adds is compared too (before '?'), after the note's own, in that order."""
    def add(wb):
        v = wb["Valuation"]
        v.cell(v.max_row + 1, 1, "EV/EBITDA: reward price")
        v.cell(v.max_row, 2, 120.0)
    _edit(model, add)
    v = _run(model, fixture_research, work)["valuation"]
    assert v["multiples"] == ["P/E", "EV/EBITDA"] and "EV/EBITDA: reward price" in v["labels"]


def test_empty_values_fail_loud(model, fixture_research, work):
    """A values copy that was never recalculated reads formulas as empty: say so rather than show silent '?'s."""
    def blank(wb):
        wb["MOD"]["AP3"] = None
        for r in range(1, wb["Px Events"].max_row + 1):
            if wb["Px Events"].cell(r, 1).value == mf.Q:
                wb["Px Events"].cell(r, 17).value = None
        for r in range(1, wb["Valuation"].max_row + 1):
            if wb["Valuation"].cell(r, 1).value == "IRR":
                wb["Valuation"].cell(r, 2).value = None
    _edit(model, blank)
    ws = _run(model, fixture_research, work)["warnings"]
    assert any("AP3" in w and "Revenue" in w and "recalculated" in w for w in ws)
    assert any("idio" in w and "recalculated" in w for w in ws)
    assert any("Valuation tab has no value for IRR" in w for w in ws)
    assert not any("Units" in w and "no value" in w for w in ws)     # the placeholder is not an empty actual


def test_yahoo_for_another_day_is_dropped(model, fixture_research, work):
    """Bars for the wrong day would put another day's gap on the print."""
    json.dump({**mf.YAHOO, "reaction_day": "2027-02-12", "prev_close": 50.0, "close": 56.0},
              open(os.path.join(work, "yahoo_after.json"), "w"))
    c = _run(model, fixture_research, work)
    assert c["move"]["gap"] is None and c["move"]["open_to_close"] is None
    assert any("not the reaction day" in w for w in c["warnings"])
    json.dump({**mf.YAHOO, "prev_close": 50.0, "close": 56.0}, open(os.path.join(work, "yahoo_after.json"), "w"))
    m = _run(model, fixture_research, work)["move"]
    assert m["gap"] == pytest.approx(0.1) and m["open_to_close"] == pytest.approx(56 / 55 - 1)


def test_stale_px_data_warns(model, fixture_research, work):
    """The IRR now uses Px Data's last close (the tab needs a cell): an old one is flagged, not passed as today's."""
    c = context.run(model, work, "TEST", values=model, research=fixture_research, today="2027-03-15")
    assert any("for today's price" in w for w in c["warnings"])
    assert not any("for today's price" in w for w in _run(model, fixture_research, work)["warnings"])


def test_modmap_reads_the_values_copy(model, fixture_research, work, monkeypatch):
    """MOD's values and its row map must come from the same (recalculated) file."""
    seen = []
    real = context.ModMap
    monkeypatch.setattr(context, "ModMap", lambda p, *a: seen.append(p) or real(p, *a))
    vals = os.path.join(work, "values.xlsx")
    shutil.copy(model, vals)
    c = context.run(model, work, "TEST", values=vals, research=fixture_research, today="2027-02-28")
    assert vals in seen and c["mod_periods"]["2026"] == "AQ" and c["mod_periods"]["Q4 26"] == "AP"


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


def test_earnings_values_give_build_its_same_tab_numbers(ctx):
    """Bands 9-15 compare with band 1's expected move, band 2's up / down moves and band 5's implied move: build.py
    needs those cells' values to know what its formulas should recalculate to. Typed cells read as typed; formulas
    in a copy that was never recalculated read None (unknown, so build.py leaves them unchecked), never 0."""
    ev = ctx["earnings_values"]
    assert set(ev) == set(ctx["earnings_refs"])
    assert ev["expected_move"] == 0.05 and ev["price"] == 51
    assert ev["up"] is None and ev["down"] is None          # formulas: no cached value in the fixture
    assert ev["implied"] == "n/a"                           # band 5 wrote text: no implied move


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
    _keep_days_after(model, -1)
    with pytest.raises(SystemExit, match="ends .*before the reaction day.*/model-price-history"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_when_px_data_has_no_row_for_the_reaction_day(model, fixture_research, tmp_path):
    def weekend(wb):
        ev = wb["Px Events"]
        for r in range(1, ev.max_row + 1):
            if ev.cell(r, 1).value == mf.Q:
                ev.cell(r, 13).value = dt.datetime(2027, 2, 13)          # a Saturday: no trading row
    _edit(model, weekend)
    with pytest.raises(SystemExit, match="no row for the reaction day.*/model-price-history"):
        _run(model, fixture_research, str(tmp_path / "w"))


def test_stop_without_a_transcript(model, fixture_research, tmp_path):
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
