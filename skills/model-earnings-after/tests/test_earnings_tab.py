"""Bands 9-15 are appended under band 8 without touching bands 1-8: the preview is the user's record of what we
expected, and the wrap is only honest if that record is unchanged. A rerun replaces bands 9-15 only."""
import re
import zipfile

import openpyxl
import pytest

import earnings_tab as et
from xlsx import CT, NS_REL, Package, Sheet, Styles, relpath_of

ROW = r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)'


def _kept(xml, start):
    return [m.group(0) for m in re.finditer(ROW, xml, re.S) if int(m.group(1)) < start]


def _splice(src, out, start, cells, notes):
    pkg = Package(src)
    st = Styles(pkg.text("xl/styles.xml"))
    sh = Sheet()
    for ref, text in cells.items():
        sh.set(ref, "s", text, st.xf())
    et.splice(pkg, et.part(pkg), start, sh, notes, et.read(src)["after_start"])
    pkg.put("xl/styles.xml", st.render())
    pkg.save(out)
    return out


def test_read_finds_band7_and_refs(fixture_model):
    """Bands 9-15 compare the print with band 7's frozen numbers and read the call from bands 1, 2 and 5."""
    t = et.read(fixture_model)
    assert t["frozen"]["quarter"] == "Q4 26E" and t["frozen"]["date"] == "2026-11-18"
    assert t["frozen"]["fy"] == "2026E"
    assert t["after_start"] is None and t["start"] == t["end"] + 2
    for k in ("price", "up", "down", "implied", "expected_move", "call_q", "call_g", "p_beat", "stance"):
        assert k in t["refs"], k
    rev = next(r for r in t["frozen"]["rows"] if r["label"] == "INCOME STATEMENT | Revenue")
    assert isinstance(rev["q"], float) and isinstance(rev["fy"], float)
    assert not any(et.BAND_RE.match(r["label"]) for r in t["frozen"]["rows"])


def test_each_ref_is_found_inside_its_own_band(fixture_model):
    """Labels repeat across bands (Revenue, Units, EPS in bands 4 and 6), so a key found in the wrong band would
    silently read the wrong cell: every ref must sit inside the band LABELS names for it."""
    t = et.read(fixture_model)
    for k, ref in t["refs"].items():
        band = et.LABELS[k][2]
        lo, hi = t["bands"][band]
        assert lo < int(ref.split("$")[-1]) <= hi, (k, ref)
    assert t["refs"]["price"] == "$B$10" and t["refs"]["p_beat"] == "$B$30" and t["refs"]["implied"] == "$B$84"


def test_a_label_outside_its_band_is_not_used(fixture_model, tmp_path):
    """If band 1 loses its 'Price' row, a 'Price' row in another band must not stand in for it."""
    pkg = Package(fixture_model)
    p = et.part(pkg)
    x = pkg.text(p).replace("<t>Price</t>", "<t>Price (moved)</t>", 1)
    x = x.replace("<t>Key metric</t>", "<t>Price</t>", 1)     # band 3 now has a 'Price' row
    pkg.put(p, x)
    out = str(tmp_path / "o.xlsx")
    pkg.save(out)
    assert "price" not in et.read(out)["refs"]


def test_splice_keeps_bands_1_to_8_byte_identical(model, tmp_path):
    """Every row above band 9 stays byte for byte, in whatever XML style the last save wrote it."""
    t = et.read(model)
    part = et.part(Package(model))
    out = _splice(model, str(tmp_path / "o.xlsx"), t["start"], {f"A{t['start']}": "9. ACTUAL VS FROZEN"},
                  {f"A{t['start']}": "a note"})
    old = zipfile.ZipFile(model).read(part).decode()
    new = zipfile.ZipFile(out).read(part).decode()
    assert _kept(new, t["start"]) == _kept(old, t["start"]) and len(_kept(old, t["start"])) > 100
    assert et.read(out)["after_start"] == t["start"]


def test_splice_keeps_the_preview_notes_and_adds_new_ones(model, tmp_path):
    """The preview's notes carry each judgment's reason and source; losing them on splice loses the audit trail.
    The result must still open (a broken comments / VML pair makes Excel repair the file)."""
    t = et.read(model)
    s = t["start"]
    out = _splice(model, str(tmp_path / "o.xlsx"), s, {f"A{s}": "9. ACTUAL VS FROZEN", f"B{s + 1}": "x"},
                  {f"B{s + 1}": "new note & <more>"})
    wb = openpyxl.load_workbook(out)
    ws = wb["Earnings"]
    assert ws["B10"].comment is not None and "Yahoo Finance" in ws["B10"].comment.text
    assert ws["B11"].comment.text.startswith("Agent: hold")
    assert ws[f"B{s + 1}"].comment.text == "new note & <more>"
    wb.close()


