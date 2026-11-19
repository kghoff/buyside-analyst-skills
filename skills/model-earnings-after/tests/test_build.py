"""The build appends bands 9-15 and the Call Notes tab and touches nothing else: bands 1-8 are the preview the wrap
is judged against, so a changed byte there is a bug. A rerun keeps the user's own yellow values. Every formula's
expected value is code's own math (aftermath), so verify.py can prove the tab and the note agree. No LibreOffice
here (test_recalc does the one recalculation)."""
import json
import os
import re
import shutil
import zipfile

import openpyxl
import pytest

import aftermath as am
import build
import earnings_tab as et
import make_fixture as mf
import xlsx_edit_helper
from xlsx import Package

PLAN = os.path.join(os.path.dirname(__file__), "fixtures", "plan_example.json")


def _ctx(model, w, research, today="2027-02-28"):
    import context
    return context.run(model, w, "TEST", values=model, research=research, today=today)


@pytest.fixture
def work(model, fixture_research, tmp_path):
    w = str(tmp_path / "w")
    os.makedirs(w)
    json.dump(mf.YAHOO, open(os.path.join(w, "yahoo_after.json"), "w"))
    _ctx(model, w, fixture_research)
    shutil.copy(PLAN, os.path.join(w, "after_plan.json"))
    return w


