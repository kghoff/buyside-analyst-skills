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


def test_played_out_is_asked_only_on_the_t7_rerun(model, work, tmp_path, fixture_research):
    """The first run cannot judge how the react call played out; the T+7 rerun asks and the answer is the user's."""
    out = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Earnings"]
    assert ws[f"B{_row(ws, build.PLAYED)}"].value == build.T7_ASK
    ctx = _ctx(model, work, fixture_research)                 # after_plan.json exists: a rerun
    assert ctx["mode"] == "rerun" and ctx["drift_ready"]
    plan = json.load(open(PLAN))
    plan["played_out"] = {"value": "partly", "reason": "The stock held half of the move through the seventh day."}
    json.dump(plan, open(os.path.join(work, "after_plan.json"), "w"))
    out2 = str(tmp_path / "o2.xlsx")
    build.build(model, work, "TEST", out2)
    ws = openpyxl.load_workbook(out2)["Earnings"]
    ref = json.load(open(os.path.join(work, "layout.json")))["refs"][build.PLAYED].replace("$", "")
    assert ws[ref].value == "partly" and ws[ref].fill.fgColor.rgb.endswith("FFFF00")


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