def test_rerun_replaces_only_the_after_rows(model, tmp_path):
    """A rerun replaces bands 9-15 and their notes; the second run's rows and notes are the only ones left."""
    s = et.read(model)["start"]
    first = _splice(model, str(tmp_path / "first.xlsx"), s,
                    {f"A{s}": "9. ACTUAL VS FROZEN", f"B{s + 1}": "FIRST-RUN"}, {f"B{s + 1}": "FIRST-RUN note"})
    assert et.read(first)["start"] == s
    second = _splice(first, str(tmp_path / "second.xlsx"), s,
                     {f"A{s}": "9. ACTUAL VS FROZEN", f"B{s + 2}": "SECOND-RUN"}, {f"B{s + 2}": "SECOND-RUN note"})
    pkg = Package(second)
    x = pkg.text(et.part(pkg))
    assert "SECOND-RUN" in x and "FIRST-RUN" not in x
    comments = "".join(pkg.text(n) for n in pkg.parts if n.startswith("xl/comments"))
    assert "SECOND-RUN note" in comments and "FIRST-RUN note" not in comments
    old = zipfile.ZipFile(model).read(et.part(pkg)).decode()
    assert _kept(x, s) == _kept(old, s)


def test_splice_adds_notes_to_a_tab_that_had_none(tmp_path):
    """A user may have deleted every preview note; the after-print notes still need a comments part of their own."""
    src = str(tmp_path / "plain.xlsx")
    wb = openpyxl.Workbook()
    wb.active.title = "Earnings"
    wb["Earnings"]["A1"] = "1. PRINT SNAPSHOT AND THE CALL"
    wb.save(src)
    out = _splice(src, str(tmp_path / "o.xlsx"), 3, {"A3": "9. ACTUAL VS FROZEN"}, {"A3": "a note"})
    ws = openpyxl.load_workbook(out)["Earnings"]
    assert ws["A3"].comment.text == "a note" and ws["A1"].value == "1. PRINT SNAPSHOT AND THE CALL"


# ---------------------------------------------------------------- the user's content below band 8
def _add(model, row_xml=None, comment=None, out=None):
    """The fixture model with an extra row and / or note the user typed (raw XML, the way Excel would keep them)."""
    pkg = Package(model)
    p = et.part(pkg)
    if row_xml:
        pkg.put(p, pkg.text(p).replace("</sheetData>", row_xml + "</sheetData>"))
    if comment:
        c = "xl/comments/comment1.xml"
        pkg.put(c, pkg.text(c).replace("</commentList>", comment + "</commentList>"))
    pkg.save(out)
    return out


def test_end_counts_every_column(model, tmp_path):
    """A value the user typed in E131, under band 8, must move band 9 below it, not be overwritten by it."""
    out = _add(model, '<row r="131"><c r="E131" t="inlineStr"><is><t>mine</t></is></c></row>',
               out=str(tmp_path / "o.xlsx"))
    t = et.read(out)
    assert t["end"] == 131 and t["start"] == 133


def test_splice_refuses_to_drop_the_users_cells_or_notes(model, tmp_path):
    """With no band 9 yet, anything in the rows splice would drop is the user's: stop and name it, never delete."""
    out = _add(model, '<row r="131"><c r="E131" t="inlineStr"><is><t>mine</t></is></c></row>',
               '<comment ref="E140" authorId="0"><text><t>my note</t></text></comment>', str(tmp_path / "o.xlsx"))
    pkg = Package(out)
    with pytest.raises(SystemExit) as e:
        et.splice(pkg, et.part(pkg), 131, Sheet(), {}, None)
    assert "E131" in str(e.value) and "E140" in str(e.value)


def test_splice_refuses_to_orphan_a_threaded_comment(model, tmp_path):
    """Excel's threaded comments live in their own part; dropping their row would leave a broken thread."""
    t = et.read(model)
    pkg = Package(model)
    p = et.part(pkg)
    tc = "xl/threadedComments/threadedComment1.xml"
    rels = pkg.rels(relpath_of(p))
    rels["rIdTC"] = ("http://schemas.microsoft.com/office/2017/10/relationships/threadedComment",
                     "../threadedComments/threadedComment1.xml")
    pkg.write_rels(relpath_of(p), rels)
    body = ('<ThreadedComments xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments">'
            '<threadedComment ref="{}" dT="2026-11-19T10:00:00.00" personId="{{0}}" id="{{1}}"><text>hi</text>'
            "</threadedComment></ThreadedComments>")
    pkg.put(tc, body.format("B10"))           # above band 9: left alone
    et.splice(pkg, p, t["start"], Sheet(), {}, t["start"])
    assert pkg.text(tc) == body.format("B10")
    pkg.put(tc, body.format(f"B{t['start'] + 1}"))
    with pytest.raises(SystemExit) as e:
        et.splice(pkg, p, t["start"], Sheet(), {}, t["start"])
    assert f"B{t['start'] + 1}" in str(e.value)