@pytest.fixture
def built(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    res = build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    return out, res, lay


def _rows_above(path, start):
    p = et.part(Package(path))
    x = zipfile.ZipFile(path).read(p).decode()
    return [m.group(0) for m in re.finditer(r'<row r="(\d+)".*?</row>', x, re.S) if int(m.group(1)) < start]


def _row(ws, label):
    """The row of a column-A label in bands 9-15 (the last one: band 7 repeats the MOD line labels above)."""
    return [c.row for c in ws["A"] if c.value == label][-1]


def _promote(work):
    for n in ("after_inputs_written", "call_notes_written"):
        os.replace(os.path.join(work, f"{n}.next.json"), os.path.join(work, f"{n}.json"))


def test_bands_1_to_8_and_other_parts_untouched(model, built):
    """The preview is the record the wrap is judged against: not one byte of bands 1-8 or any other tab changes."""
    out, res, _ = built
    start = et.read(model)["start"]
    assert res["changed_parts"] == []
    assert _rows_above(out, start) == _rows_above(model, start)


def test_every_band_header_and_unique_labels(built):
    """Seven bands, in order, and every column-A label once: reruns and verify find cells by label."""
    out, _, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    start = lay["start"]
    heads = [c.value for c in ws["A"] if c.row >= start and isinstance(c.value, str) and re.match(r"^\d+\. ", c.value)]
    assert [int(h.split(".")[0]) for h in heads] == list(range(9, 16))
    labels = [c.value for c in ws["A"] if c.row >= start and c.value]
    assert len(labels) == len(set(labels))
    assert ws[f"A{start}"].value.startswith("TEST after the print: Q4 26")


def test_colours(built):
    """House colours tell the user what is theirs: green links, blue typed, yellow inputs, black formulas."""
    out, _, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    k = lay["kinds"]
    link = next(r for r, v in k.items() if v == "link")
    typed = next(r for r, v in k.items() if v == "typed")
    form = next(r for r, v in k.items() if v == "formula")
    assert ws[link].font.color.rgb == "FF008000"
    assert ws[typed].font.color.rgb == "FF0000FF"
    assert ws[form].font.color.rgb == "FF000000"
    react = lay["refs"]["React: the call"].replace("$", "")
    assert ws[react].fill.fgColor.rgb.endswith("FFFF00")          # yellow: the user's to change
    assert ws[react].value == "hold"


def test_placeholder_row_shows_awaiting_and_no_result(built):
    """A line model-update filled with an estimate is not a beat or a miss: scoring it would score our own guess."""
    out, res, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    y = _row(ws, "KEY OPERATING METRICS | Units")
    assert res["placeholders"] == ["KEY OPERATING METRICS | Units"]
    assert ws[f"F{y}"].value == build.PLACEHOLDER and ws[f"F{y}"].font.i
    assert ws[f"D{y}"].value is None and ws[f"E{y}"].value is None
    assert f"F{y}" not in lay["expected"] and f"E{y}" not in lay["expected"]


def test_in_line_band_drives_the_result_column(built):
    """The user changes the in-line band in one cell and every result follows: column F reads that cell."""
    out, _, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    band = lay["refs"][build.IN_LINE_LABEL]
    y = _row(ws, "INCOME STATEMENT | Revenue")
    assert band in ws[f"F{y}"].value and f"E{y}" in ws[f"F{y}"].value
    assert ws[band.replace("$", "")].value == 0.01


def test_expected_values_are_the_chapter_math(built, work):
    """verify.py compares the recalculated tab with these numbers, so they must be code's math, hand-checked here:
    revenue +4% (beat), operating income -3% (miss), the move in sigmas and the IRR at the latest close."""
    out, _, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    ex = lay["expected"]
    ctx = json.load(open(os.path.join(work, "context.json")))
    rv, oi = _row(ws, "INCOME STATEMENT | Revenue"), _row(ws, "INCOME STATEMENT | Operating Income")
    assert ex[f"E{rv}"] == pytest.approx(0.04) and ex[f"F{rv}"] == "beat"
    assert ex[f"E{oi}"] == pytest.approx(-0.03) and ex[f"F{oi}"] == "miss"
    sg = _row(ws, "Move in daily sigmas")
    assert ex[f"B{sg}"] == pytest.approx(0.08 / ctx["move"]["daily_sigma"])
    close = ctx["latest_close"]["value"]
    ir = _row(ws, "IRR at the latest close on the after horizon price (section 13.7)")
    assert ex[f"B{ir}"] == pytest.approx((140 / close) ** (1 / 3) - 1)
    mm = _row(ws, "Day move minus expected (|day move| - expected)")
    assert ex[f"B{mm}"] == pytest.approx(0.08 - 0.05)       # band 1's expected move is 5%
    tg = _row(ws, "Target change minus the day's move (positive = the stock under-reacted; section 13.6)")
    assert ex[f"B{tg}"] == pytest.approx((116 / 106.66 - 1) - 0.08)
    f30 = _row(ws, "Fade: price -30%")
    assert ex[f"D{f30}"] == pytest.approx(am.irr(close * 0.7, 140))


def test_unknown_preview_values_are_written_but_not_checked(built):
    """Band 2's up / down moves have no value in an un-recalculated copy: the formula goes in, but verify must not
    expect a number nobody computed, and the user hears about it."""
    out, res, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    up = _row(ws, "Preview's upside move (band 2)")
    assert ws[f"B{up}"].value.startswith("=$B$") and f"B{up}" not in lay["expected"]
    assert "Preview's upside move (band 2)" in res["unchecked"]
    assert any("Not checked by verify" in x for x in res["warnings"])
    imp = _row(ws, "Options-implied move (preview, band 5)")
    assert ws[f"B{imp}"].value == "?"                      # the preview wrote text there: no implied move


def test_long_term_pace_is_formulas_over_mod(built, model, work):
    """The pace to the long-term target is live: formulas on MOD's fiscal-year cells, with code's math expected."""
    out, _, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    y = _row(ws, "Long-term target: latest (2026, MOD)")
    assert "'MOD'!$AQ$5/'MOD'!$AQ$3" in ws[f"B{y}"].value
    m = openpyxl.load_workbook(model, data_only=True)["MOD"]
    c23 = json.load(open(os.path.join(work, "context.json")))["mod_periods"]["2023"]
    v0, v3 = m["AQ5"].value / m["AQ3"].value, m[f"{c23}5"].value / m[f"{c23}3"].value
    pace = am.lt_pace(v0, 2026, am.trend({2026: v0, 2023: v3}, 2026), 0.20, 2028)
    assert lay["expected"][f"B{_row(ws, 'Long-term target: status')}"] == pace["status"]
    assert lay["expected"][f"B{_row(ws, 'Long-term target: needed a year')}"] == pytest.approx((0.20 - v0) / 2)


def test_band_13_shows_a_question_mark_for_an_unknown_before(model, work, tmp_path):
    """An n/a reward / risk in the pre-print note is not zero: the before cell says '?' and so does the change."""
    cp = os.path.join(work, "context.json")
    ctx = json.load(open(cp))
    ctx["valuation"]["before"]["values"]["Blended reward / risk"]["value"] = None
    json.dump(ctx, open(cp, "w"))
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Earnings"]
    y = _row(ws, "Blended reward / risk")
    assert ws[f"B{y}"].value == "?" and ws[f"B{y}"].font.i and ws[f"D{y}"].value == "?"
    assert ws[f"C{y}"].value.startswith("='Valuation'!")


def _edit_ctx(work, fn):
    cp = os.path.join(work, "context.json")
    ctx = json.load(open(cp))
    fn(ctx)
    json.dump(ctx, open(cp, "w"))


def _plan(work, fn):
    p = json.load(open(PLAN))
    fn(p)
    json.dump(p, open(os.path.join(work, "after_plan.json"), "w"))
    return p


def test_played_out_waits_for_the_drift(model, work, tmp_path):
    """Before T+7 closes there is no drift to judge: the row says it is asked on the T+7 rerun, and is no input."""
    _edit_ctx(work, lambda c: c.update(drift_ready=False))
    out = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Earnings"]
    assert ws[f"B{_row(ws, build.PLAYED)}"].value == build.T7_ASK
    assert build.PLAYED not in json.load(open(os.path.join(work, "layout.json")))["inputs"]


def test_played_out_on_a_first_run_after_t7(built):
    """A first run made after T+7 has the drift too, so it answers played-out instead of waiting for a rerun."""
    out, _, lay = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    ref = lay["refs"][build.PLAYED].replace("$", "")
    assert ws[ref].value == "yes" and ws[ref].fill.fgColor.rgb.endswith("FFFF00")


def test_t7_rerun_lands_the_agents_answer(model, work, tmp_path, fixture_research):
    """The real flow: first run before the drift (the row holds our 'asked on the T+7 rerun' text), the copy
    replaces the model, then the T+7 rerun. Our own placeholder text is not the user's edit, so the agent's answer
    lands and no cell is reported as the user's. The agent may also change its own guidance call on the rerun."""
    _edit_ctx(work, lambda c: c.update(drift_ready=False))
    _plan(work, lambda p: p.update(played_out=None))
    out1 = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out1)
    _promote(work)
    shutil.copy(out1, model)                                   # the SKILL copies the checked build over the model
    ctx = _ctx(model, work, fixture_research)
    assert ctx["mode"] == "rerun" and ctx["drift_ready"]

    def t7(p):
        p["played_out"] = {"value": "partly", "reason": "The stock held half of the move through the seventh day."}
        p["guidance"][0]["change"] = "raise"
    plan = _plan(work, t7)
    res = build.build(model, work, "TEST", str(tmp_path / "o2.xlsx"))
    assert res["users_kept"] == []
    lay = json.load(open(os.path.join(work, "layout.json")))
    ws = openpyxl.load_workbook(str(tmp_path / "o2.xlsx"))["Earnings"]
    assert ws[lay["refs"][build.PLAYED].replace("$", "")].value == "partly"
    assert ws[lay["refs"][build.guidance_labels(plan)[0]].replace("$", "")].value == "raise"


