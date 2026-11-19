"""build_deck.py: the long and core decks from the plan, the template and the recalculated values copy.
Fast (no LibreOffice): the decks are read back with python-pptx."""
import copy
import json
import pathlib
import subprocess
import sys

import openpyxl
import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from conftest import FIX

SK = pathlib.Path(__file__).resolve().parents[1]
BASE = json.loads((FIX / "plan_example.json").read_text())


def run(tmp, values, plan=BASE, *extra):
    f = tmp / "p.json"
    f.write_text(json.dumps(plan))
    r = subprocess.run([sys.executable, str(SK / "scripts" / "build_deck.py"), "--plan", str(f),
                        "--template", str(SK / "assets" / "pitch_template.pptx"), "--values", str(values),
                        "--research", str(FIX / "research"), "--tabs", str(FIX / "tabs"),
                        "--out-long", str(tmp / "long.pptx"), "--out-core", str(tmp / "core.pptx"), *extra],
                       check=True, capture_output=True, text=True)
    return Presentation(tmp / "long.pptx"), Presentation(tmp / "core.pptx"), r.stdout


def build(tmp, model_values, plan=BASE, *extra):
    long, core, _ = run(tmp, model_values, plan, *extra)
    return long, core


def of_type(prs, plan, t):
    return list(prs.slides)[[s["type"] for s in plan["slides"]].index(t)]


def tables(slide):
    return [sh.table for sh in slide.shapes if sh.has_table]


def cells(slide):
    return [c.text for t in tables(slide) for row in t.rows for c in row.cells]


def charts(slide):
    return [sh.chart for sh in slide.shapes if sh.has_chart]


def face_text(slide):
    out = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
    return "\n".join(out + cells(slide))


def with_pictures():
    """The example plan with a tab picture on every text_chart slide (the base plan has none: those fall back)."""
    p = copy.deepcopy(BASE)
    for s in p["slides"]:
        if s["type"] == "text_chart":
            s["image"] = {"png": "Filings_Charts_r1c1.png"}
    return p


@pytest.fixture(scope="module")
def decks(tmp_path_factory, model_values):
    """One build of the example plan (with pictures and an UNVERIFIED list), shared by the read-only tests."""
    tmp = tmp_path_factory.mktemp("deck")
    unv = tmp / "unverified.json"
    unv.write_text(json.dumps([{"key": "eps_27_street", "rule": "A1", "problem": "eps_27_street 3.05 is not SUM!K12"},
                               {"quote": "q1", "rule": "A4", "problem": "q1 is not on line 214"},
                               {"key": "buy_price", "rule": "A3", "problem": "buy_price calc is off"}]))
    long, core, out = run(tmp, model_values, with_pictures(), "--unverified", str(unv))
    return long, core, out


def test_counts_and_core_subset(tmp_path, model_values):
    long, core = build(tmp_path, model_values)
    assert len(long.slides) == len(BASE["slides"]) and len(core.slides) == 10
    t = lambda s: s.shapes.title.text if s.shapes.title else ""  # noqa: E731
    assert [t(s) for s in core.slides] == [t(s) for s in list(long.slides)[:10]]


def test_notes_on_every_slide_and_no_raw_placeholders(tmp_path, model_values):
    long, _ = build(tmp_path, model_values)
    for s in long.slides:
        assert s.has_notes_slide and s.notes_slide.notes_text_frame.text.strip()
        for sh in s.shapes:
            if sh.has_text_frame:
                assert "{" not in sh.text_frame.text


def test_each_slide_uses_the_layout_named_after_its_type(decks):
    # the user may restyle the template; the builder finds layouts by name, so the name must carry the type
    long, _, _ = decks
    assert [s.slide_layout.name for s in long.slides] == [s["type"] for s in BASE["slides"]]


def test_no_empty_leftover_placeholders(decks):
    # an empty placeholder shows "Click to add text" in PowerPoint: in front of a PM that looks unfinished
    long, core, _ = decks
    for prs in (long, core):
        for i, s in enumerate(prs.slides, 1):
            for ph in s.placeholders:
                assert ph.has_text_frame and ph.text_frame.text.strip(), f"slide {i}: empty placeholder idx " \
                                                                         f"{ph.placeholder_format.idx}"


def test_core_slides_draw_native_charts_and_tables(decks):
    # native objects stay editable in PowerPoint; a picture of a chart would not
    long, _, _ = decks
    assert charts(of_type(long, BASE, "setup")) and charts(of_type(long, BASE, "valuation"))
    rr = of_type(long, BASE, "risk_reward")
    assert len(tables(rr)) == 2 and charts(rr)          # cases table and ladder table, ladder chart
    names = [s.name for s in charts(of_type(long, BASE, "valuation"))[0].plots[0].series]
    assert any("median" in n for n in names) and "S&P 500 P/E" in names


