import os, re, shutil

import openpyxl
import pytest
from openpyxl.chart import LineChart, Reference
from openpyxl.comments import Comment
from openpyxl.workbook.defined_name import DefinedName

import lo
from xlsx import Package
from xledit import (add_cf, arrow, ensure_drawing, insert_rows, put_anchors, set_cells, shift_formula, textbox,
                    unshare)


def test_shift_moves_only_rows_below_the_insert_on_the_target_tab():
    # the user's other tabs point into MOD by row; an inserted KPI row must not make them read the wrong line
    assert shift_formula("=MOD!H104/MOD!H30", "Research", "MOD", 34, 3) == "=MOD!H107/MOD!H30"
    assert shift_formula("SUM(H33:H40)", "MOD", "MOD", 34, 3) == "SUM(H33:H43)"       # range across the insert grows
    assert shift_formula("=$B$50+B$34+$B33", "MOD", "MOD", 34, 2) == "=$B$52+B$36+$B33"
    assert shift_formula("='Px Data'!B50+B50", "Research", "MOD", 34, 2) == "='Px Data'!B50+B50"   # not MOD
    assert shift_formula('=IF(A1="MOD!H99",SUM(5:40),MOD!A:A)', "MOD", "MOD", 34, 1) == '=IF(A1="MOD!H99",SUM(5:41),MOD!A:A)'


def test_shared_formulas_are_written_out_before_rows_move():
    # a shared formula's children are offsets from its first cell; inserting rows between them would re-point them
    xml = ('<sheetData><row r="33"><c r="C33"><f t="shared" ref="C33:C35" si="0">B33*2</f><v>2</v></c></row>'
           '<row r="34"><c r="C34"><f t="shared" si="0"/><v>4</v></c></row>'
           '<row r="35"><c r="C35"><f t="shared" si="0"/><v>6</v></c></row></sheetData>')
    out = unshare(xml, "MOD", "MOD")
    assert "<f>B33*2</f>" in out and "<f>B34*2</f>" in out and "<f>B35*2</f>" in out and 't="shared"' not in out


def test_set_cells_never_overwrites_a_filled_cell():
    # the user's own annotations stay; only empty cells get Claude's text
    xml = ('<worksheet><dimension ref="A1:C2"/><sheetData><row r="2"><c r="B2" t="inlineStr"><is><t>Mine</t></is></c>'
           '<c r="C2" s="1"/></row></sheetData></worksheet>')
    out, skipped = set_cells(xml, {"B2": ("s", "Claude", 0), "C2": ("s", "new", 0), "A5": ("n", 3, 0)})
    assert skipped == ["B2"] and "Mine" in out and "Claude" not in out and ">new<" in out
    assert out.index('r="2"') < out.index('r="5"') and '<dimension ref="A1:C5"/>' in out


def test_conditional_formatting_goes_before_page_margins():
    xml = '<worksheet><sheetData/><pageMargins left="1"/><drawing r:id="rId1"/></worksheet>'
    out = add_cf(xml, [("B2:B9", "B2<C2", 0)])
    assert out.index("<conditionalFormatting") < out.index("<pageMargins")


def _book(path):
    wb = openpyxl.Workbook()
    m = wb.active
    m.title = "MOD"
    for r in range(1, 11):
        m.cell(r, 1, r * 10)
    m["B5"] = "=A5+A9"
    m["B9"] = "=SUM(A1:A10)"
    m["A9"].comment = Comment("row nine", "User")
    o = wb.create_sheet("Research")
    o["A1"] = "=MOD!A9*2"
    o["A2"] = "=SUM(MOD!A3:A8)"
    o["A3"] = "=A1+1"
    ch = LineChart()
    ch.add_data(Reference(m, min_col=1, min_row=6, max_row=10))
    o.add_chart(ch, "C3")
    wb.defined_names["Nine"] = DefinedName("Nine", attr_text="MOD!$A$9")
    o["A4"] = "=Nine"
    wb.save(path)


@pytest.mark.skipif(not lo.SOFFICE, reason="LibreOffice not installed")
def test_inserted_rows_leave_every_value_where_excel_would(tmp_path):
    # the WHY: after the insert, every number on every tab must be the same as before (checked by a real recalc)
    src, out = str(tmp_path / "m.xlsx"), str(tmp_path / "out" / "m.xlsx")
    _book(src)
    pkg = Package(src)
    insert_rows(pkg, "MOD", 4, 2)
    pkg.finish()
    os.makedirs(tmp_path / "out")
    pkg.save(out)
    rc = openpyxl.load_workbook(lo.recalc(out, str(tmp_path / "rc")), data_only=True)
    m, o = rc["MOD"], rc["Research"]
    assert [m.cell(r, 1).value for r in (1, 3, 4, 5, 6, 11, 12)] == [10, 30, None, None, 40, 90, 100]
    assert m["B7"].value == 140 and m["B11"].value == 550
    assert [o["A1"].value, o["A2"].value, o["A3"].value, o["A4"].value] == [180, 330, 181, 90]
    p = Package(out)
    assert "MOD!$A$11" in p.text("xl/workbook.xml")
    assert "$A$8:$A$12" in p.text("xl/charts/chart1.xml")
    assert 'ref="A11"' in [p.text(k) for k in p.parts if k.startswith("xl/comments")][0]


def test_claude_shapes_are_replaced_on_rerun_and_users_stay(tmp_path):
    src = str(tmp_path / "m.xlsx")
    _book(src)
    pkg = Package(src)
    part = [s[3] for s in pkg.sheets() if s[0] == "Research"][0]
    d = ensure_drawing(pkg, part)
    users = ('<xdr:twoCellAnchor><xdr:from/><xdr:to/><xdr:sp><xdr:nvSpPr><xdr:cNvPr id="40" name="TextBox 4"/>'
            '</xdr:nvSpPr></xdr:sp><xdr:clientData/></xdr:twoCellAnchor>')
    x = pkg.text(d)
    pkg.put(d, x[:x.rindex("</")] + users + x[x.rindex("</"):])
    for _ in range(2):
        put_anchors(pkg, d, [textbox("note", (1, 0, 2, 0), (4, 0, 4, 0), "G7 launch"),
                             arrow("note arrow", (2, 0, 4, 0), (3, 0, 6, 0))])
    x = pkg.text(d)
    assert x.count('name="P1 note"') == 1 and x.count('name="P1 note arrow"') == 1 and 'name="TextBox 4"' in x
    assert len(set(re.findall(r'cNvPr id="(\d+)"', x))) == len(re.findall(r'cNvPr id="(\d+)"', x))


def test_a_shared_formula_child_is_not_mistaken_for_a_formula():
    # a tab whose shared formulas don't touch MOD keeps them; their '<f .../>' children must not swallow the next
    # cell (on the DXCM model this wiped 105k values on Px Data and everything that reads it)
    from xledit import _shift_formulas_in
    x = '<c r="A1"><f t="shared" si="0"/><v>1</v></c><c r="A2"><f>MOD!B40</f></c>'
    assert _shift_formulas_in(x, "Px Data", "MOD", 34, 5) == x.replace("B40", "B45")


def test_verify_rejects_xml_excel_would_refuse(tmp_path):
    # LibreOffice opened a model with a bare '&' in a cell note; Excel would have called the file damaged
    import zipfile
    from xlverify import bad_parts
    p = tmp_path / "m.xlsx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("xl/comments1.xml", "<comments><t>Q&A</t></comments>")
        z.writestr("xl/ok.xml", "<a>Q&amp;A</a>")
    assert [b.split(":")[0] for b in bad_parts(str(p))] == ["xl/comments1.xml"]