# ---------------------------------------------------------------- an Excel-saved tab
VML_HEAD = ('<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:x="urn:schemas-microsoft-com:office:excel"><o:shapelayout v:ext="edit">'
            '<o:idmap v:ext="edit" data="1"/></o:shapelayout>'
            '<v:shapetype id="_x0000_t201" coordsize="21600,21600" o:spt="201" path="m,l,21600r21600,l21600,xe">'
            '<v:stroke joinstyle="miter"/><v:path shadowok="f" o:extrusionok="f" strokeok="f" fillok="f" '
            'o:connecttype="rect"/></v:shapetype>')
NOTE_TYPE = ('<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe">'
             '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>')


def _xshape(sid, row, col, kind="Note"):
    typ = "#_x0000_t202" if kind == "Note" else "#_x0000_t201"
    return (f'<v:shape id="_x0000_s{sid}" type="{typ}" style="position:absolute;margin-left:80pt;margin-top:2pt;'
            'width:108pt;height:59.25pt;z-index:1;visibility:hidden" fillcolor="infoBackground [80]" '
            'o:insetmode="auto"><v:fill color2="infoBackground [80]"/><v:textbox style="mso-direction-alt:auto">'
            f'<div style="text-align:left"></div></v:textbox><x:ClientData ObjectType="{kind}">'
            f"<x:MoveWithCells/><x:SizeWithCells/><x:Anchor>2, 15, {row}, 2, 4, 15, {row + 4}, 16</x:Anchor>"
            f"<x:AutoFill>False</x:AutoFill><x:Row>{row}</x:Row><x:Column>{col}</x:Column></x:ClientData></v:shape>")


XCOMMENTS = [
    '<comment ref="B2" authorId="0" shapeId="0" xr:uid="{0A1B2C3D-0000-0000-0000-000000000001}"><text><r><rPr><b/>'
    '<sz val="10"/><rFont val="Tahoma"/></rPr><t>Analyst:</t></r><r><rPr><sz val="10"/><rFont val="Tahoma"/></rPr>'
    '<t xml:space="preserve">&#10;typed from the release</t></r></text></comment>',
    '<comment ref="B3" authorId="1" shapeId="0" xr:uid="{0A1B2C3D-0000-0000-0000-000000000002}"><text><r><rPr>'
    '<sz val="10"/></rPr><t>my call</t></r></text></comment>',
    '<comment ref="B8" authorId="0" shapeId="0"><text><t>old after-print note</t></text></comment>']
XSHAPES = [_xshape(1025, 1, 1), _xshape(1026, 2, 1), _xshape(1027, 4, 3, "Button"), _xshape(1028, 7, 1)]