def test_a_users_guidance_call_in_column_e_is_kept(model, work, tmp_path):
    """Guidance's yellow cell is in column E, not B: a rerun must read it there and keep the user's edit."""
    out1 = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out1)
    _promote(work)
    lab = "Guidance: 2027 revenue"
    ref = json.load(open(os.path.join(work, "layout.json")))["refs"][lab].replace("$", "")
    assert ref.startswith("E")
    xlsx_edit_helper.set_text(out1, "Earnings", ref, "raise")
    res = build.build(out1, work, "TEST", str(tmp_path / "o2.xlsx"))
    assert res["users_kept"] == [lab]
    assert openpyxl.load_workbook(str(tmp_path / "o2.xlsx"))["Earnings"][ref].value == "raise"


def test_lt_target_below_the_latest_flips_the_status(model, work, tmp_path):
    """A target below today's value (a leverage or cost ratio coming down) is on pace when the run rate falls to
    it, not when it rises past it: the status formula and code's expected value both flip."""
    _plan(work, lambda p: p["lt_target"].update(target=0.10, anchor_value=0.10))
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Earnings"]
    lay = json.load(open(os.path.join(work, "layout.json")))
    v0 = lay["expected"][f"B{_row(ws, 'Long-term target: latest (2026, MOD)')}"]
    slope = lay["expected"][f"B{_row(ws, 'Long-term target: trend a year (2023 to 2026)')}"]
    assert 0.10 < v0
    pace = am.lt_pace(v0, 2026, slope, 0.10, 2028)
    st = _row(ws, "Long-term target: status")
    assert lay["expected"][f"B{st}"] == pace["status"]
    assert pace["status"] == ("on pace" if v0 + 2 * slope <= 0.10 else "behind pace")
    assert "IF($B$" in ws[f"B{st}"].value and "<=" in ws[f"B{st}"].value


