"""The SUM tab: first sheet, the course template, every number a link to its home tab (green), SUM's own arithmetic
black, the judgment boxes yellow and empty for write-pitch, the user's file untouched outside SUM."""
import zipfile

import openpyxl

from tabkit import changed_parts


def _wb(built):
    return openpyxl.load_workbook(built[0])          # the built TEST copy, read only by the test


def test_sum_is_first_and_nothing_else_moved(built):
    wb = _wb(built)
    assert wb.sheetnames[0] == "SUM" and wb.sheetnames[1] == "MOD"
    assert wb.active.title == "Valuation" and wb["MOD"].print_area is not None


def test_cap_table_links_the_dcf_bridge(built):
    ws = _wb(built)["SUM"]
    assert ws["C7"].value == "=DCF!$C$18" and ws["D7"].value == "=DCF!$D$18"
    assert ws["C12"].value == "=DCF!$C$14" and ws["C13"].value == "=C9+C12"
    assert ws["C15"].value == "=Multiples!$H$39/1000000"


def test_targets_link_the_primary_multiple(built):
    ws = _wb(built)["SUM"]
    assert ws["C33"].value == "=Valuation!$B$91"                       # IRR
    assert ws["C39"].value == "=Valuation!$B$39" and ws["C46"].value == "=Valuation!$B$42"
    assert ws["B37"].value == "P/E: NTM+1 EPS (Q1 27E to Q4 27E)"


def test_ntm_fcf_label_names_its_quarters(built):
    ws = _wb(built)["SUM"]
    assert "Q1 26E to Q4 26E" in ws["B22"].value and "internal" in ws["B22"].value


def test_estimates_grid_and_street_variance(built):
    ws = _wb(built)["SUM"]
    assert [ws.cell(4, c).value for c in range(6, 14)] == ["2022A", "2023A", "2024A", "2025A", "2026E", "2027E",
                                                           "2028E", "2029E"]
    assert ws["J12"].value == "=Multiples!$B$34"                       # 2026E Street EPS
    assert ws["J13"].value == "=IF(AND(J12>0,ISNUMBER(J10)),J10/J12-1,NA())"
    assert ws["L12"].value == "n/a" and ws["L13"].value == "n/a"        # 2028E: no Street estimate


def test_scenarios_mirror_the_tree(built):
    ws = _wb(built)["SUM"]
    assert [ws.cell(r, 16).value for r in range(5, 10)] == ["Bull", "Base", "Risk", "Bear", "Probability-weighted"]
    assert ws["Q6"].value == "=Valuation!$B$36" and ws["R6"].value == "=Valuation!$B$38"   # Base = reward
    assert ws["Q5"].value == "n/a"                                                          # Bull: a DCF value
    assert ws["U9"].value == "=Valuation!$D$121"


def test_ladder_has_every_rung(built):
    ws = _wb(built)["SUM"]
    assert [ws.cell(r, 24).value for r in range(5, 12)] == [f"=Valuation!$B${r}" for r in range(75, 82)]


def test_colours(built):
    ws = _wb(built)["SUM"]
    assert ws["C7"].font.color.rgb == "FF008000"                       # link green
    assert ws["C9"].font.color.rgb == "FF000000"                       # formula black
    for ref in ("C19", "C20", "C51", "B54", "E21", "E33"):
        assert ws[ref].fill.fgColor.rgb == "FFFFFF99", ref                # the house pale yellow (Valuation's)


def test_yellow_means_only_yours_to_type(built):
    """Yellow tells the PM "yours to type"; a key OUTPUT in yellow would invite typing over a formula. Every yellow
    cell on SUM must be one of the input cells, and the key results are bold and outlined instead."""
    import json
    import os
    ws = _wb(built)["SUM"]
    inputs = set(json.load(open(os.path.join(built[2], "layout.json")))["inputs"].values())
    yellow = {c.coordinate for row in ws.iter_rows() for c in row
              if c.fill.fill_type == "solid" and c.fill.fgColor.rgb in ("FFFFFF99", "FFFFFF00")
              and not (c.value is None and c.coordinate not in inputs)}
    assert yellow == inputs - {"C3"}          # Action is a green link to Valuation's verdict until typed over
    for ref in ("C30", "C31", "C33", "C47", "F10", "F13"):
        assert ws[ref].font.b and ws[ref].fill.fgColor.rgb != "FFFFFF99", ref


def test_section_titles_are_dark_blue_bars(built):
    """A PM scans the page by its blocks: each block's title is a dark-blue bar with white bold text, across the
    block's full width, so the blocks read apart at a glance."""
    import json
    import os
    ws = _wb(built)["SUM"]
    last = json.load(open(os.path.join(built[2], "layout.json")))["refs"]["grid_cols"][-1]
    for ref in ("B6", "D6", "B26", "D26", "B36", "B43", "E3", f"{last}3", "P3", "U3", "W3", "AA3", "E20", "E32", "B53"):
        c = ws[ref]
        assert c.fill.fgColor.rgb == "FF002060" and c.font.color.rgb == "FFFFFFFF" and c.font.b, ref
    assert ws["F4"].fill.fgColor.rgb == "FFBDD7EE" and ws["F4"].font.b      # the years: a light-blue header row


def test_cap_table_is_boxed(built):
    """The cap table is the anchor of the page (price, shares, EV): a thick outline sets it apart from the targets."""
    ws = _wb(built)["SUM"]
    assert all(ws[f"B{r}"].border.left.style == "medium" for r in range(6, 17))
    assert all(ws[f"{c}16"].border.bottom.style == "medium" for c in "BCD")
    assert ws["D10"].border.right.style == "medium" and ws["C10"].border.right.style is None
    assert ws["F14"].border.top.style == "thin"           # the multiples rows sit apart from the P&L rows


def test_every_typed_number_has_a_note(built):
    import json
    import os
    lay = json.load(open(os.path.join(built[2], "layout.json")))
    typed = [r for r, k in lay["kinds"].items() if k in ("typed", "input")]
    assert typed and all(r in lay["notes"] for r in typed)


def test_only_sum_and_workbook_parts_changed(built, fixture_model):
    from tabkit import tab_parts
    from xlsx import Package
    # allowed: SUM's own parts (sheet, rels, comments, vml) + workbook.xml, its rels, content types, styles
    assert changed_parts(fixture_model, built[0], tab_parts(Package(built[0]), "SUM")) == []
    mod = "xl/worksheets/sheet1.xml"
    assert zipfile.ZipFile(fixture_model).read(mod) == zipfile.ZipFile(built[0]).read(mod)


def test_short_position_warns(fixture_model, tmp_path):
    """% returns and their colours are long-side math; a short on Valuation must be flagged to the reader."""
    import shutil
    import build
    m = str(tmp_path / "s.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)          # a test copy, never a user's model
    wb["Valuation"]["B14"] = "short"
    wb.save(m)
    rep = build.build(m, str(tmp_path / "w"), "TEST", str(tmp_path / "o.xlsx"), research_dir=str(tmp_path),
                      fetch=lambda *a: (_ for _ in ()).throw(AssertionError("no Yahoo")))
    assert any("long-side math" in w for w in rep["warnings"])


def test_labels_and_cap_period(built):
    ws = _wb(built)["SUM"]
    assert ws["B36"].value == "12-month base target (P/E only)" and ws["B43"].value == "12-month risk case (P/E only)"
    assert "balance sheet at Q4 25" in ws["B6"].value