def _excel_book(tmp_path, notes=True):
    """An Earnings tab the way Excel saves it: shared strings, row spans, an o:idmap VML with note shapes and a
    form-control button, and comments by two authors with rich text and xr:uid. Band 9 already sits at row 7."""
    src = str(tmp_path / "x.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Earnings"
    for ref, v in {"A1": "1. PRINT SNAPSHOT AND THE CALL", "A2": "Price", "B2": 51, "A3": "Stance (rule)",
                   "B3": "hold", "A7": "9. ACTUAL VS FROZEN", "B8": "old"}.items():
        ws[ref] = v
    wb.save(src)
    pkg = Package(src)
    p = et.part(pkg)
    x = re.sub(r'<row r="(\d+)"', r'<row r="\1" spans="1:2"', pkg.text(p))
    sst = []

    def shared(m):                      # openpyxl writes inline strings; Excel writes shared ones
        sst.append(m.group(2))
        return f'<c r="{m.group(1)}" t="s"><v>{len(sst) - 1}</v></c>'
    x = re.sub(r'<c r="([A-Z]+\d+)" t="inlineStr"><is><t>(.*?)</t></is></c>', shared, x)
    pkg.put("xl/sharedStrings.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://'
            f'schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(sst)}" uniqueCount="{len(sst)}">'
            + "".join(f"<si><t>{s}</t></si>" for s in sst) + "</sst>")
    pkg.attach("xl/workbook.xml", "sheet", "xl/sharedStrings.xml",
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
    rels = pkg.rels("xl/_rels/workbook.xml.rels")
    rels = {k: (t.replace("/worksheet", "/sharedStrings") if g == "sharedStrings.xml" else t, g)
            for k, (t, g) in rels.items()}
    pkg.write_rels("xl/_rels/workbook.xml.rels", rels)
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    pkg.put("xl/drawings/vmlDrawing1.vml", VML_HEAD + (NOTE_TYPE if notes else "")
            + "".join(XSHAPES if notes else XSHAPES[2:3]) + "</xml>")
    rid = pkg.attach(p, "vml", "xl/drawings/vmlDrawing1.vml")
    if notes:
        pkg.put("xl/comments1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="xr" '
                'xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"><authors>'
                '<author>Analyst</author><author>Reviewer</author></authors><commentList>'
                + "".join(XCOMMENTS) + "</commentList></comments>")
        pkg.attach(p, "comments", "xl/comments1.xml", CT["comments"])
    x = x.replace("</worksheet>", f'<legacyDrawing xmlns:r="{NS_REL}" r:id="{rid}"/></worksheet>')
    pkg.put(p, x)
    pkg.save(src)
    return src


def test_splice_keeps_an_excel_tabs_notes_and_shapes_byte_for_byte(tmp_path):
    """The user's own notes (their authors, bold runs, xr:uid) and form controls are theirs: kept exactly; only
    the old after-print note on row 8 goes, and the new note is filed under Claude without reusing a shape id."""
    src = _excel_book(tmp_path)
    old_sheet = zipfile.ZipFile(src).read("xl/worksheets/sheet1.xml").decode()
    out = _splice(src, str(tmp_path / "o.xlsx"), 7, {"A7": "9. ACTUAL VS FROZEN"}, {"B8": "new note"})
    z = zipfile.ZipFile(out)
    cx, vml = z.read("xl/comments1.xml").decode(), z.read("xl/drawings/vmlDrawing1.vml").decode()
    assert XCOMMENTS[0] in cx and XCOMMENTS[1] in cx and "old after-print note" not in cx
    assert "<author>Analyst</author><author>Reviewer</author><author>Claude</author>" in cx
    assert re.search(r'<comment ref="B8" authorId="2">', cx)
    assert all(s in vml for s in XSHAPES[:3]) and XSHAPES[3] not in vml
    ids = re.findall(r'id="_x0000_s(\d+)"', vml)
    assert len(ids) == len(set(ids)) == 4
    assert _kept(z.read("xl/worksheets/sheet1.xml").decode(), 7) == _kept(old_sheet, 7)
    ws = openpyxl.load_workbook(out)["Earnings"]
    assert "typed from the release" in ws["B2"].comment.text and ws["B8"].comment.text == "new note"
    assert ws["B2"].value == 51 and ws["A3"].value == "Stance (rule)"


def test_a_tab_with_only_form_controls_keeps_its_one_legacy_drawing(tmp_path):
    """A sheet may hold one legacyDrawing: notes join the VML the buttons already use instead of a second one."""
    src = _excel_book(tmp_path, notes=False)
    out = _splice(src, str(tmp_path / "o.xlsx"), 7, {"A7": "9. ACTUAL VS FROZEN"}, {"B8": "new note"})
    z = zipfile.ZipFile(out)
    sheet, vml = z.read("xl/worksheets/sheet1.xml").decode(), z.read("xl/drawings/vmlDrawing1.vml").decode()
    assert sheet.count("<legacyDrawing ") == 1 and XSHAPES[2] in vml
    assert not any(n.endswith(".vml") and n != "xl/drawings/vmlDrawing1.vml" for n in z.namelist())
    assert openpyxl.load_workbook(out)["Earnings"]["B8"].comment.text == "new note"


def test_new_shape_ids_avoid_every_other_drawing(tmp_path):
    """Two VML drawings sharing an id block make Excel repair the file, so a taken block is skipped and added."""
    src = _excel_book(tmp_path)
    pkg = Package(src)
    pkg.put("xl/drawings/vmlDrawing9.vml", VML_HEAD + _xshape(1029, 0, 0, "Button") + "</xml>")
    vml = et._vml(pkg, "xl/drawings/vmlDrawing1.vml", 7, ["B8"])
    assert 'data="1,2"' in vml and 'id="_x0000_s2049"' in vml


def test_comment_text_reader_handles_excel_runs():
    """Guard messages quote the user's notes; empty runs, line breaks and phonetic hints must not garble them."""
    cx = ('<comments><commentList><comment ref="B10" authorId="0"><text><r><t>a</t></r><r><t xml:space="preserve"/>'
          '</r><r><t xml:space="preserve">&#10;b &amp; c</t></r></text></comment><comment ref="B13" authorId="0">'
          '<text><t>base</t><rPh sb="0" eb="1"><t>PHON</t></rPh></text></comment></commentList></comments>')
    assert et._comment_texts(cx) == {"B10": "a\nb & c", "B13": "base"}