def test_an_open_year_labels_the_latest_and_warns(model, work, tmp_path):
    """After a Q1-Q3 print the fiscal year still holds forecast quarters: the label says so and the user hears it
    as a judgment call."""
    _edit_ctx(work, lambda c: c.update(fy="2026E"))
    res = build.build(model, work, "TEST", str(tmp_path / "o.xlsx"))
    ws = openpyxl.load_workbook(str(tmp_path / "o.xlsx"))["Earnings"]
    _row(ws, "Long-term target: latest (FY 2026E, MOD: includes forecast quarters until the year closes)")
    assert any(w.startswith("Judgment call: the long-term pace starts from FY 2026E") for w in res["warnings"])


def test_estimate_before_from_band_7_is_a_same_tab_formula(model, work, tmp_path):
    """With no model-update snapshot, this year's 'before' is band 7's frozen value: a live formula onto it, not a
    second typed copy that could drift from the record."""
    def fall_back(c):
        e = c["estimates"][0]["fy"]
        e["before_src"] = {"kind": "band 7", "ref": "$C$109"}
    _edit_ctx(work, fall_back)
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Earnings"]
    lay = json.load(open(os.path.join(work, "layout.json")))
    y = _row(ws, "Estimate: Revenue")
    assert ws[f"B{y}"].value == "=IF(ISNUMBER($C$109),$C$109,NA())"
    assert lay["kinds"][f"B{y}"] == "formula" and ws[f"B{y}"].font.color.rgb == "FF000000"
    assert lay["expected"][f"B{y}"] == pytest.approx(ws["C109"].value)


def test_a_shrinking_cost_reads_as_a_beat(model, work, tmp_path):
    """Costs are stored negative: a cost that comes in smaller than frozen is good news, so its surprise is
    positive and its result a beat (synthetic band 9 row: the fixture has no cost line)."""
    def cost(c):
        c["frozen"]["rows"].append({**c["frozen"]["rows"][0], "label": "INCOME STATEMENT | SG&A", "frozen": -50.0,
                                    "actual": -48.0, "placeholder": False})
    _edit_ctx(work, cost)
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Earnings"]
    lay = json.load(open(os.path.join(work, "layout.json")))
    y = _row(ws, "INCOME STATEMENT | SG&A")
    assert ws[f"E{y}"].value == f"=IFERROR((C{y}-B{y})/ABS(B{y}),NA())"
    assert lay["expected"][f"E{y}"] == pytest.approx(0.04) and lay["expected"][f"F{y}"] == "beat"