def test_summary_table_holds_sum_values(decks):
    long, _, _ = decks
    got = cells(of_type(long, BASE, "summary"))
    assert "$72.40" in got                               # SUM's price (cap table)
    assert "3.30" in got and "3.05" in got and "+8.2%" in got   # our EPS, Street EPS, Expected Delta (grid)


def test_unverified_only_in_notes_of_slides_using_it(decks):
    # an unproved number must reach the presenter, but never the slide face
    long, _, _ = decks
    for s, plan_s in zip(long.slides, BASE["slides"]):
        notes = s.notes_slide.notes_text_frame.text
        uses_key = "{eps_27_street}" in json.dumps(plan_s)
        assert ("UNVERIFIED: eps_27_street" in notes) == uses_key
        assert ("UNVERIFIED: q1" in notes) == ("q1" in plan_s.get("quotes", []))
        assert "UNVERIFIED" not in face_text(s)
    assert any("UNVERIFIED" in s.notes_slide.notes_text_frame.text for s in long.slides)


def test_summary_notes_flag_plan_numbers_shown_in_place_of_sum(decks):
    # SUM's buy price is empty in the fixture, so the cap table shows the plan's buy_price: its UNVERIFIED line
    # belongs on the summary slide even though the summary's own text never names {buy_price}
    long, _, _ = decks
    s = of_type(long, BASE, "summary")
    assert "{buy_price}" not in json.dumps(BASE["slides"][1])
    assert "UNVERIFIED: buy_price" in s.notes_slide.notes_text_frame.text
    assert "$69.44" in cells(s)


def test_valuation_chart_names_its_basis(decks):
    long, _, _ = decks
    ch = charts(of_type(long, BASE, "valuation"))[0]
    assert ch.has_title and "P/E history (TTM)" in ch.chart_title.text_frame.text


def test_pictures_fit_inside_their_frame(decks):
    long, _, _ = decks
    for t in ("title", "text_chart"):
        s = of_type(long, BASE, t)
        pics = [sh for sh in s.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]
        assert len(pics) == 1, t
        ph = {p.placeholder_format.idx: p for p in s.slide_layout.placeholders}[13 if t == "text_chart" else 12]
        p = pics[0]
        assert ph.left <= p.left and p.left + p.width <= ph.left + ph.width + 2
        assert ph.top <= p.top and p.top + p.height <= ph.top + ph.height + 2


def test_missing_tabs_and_pictures_fall_back_without_crashing(tmp_path, model_values):
    # a model without Multiples or Px Data must still give a deck; the note shows where the gap is
    wb = openpyxl.load_workbook(model_values)
    for name in ("Multiples", "Px Data"):
        del wb[name]
    thin = tmp_path / "thin.xlsx"
    wb.save(thin)
    long, _, out = run(tmp_path, thin)                   # BASE has text_chart slides with no picture
    val, setup = of_type(long, BASE, "valuation"), of_type(long, BASE, "setup")
    assert not charts(val) and "Multiples P/E history not found" in face_text(val)
    assert not charts(setup) and "Px Data price history not found" in face_text(setup)
    assert "WARNING: Multiples P/E history not found" in out and "WARNING: Px Data price history" in out
    assert "Picture missing" in face_text(of_type(long, BASE, "text_chart"))


def test_tables_and_charts_follow_the_values_copy(tmp_path, model_values):
    # the deck shows what the model says now: change the model, the deck changes
    wb = openpyxl.load_workbook(model_values)
    wb["SUM"]["C7"] = 81.25                              # cap table price
    px = wb["Px Data"]
    px.cell(row=px.max_row, column=2, value=99.99)       # last close
    wb["Valuation"]["E54"] = 9.9                         # R/R at today's entry on the ladder
    moved = tmp_path / "moved.xlsx"
    wb.save(moved)
    long, _ = build(tmp_path, moved)
    assert "$81.25" in cells(of_type(long, BASE, "summary"))
    assert list(charts(of_type(long, BASE, "setup"))[0].plots[0].series[0].values)[-1] == pytest.approx(99.99)
    assert "9.9x" in cells(of_type(long, BASE, "risk_reward"))


def test_same_out_path_for_both_decks_is_refused(tmp_path, model_values):
    f = tmp_path / "p.json"
    f.write_text(json.dumps(BASE))
    r = subprocess.run([sys.executable, str(SK / "scripts" / "build_deck.py"), "--plan", str(f),
                        "--template", str(SK / "assets" / "pitch_template.pptx"), "--values", str(model_values),
                        "--research", str(FIX / "research"), "--tabs", str(FIX / "tabs"),
                        "--out-long", str(tmp_path / "x.pptx"), "--out-core", str(tmp_path / "x.pptx")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and not (tmp_path / "x.pptx").exists()
