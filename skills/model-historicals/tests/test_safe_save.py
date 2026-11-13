"""safe_save: skills that edit with openpyxl save through it, so the user's text boxes, shapes and pictures survive (openpyxl
drops them on save) while the result equals what openpyxl would have written, cell for cell."""
import os
import re
import sys
import zipfile

import openpyxl
import pytest
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import safe_save as S  # noqa: E402
from xlsx import Package  # noqa: E402

TEXTBOX = ('<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><xdr:twoCellAnchor>'
           '<xdr:from><xdr:col>5</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>9</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
           '<xdr:to><xdr:col>8</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>12</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
           '<xdr:sp macro="" textlink=""><xdr:nvSpPr><xdr:cNvPr id="2" name="the user note"/><xdr:cNvSpPr txBox="1"/></xdr:nvSpPr>'
           '<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
           '</a:prstGeom></xdr:spPr><xdr:txBody><a:bodyPr/><a:p><a:r><a:t>the user text box</a:t></a:r></a:p></xdr:txBody>'
           '</xdr:sp><xdr:clientData/></xdr:twoCellAnchor></xdr:wsDr>')


def _model(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for r in range(1, 21):
        ws.cell(r, 2, f"line {r}")
        ws.cell(r, 3, r * 10)
    ws["D15"] = "=C14+C10"
    ws["C1"].fill = PatternFill("solid", fgColor="FFD9D9D9")
    ws.merge_cells("F18:G18")
    ws["B5"].comment = Comment("the user's note", "the user")
    other = wb.create_sheet("Other")
    other["A1"] = "=MOD!C12"
    p = str(tmp_path / "m.xlsx")
    wb.save(p)
    pkg = Package(p)                                   # add the user's text box the way Excel stores it
    part = {s[0]: s[3] for s in pkg.sheets()}["MOD"]
    pkg.put("xl/drawings/drawing1.xml", TEXTBOX)
    pkg.content_override("/xl/drawings/drawing1.xml", "application/vnd.openxmlformats-officedocument.drawing+xml")
    rid = pkg.attach(part, "drawing", "xl/drawings/drawing1.xml")
    xml = pkg.text(part)
    if 'xmlns:r="' not in xml[:xml.index(">", xml.index("<worksheet"))]:
        xml = xml.replace("<worksheet ", '<worksheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    xml = re.sub(r"<legacyDrawing ([^>]*?)r:id=", lambda m: f'<drawing r:id="{rid}"/><legacyDrawing {m.group(1)}r:id=', xml, count=1)
    pkg.put(part, xml)
    pkg.save(p)
    return p


def _edit(path):
    """What the skills do: insert rows (logged), write values / formulas / styles, add a note."""
    wb = openpyxl.load_workbook(path)
    ws = wb["MOD"]
    ws.insert_rows(8, 2)                                # openpyxl's own insert shifts no formulas: shift them like xlmodel
    S.log_move(ws, S.insert_fn(8, 2))
    ws["D17"] = "=C16+C12"                              # the formula that was D15 (=C14+C10), shifted by the skill
    wb["Other"]["A1"] = "=MOD!C14"
    ws["B8"], ws["C8"] = "new line", 1.5
    ws["C8"].font = Font(color="FF0000FF", bold=True)
    ws["C8"].number_format = "0.0%"
    ws["C9"].comment = Comment("added by a skill", "Claude")
    ws.merged_cells.ranges = set()
    ws.merge_cells("F20:G20")
    return wb


def test_text_box_survives_and_moves_with_its_rows(tmp_path):
    src = _model(tmp_path)
    wb = _edit(src)
    out = str(tmp_path / "out.xlsx")
    S.safe_save(wb, src, out)
    z = zipfile.ZipFile(out)
    d = z.read("xl/drawings/drawing1.xml").decode()
    assert "the user text box" in d
    assert re.findall(r"<xdr:row>(\d+)</xdr:row>", d) == ["11", "14"]        # rows 10-13 (0-based 9-12) moved down 2


def test_result_equals_what_openpyxl_would_have_written(tmp_path):
    src = _model(tmp_path)
    wb = _edit(src)
    ref = str(tmp_path / "openpyxl.xlsx")
    _edit(src).save(ref)
    out = str(tmp_path / "out.xlsx")
    S.safe_save(wb, src, out)
    a, b = S._snapshot(ref)[0], S._snapshot(out)[0]
    for name in a:
        for what in ("cells", "notes", "merges"):
            assert a[name][what] == b[name][what], (name, what)
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws["D17"].value == "=C16+C12" and openpyxl.load_workbook(out)["Other"]["A1"].value == "=MOD!C14"
    assert ws["B5"].comment.text == "the user's note" and ws["C9"].comment.text == "added by a skill"


def test_an_unlogged_move_still_reproduces_openpyxls_grid_and_keeps_the_text_box(tmp_path):
    """A move a skill forgot to log is still reproduced cell by cell (the equivalence check guards the result)."""
    src = _model(tmp_path)
    wb = openpyxl.load_workbook(src)
    wb["MOD"].delete_rows(3, 1)                         # not logged, formulas not shifted either
    out = str(tmp_path / "out.xlsx")
    S.safe_save(wb, src, out)                           # cell-by-cell writes still reproduce openpyxl's grid...
    d = zipfile.ZipFile(out).read("xl/drawings/drawing1.xml").decode()
    assert "the user text box" in d                         # ...and the text box is still there


def test_deleted_rows_drop_and_references_into_them_are_refused(tmp_path):
    src = _model(tmp_path)
    pkg = Package(src)
    S.remap_rows(pkg, "MOD", S.delete_fn(3, 2))         # rows 3-4 gone; nothing refers to them
    p = str(tmp_path / "d.xlsx")
    pkg.save(p)
    ws = openpyxl.load_workbook(p)["MOD"]
    assert ws["B3"].value == "line 5" and ws["D13"].value == "=C12+C8"
    pkg = Package(src)
    with pytest.raises(S.RefIntoDeleted):               # D15 refers to C14 and C10: deleting row 10 must refuse
        S.remap_rows(pkg, "MOD", S.delete_fn(10, 1))


def test_a_block_move_keeps_every_formula_pointing_at_the_same_cells(tmp_path):
    """Moving rows 3-4 below row 10 (cut + insert): formulas anywhere still read the same cells; a range the move
    would split is refused rather than silently re-pointed."""
    src = _model(tmp_path)
    pkg = Package(src)
    S.remap_rows(pkg, "MOD", S.move_fn(3, 4, 11), strict=True)   # rows 3,4 -> 9,10; rows 5-10 -> 3-8
    p = str(tmp_path / "moved.xlsx")
    pkg.save(p)
    ws = openpyxl.load_workbook(p)["MOD"]
    assert ws["B9"].value == "line 3" and ws["B10"].value == "line 4" and ws["B3"].value == "line 5"
    assert ws["D15"].value == "=C14+C8"                  # C10 (line 10) now sits in row 8
    rows = [int(r) for r in re.findall(r'<row r="(\d+)"', zipfile.ZipFile(p).read("xl/worksheets/sheet1.xml").decode())]
    assert rows == sorted(rows)
    wb = openpyxl.load_workbook(src)
    wb["Other"]["B1"] = "=SUM(MOD!C2:C6)"               # spans the moved block's edge
    wb.save(src)
    with pytest.raises(S.RefIntoDeleted):
        S.remap_rows(Package(src), "MOD", S.move_fn(3, 4, 11), strict=True)