def test_an_empty_plan_builds(model, work, tmp_path):
    """A quiet call: no guidance, no long-term target, no catalysts or controversies. The bands still build."""
    _plan(work, lambda p: p.update(guidance=[], lt_target=None, catalysts=[], controversies=[]))
    res = build.build(model, work, "TEST", str(tmp_path / "o.xlsx"))
    assert res["changed_parts"] == []
    ws = openpyxl.load_workbook(str(tmp_path / "o.xlsx"))["Earnings"]
    _row(ws, "No guidance items in the plan")
    assert not [c for c in ws["A"] if str(c.value).startswith(("Long-term target", "Catalyst", "Controversy"))]


def test_irr_years_change_is_a_difference(built):
    """Years are compared as years (3 -> 3 is 0), like the IRR itself, not as a percent change."""
    out, _, _ = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    y = _row(ws, "IRR: years")
    assert ws[f"D{y}"].value == f"=IFERROR(C{y}-B{y},NA())"


def test_rerun_keeps_the_users_value(model, work, tmp_path):
    """A yellow cell the user changed in Excel survives the rerun; the rest of the tab is rewritten."""
    out1 = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out1)
    _promote(work)
    lay = json.load(open(os.path.join(work, "layout.json")))
    ref = lay["refs"]["React: the call"].replace("$", "")
    xlsx_edit_helper.set_text(out1, "Earnings", ref, "trim")
    out2 = str(tmp_path / "o2.xlsx")
    res = build.build(out1, work, "TEST", out2)
    assert res["users_kept"] == ["React: the call"]
    assert openpyxl.load_workbook(out2, read_only=True)["Earnings"][ref].value == "trim"
    assert res["changed_parts"] == []
    assert _rows_above(out2, lay["start"]) == _rows_above(model, lay["start"])   # no title row left behind


def test_rebuild_restores_the_users_recorded_values(model, work, tmp_path):
    """A /model-earnings-before rerun clears bands 9-15; --rebuild puts back what the record says was the user's."""
    out1 = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out1)
    rec = json.load(open(os.path.join(work, "after_inputs_written.next.json")))
    rec["React: the call"] = {"value": "trim", "user": True}
    json.dump(rec, open(os.path.join(work, "after_inputs_written.json"), "w"))
    out2 = str(tmp_path / "o2.xlsx")
    res = build.build(model, work, "TEST", out2, rebuild=True)    # the model has no band 9
    lay = json.load(open(os.path.join(work, "layout.json")))
    assert res["users_kept"] == ["React: the call"]
    assert openpyxl.load_workbook(out2)["Earnings"][lay["refs"]["React: the call"].replace("$", "")].value == "trim"
    res = build.build(model, work, "TEST", str(tmp_path / "o3.xlsx"))    # without --rebuild: the agent's value
    assert res["users_kept"] == []
    assert any("rerun with --rebuild to restore them" in x for x in res["warnings"])


def test_call_notes_written_after_earnings(built, work):
    """The Call Notes tab sits right after Earnings with this quarter at B, and its record is written for the rerun."""
    out, _, _ = built
    names = openpyxl.load_workbook(out, read_only=True).sheetnames
    assert names.index("Call Notes") == names.index("Earnings") + 1
    ws = openpyxl.load_workbook(out)["Call Notes"]
    assert ws["B4"].value == "Q4 26" and ws["B5"].value == "2027-02-10"
    rec = json.load(open(os.path.join(work, "call_notes_written.next.json")))
    assert rec["Q4 26"]["Tone"] == "Most confident in two years."


def test_out_must_be_a_copy(model, work):
    """The build never writes the user's model in place: the SKILL copies over it only after verify."""
    with pytest.raises(SystemExit):
        build.build(model, work, "TEST", model)
