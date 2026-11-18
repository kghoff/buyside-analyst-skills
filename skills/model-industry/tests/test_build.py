from xlsx import Sheet


def test_sheet_writes_merges_before_conditional_formatting():
    # Excel refuses (repairs) a sheet whose mergeCells come after conditionalFormatting
    s = Sheet()
    s.set("A1", "s", "note", 0)
    s.merges.append("A1:I2")
    s.cf.append(("A1", "TRUE", 0))
    x = s.xml()
    assert '<mergeCells count="1"><mergeCell ref="A1:I2"/></mergeCells>' in x
    assert x.index("<mergeCells") < x.index("<conditionalFormatting")


import json
import os
import re
import shutil

import pytest

from conftest import FIX, REFERENCE
import build
from xlsx import Package


def small(tmp_path):
    W = tmp_path / "w"
    W.mkdir()
    I = json.load(open(os.path.join(FIX, "industry_small.json")))
    # link a real MOD cell (reference FY2025 revenue = 4662) so the LibreOffice recalc can be checked
    I["companies"][0]["lines"]["revenue"]["2025"] = {"v": 4662, "kind": "link", "f": "MOD!BP104", "note": ""}
    json.dump(I, open(W / "industry.json", "w"))
    M = tmp_path / "model.xlsx"
    shutil.copy(REFERENCE, M)
    return str(M), str(W)


def test_build_adds_two_tabs_and_leaves_every_other_part_byte_identical(tmp_path):
    M, W = small(tmp_path)
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    before, after = Package(M), Package(out)
    names = [s[0] for s in after.sheets()]
    assert names[-2:] == ["Industry P&L", "Industry Comparison"]
    allowed = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml",
               "xl/calcChain.xml", "docProps/app.xml"}
    changed = [p for p in before.parts if p not in allowed and before.parts[p] != after.parts.get(p)]
    assert changed == []


def test_build_formulas_follow_the_rules(tmp_path):
    M, W = small(tmp_path)
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    L = json.load(open(os.path.join(W, "layout.json")))
    pnl = Package(out)
    part = next(p for n, _, _, p in pnl.sheets() if n == "Industry P&L")
    x = pnl.text(part)
    r = L["rows"]["AAA"]["revenue"]
    assert f'<c r="E{r}"' in x and "<f>MOD!BP104</f>" in x                      # subject link, green
    gp = L["rows"]["AAA"]["gross_profit"]
    assert f"IF(AND(ISNUMBER(E{r}),ISNUMBER(E{L['rows']['AAA']['cogs']}))" in x.replace("&quot;", '"').split(f'r="E{gp}"')[1][:200]
    assert L["expected"][f"E{L['rows']['IND']['revenue']}"] == 4662 + 301
    assert L["expected"][f"D{L['rows']['IND_AN']['new_dollars']}"] == 1.0
    assert L["typed_without_note"] == []


def test_build_refuses_existing_tabs_without_replace(tmp_path):
    M, W = small(tmp_path)
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    with pytest.raises(SystemExit) as e:
        build.build(out, W, os.path.join(W, "again.xlsx"))
    assert e.value.code == 2
    build.build(out, W, os.path.join(W, "again.xlsx"), replace=True)        # replace works
    assert [s[0] for s in Package(os.path.join(W, "again.xlsx")).sheets()].count("Industry P&L") == 1


import lo


