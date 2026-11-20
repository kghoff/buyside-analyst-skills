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


def test_blank_tile_is_detected_and_ink_is_not():
    # a white tile must not become a picture; a tile with a small chart line must
    assert render_tabs.is_blank(bytes([255]) * 10000)
    assert not render_tabs.is_blank(bytes([255]) * 9900 + bytes([0]) * 100)
    assert render_tabs.is_blank(b"")


def test_tall_page_is_cut_into_tiles_not_one_image():
    tiles = render_tabs.tile_rects(600, 600 * 1.3 * 20)
    assert len(tiles) == 20 and all(c == 1 for _, c, _ in tiles)     # narrow page: one column of its own width
    assert all(r[2] == 600 and r[3] - r[1] <= 600 * 1.3 + 1e-6 for _, _, r in tiles)
    assert tiles[-1][2][3] == 600 * 1.3 * 20                        # the cut covers the whole page
    assert len(render_tabs.tile_rects(600, 700)) == 1


def test_wide_page_gets_columns_so_text_stays_legible():
    # a 5000 pt wide tab squeezed into 1600 px is unreadable (the Multiples tab): it needs several columns
    tiles = render_tabs.tile_rects(2500, 1000)
    assert [(r, c) for r, c, _ in tiles] == [(1, 1), (1, 2), (1, 3)]
    assert [t[2][0] for t in tiles] == [0, 1000, 2000] and tiles[-1][2][2] == 2500


def test_tiles_are_row_major_from_the_top_left():
    tiles = render_tabs.tile_rects(2000, 2600)
    assert [(r, c) for r, c, _ in tiles] == [(1, 1), (1, 2), (2, 1), (2, 2)]


def test_cap_is_larger_for_chart_tabs():
    # chart tabs need every chart; plain tabs are already in the digest, so a few layout tiles are enough
    assert render_tabs.MAX_CHART_TILES > render_tabs.MAX_PLAIN_TILES
    tiles = render_tabs.tile_rects(3000, 1300 * 20)               # 3 x 20 = 60 tiles
    for cap in (render_tabs.MAX_CHART_TILES, render_tabs.MAX_PLAIN_TILES):
        keep, truncated = render_tabs.pick_tiles(tiles, lambda t: False, cap)
        assert len(keep) == cap and truncated and keep == tiles[:cap]   # the top-left is kept
        keep, truncated = render_tabs.pick_tiles(tiles[:cap], lambda t: False, cap)
        assert len(keep) == cap and not truncated                       # exactly the cap is not truncation


def test_blank_tiles_do_not_count_toward_the_cap():
    tiles = render_tabs.tile_rects(600, 600 * 1.3 * 20)
    keep, truncated = render_tabs.pick_tiles(tiles, lambda t: t not in (tiles[0], tiles[19]), 4)
    assert keep == [tiles[0], tiles[19]] and not truncated


def test_clipped_title_still_matches_its_page():
    # a centred title wider than its column prints without letters at one or both ends; that must not flag the mapping
    title = "CAPITAL ASSET PRICING MODEL (CAPM)"
    assert render_tabs._on_page(title, "APITAL ASSET PRICING MODEL (CAPM\nWACC")
    assert render_tabs._on_page(title, "CAPITAL ASSET PRICING MO\nWACC")
    assert not render_tabs._on_page(title, "Revenue growth by segment")


def test_chartsheet_is_detected_and_does_not_crash_first_text(tmp_path):
    # a chartsheet has no cells; asking it for its first text used to raise AttributeError
    wb = openpyxl.Workbook()
    wb.active["A1"] = "Data tab title"
    ch = LineChart()
    ch.add_data(Reference(wb.active, min_col=1, min_row=1, max_row=1))
    cs = wb.create_chartsheet("Big chart")
    cs.add_chart(ch)
    p = str(tmp_path / "c.xlsx")
    wb.save(p)
    parts = {n: part for n, _, part in render_tabs.sheets(p)}
    assert render_tabs.is_chartsheet(parts["Big chart"]) and not render_tabs.is_chartsheet(parts["Sheet"])
    assert render_tabs.first_texts(p, ["Sheet"]) == {"Sheet": "Data tab title"}


def test_cap_chosen_from_has_chart():
    assert render_tabs.cap_for(True) == render_tabs.MAX_CHART_TILES
    assert render_tabs.cap_for(False) == render_tabs.MAX_PLAIN_TILES


@pytest.mark.slow
def test_render_small_workbook(tab_render):
    out, index, src = tab_render
    assert json.load(open(os.path.join(out, "index.json"))) == index
    by_tab = {e["tab"]: e for e in index}
    assert set(by_tab) == {"Notes", "Charts"}            # the hidden tab is printed by LibreOffice but left out
    assert by_tab["Charts"]["has_chart"] and not by_tab["Notes"]["has_chart"]
    # LibreOffice prints the hidden tab too, so the chart tab is page 3: a mapping that skipped it would say 2
    assert (by_tab["Notes"]["page"], by_tab["Charts"]["page"]) == (1, 3)
    for e in index:
        assert e["png"] and os.path.exists(os.path.join(out, e["png"]))
    assert not [f for f in os.listdir(out) if f.endswith(".pdf")]
    md = open(os.path.join(out, "index.md")).read()
    assert md.index("Charts") < md.index("Notes")                 # chart tabs first
    assert "Problems" not in md                                   # every tab's first text was found on its own page


# why: the deck tests point plan images at the fixture tabs folder; a name render_tabs could never write would let a
# test pass on a picture no real run has
def test_fixture_tab_pictures_use_render_tabs_names():
    from conftest import FIX
    for e in json.loads((FIX / "tabs" / "index.json").read_text()):
        assert e["png"] == render_tabs.png_name(e["tab"], e["page"], e["row"], e["col"])
        assert (FIX / "tabs" / e["png"]).is_file()
