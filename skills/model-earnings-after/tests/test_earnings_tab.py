"""Bands 9-15 are appended under band 8 without touching bands 1-8: the preview is the user's record of what we
expected, and the wrap is only honest if that record is unchanged. A rerun replaces bands 9-15 only."""
import re
import zipfile

import openpyxl

import earnings_tab as et
from xlsx import Package, Sheet, Styles

ROW = r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)'


def _kept(xml, start):
    return [m.group(0) for m in re.finditer(ROW, xml, re.S) if int(m.group(1)) < start]


def _splice(src, out, start, cells, notes):
    pkg = Package(src)
    st = Styles(pkg.text("xl/styles.xml"))
    sh = Sheet()
    for ref, text in cells.items():
        sh.set(ref, "s", text, st.xf())
    et.splice(pkg, et.part(pkg), start, sh, notes)
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