@pytest.mark.slow
@pytest.mark.skipif(not lo.SOFFICE, reason="LibreOffice not installed")
def test_verify_passes_on_a_fresh_build(tmp_path):
    # every formula, recalculated by LibreOffice, must equal the Python prototype; nothing else may change
    import subprocess, sys
    M, W = small(tmp_path)
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    here = os.path.join(os.path.dirname(__file__), "..", "scripts")
    r = subprocess.run([sys.executable, os.path.join(here, "verify.py"), "--before", M, "--built", out, "--work", W],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(os.path.join(W, "industry_comparison.png"))


def test_margin_and_roic_axes_ignore_peer_outliers(tmp_path):
    # Senseonics' op. margin of -14,000% auto-scaled chart 4 so far down that the industry and subject lines went
    # flat; the axis must follow industry + subject only and clip the outlier peer.
    M, W = small(tmp_path)
    I = json.load(open(os.path.join(W, "industry.json")))
    b = I["companies"][1]["lines"]
    b["revenue"]["2025"]["v"], b["oi"]["2025"]["v"] = 3, -150          # BBB op. margin -5,000%
    json.dump(I, open(os.path.join(W, "industry.json"), "w"))
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    pkg = Package(out)
    for title in ("Gross and operating margin", "ROIC (approx."):
        x = next(pkg.text(p) for p in pkg.parts if p.startswith("xl/charts/chart") and title in pkg.text(p))
        mn = float(re.search(r'<c:min val="([^"]+)"', x)[1])
        assert -1 <= mn <= 0, (title, mn)


@pytest.mark.slow
@pytest.mark.skipif(not lo.SOFFICE, reason="LibreOffice not installed")
def test_verify_passes_on_a_replace_rebuild_against_the_model_with_old_tabs(tmp_path):
    # --replace frees the old tabs' part names (sheetN, chartN, commentsN, vmlDrawingN...) and the rebuild reuses
    # them; verify must treat those as the rebuilt tabs, not as the user's parts changing, so --before "$M" works.
    import subprocess, sys
    M, W = small(tmp_path)
    first, again = os.path.join(W, "built.xlsx"), os.path.join(W, "again.xlsx")
    build.build(M, W, first)
    build.build(first, W, again, replace=True)
    here = os.path.join(os.path.dirname(__file__), "..", "scripts")
    r = subprocess.run([sys.executable, os.path.join(here, "verify.py"), "--before", first, "--built", again,
                        "--work", W], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_comments_vml_declares_enough_id_blocks_for_a_real_run():
    # A real run writes 1,000+ notes; one o:idmap block holds 1024 shape ids, so ids past it would belong to no
    # declared block (or to another drawing's) and Excel repairs the file.
    from xlsx import comments_parts
    _, vml = comments_parts({f"C{r}": "n" for r in range(1, 2501)}, 5)
    assert 'data="5,6,7"' in vml
    ids = [int(x) for x in re.findall(r'id="_x0000_s(\d+)"', vml)]
    assert min(ids) >= 5 * 1024 and max(ids) < 8 * 1024 and len(set(ids)) == 2500


def test_build_starts_after_excel_comma_list_idmap_blocks(tmp_path):
    # Excel writes data="7,8,9" for a sheet with many notes; reading only the first number would reuse blocks 8-9
    # and collide with the user's own comments. (The reference model's own vml already uses blocks 1, 2, 4 and 5.)
    M, W = small(tmp_path)
    pkg = Package(M)
    pkg.put("xl/drawings/vmlDrawing90.vml", '<xml><o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="7,8,9"/>'
                                            "</o:shapelayout></xml>")
    M = os.path.join(W, "with_vml.xlsx")          # the copied fixture is read-only
    pkg.save(M)
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    new = [Package(out).text(p) for p in Package(out).parts if p.endswith(".vml") and p not in pkg.parts]
    blocks = [int(x) for v in new for d in re.findall(r'data="([\d,]+)"', v) for x in d.split(",")]
    assert blocks and min(blocks) == 10


def test_industry_roic_label_explains_the_approximation(tmp_path):
    # The MOD ROIC is richer than the condensed lines allow; the industry ROIC row must say how it differs.
    M, W = small(tmp_path)
    out = os.path.join(W, "built.xlsx")
    build.build(M, W, out)
    L = json.load(open(os.path.join(W, "layout.json")))
    pkg = Package(out)
    cx = next(pkg.text(p) for p in pkg.parts if re.match(r"xl/comments\d+\.xml", p) and p not in Package(M).parts)
    assert f'<comment ref="B{L["rows"]["IND_AN"]["roic"]}"' in cx and "Condensed approximation of the MOD" in cx


def test_layout_follows_house_formatting(tmp_path):
    # The DXCM tabs were restyled by hand; new builds must come out that way without manual edits
    import openpyxl
    M, W = small(tmp_path)
    out = os.path.join(W, "built.xlsx")
    L = build.build(M, W, out)
    wb = openpyxl.load_workbook(out)
    p, c = wb["Industry P&L"], wb["Industry Comparison"]
    assert p.row_dimensions[1].height == 22 and c.row_dimensions[1].height == 22
    assert all(p.cell(4, k).fill.fgColor.rgb == "FF002060" for k in range(1, 6))        # navy header row A:last year
    sub = L["rows"]["IND"]["revenue"] - 1                                                  # "Income statement" band
    assert p.cell(sub, 2).value == "Income statement" and p.cell(sub, 1).fill.fgColor.rgb == "FF0070C0"
    assert p.cell(sub, 2).font.b and p.cell(sub, 2).font.color.rgb == "FFFFFFFF"
    assert p.cell(L["rows"]["AAA"]["revenue"] - 1, 2).fill.fill_type is None             # company blocks stay plain
    an = L["rows"]["IND_AN"]["count"] - 1
    assert p.cell(an, 1).value == "INDUSTRY ANALYSIS" and p.cell(an, 5).fill.fgColor.rgb == "FF002060"
    assert p.column_dimensions["C"].width == 13 and p.column_dimensions["E"].width == 13
    assert not p["A2"].alignment.wrap_text
    assert c.sheet_view.zoomScale == 117 and c.column_dimensions["A"].width == 9 and c.column_dimensions["T"].width == 13
    assert c.row_dimensions[76].height == 34
