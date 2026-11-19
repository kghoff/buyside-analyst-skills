import json
import os
import zipfile

import openpyxl
import pytest
from openpyxl.chart import LineChart, Reference

import render_tabs


def _book(path, chart_on):
    wb = openpyxl.Workbook()
    wb.active.title = "Plain"
    for name in ("Hidden", "Graphs"):
        wb.create_sheet(name)
    for ws in wb:
        ws["A1"] = "x"
        ws["A2"] = 1
    wb["Hidden"].sheet_state = "hidden"
    ch = LineChart()
    ch.add_data(Reference(wb[chart_on], min_col=1, min_row=2, max_row=2))
    wb[chart_on].add_chart(ch, "C1")
    wb.save(path)
    return path


def test_chart_detected_from_the_zip_only_on_the_chart_tab(tmp_path):
    # the analyst is told which tabs to look at first: a tab without a drawing must not be flagged
    p = _book(str(tmp_path / "b.xlsx"), "Graphs")
    assert render_tabs.chart_tabs(p) == {"Graphs"}
    with zipfile.ZipFile(p) as z:
        assert any(n.startswith("xl/charts/") for n in z.namelist())


def test_hidden_tabs_are_not_in_the_visible_list(tmp_path):
    # LibreOffice prints visible tabs only, so page numbers follow this list
    p = _book(str(tmp_path / "b.xlsx"), "Graphs")
    states = {n: s for n, s, _ in render_tabs.sheets(p)}
    assert states["Hidden"] != "visible" and states["Plain"] == "visible"


def test_blank_tile_is_detected_and_ink_is_not():
    # a white tile must not become a picture; a tile with a small chart line must
    assert render_tabs.is_blank(bytes([255]) * 10000)
    assert not render_tabs.is_blank(bytes([255]) * 9900 + bytes([0]) * 100)
    assert render_tabs.is_blank(b"")


def test_tall_page_is_cut_into_tiles_not_one_image():
    rects = render_tabs.tile_rects(600, 600 * 1.3 * 20)
    assert len(rects) == 20
    assert all(r[2] == 600 and r[3] - r[1] <= 600 * 1.3 + 1e-6 for r in rects)
    assert rects[-1][3] == 600 * 1.3 * 20            # the cut covers the whole page
    assert len(render_tabs.tile_rects(600, 700)) == 1


def test_cap_of_eight_and_truncated_flag():
    rects = render_tabs.tile_rects(600, 600 * 1.3 * 20)
    keep, truncated = render_tabs.pick_tiles(rects, lambda r: False)
    assert len(keep) == 8 and truncated and keep[0] == rects[0]    # the top is kept
    keep, truncated = render_tabs.pick_tiles(rects[:8], lambda r: False)
    assert len(keep) == 8 and not truncated                        # exactly 8 is not truncation


def test_blank_tiles_do_not_count_toward_the_cap():
    rects = render_tabs.tile_rects(600, 600 * 1.3 * 20)
    blank = lambda r: r != rects[0] and r != rects[19]
    keep, truncated = render_tabs.pick_tiles(rects, blank)
    assert keep == [rects[0], rects[19]] and not truncated


@pytest.mark.slow
def test_render_small_workbook(tab_render):
    out, index = tab_render
    assert json.load(open(os.path.join(out, "index.json"))) == index
    by_tab = {e["tab"]: e for e in index}
    assert set(by_tab) == {"Notes", "Charts"}
    assert by_tab["Charts"]["has_chart"] and not by_tab["Notes"]["has_chart"]
    for e in index:
        assert e["png"] and os.path.exists(os.path.join(out, e["png"]))
    assert not [f for f in os.listdir(out) if f.endswith(".pdf")]
    md = open(os.path.join(out, "index.md")).read()
    assert md.index("Charts") < md.index("Notes")                 # chart tabs first
