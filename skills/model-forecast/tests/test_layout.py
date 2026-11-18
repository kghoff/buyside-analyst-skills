"""layout: The user reads column B to follow the forecast's logic. A flat list of driver rows was "not very intuitive", so
the plan groups each driver section and the script moves the rows into those groups and formats them their way (group
name plain, inputs indented, working steps italic, the result bold, a blank row between groups), with every formula
following the rows it reads."""
import openpyxl
import pytest

import layout

SEC = "COST BRIDGE"


def _model(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, p in enumerate(["2025", "2026E"]):
        ws.cell(2, 4 + k, p)
    ws["A4"] = SEC
    rows = [("Units", 10, 11), ("Price check", 5, "=E5"), ("Cost per unit", 2, 2.1),
            ("Total cost", "=D5*D7", "=E5*E7"), ("Guide, low", 1, 1)]
    for i, (lab, h, f) in enumerate(rows, start=5):
        ws.cell(i, 2, lab)
        ws.cell(i, 4, h)
        ws.cell(i, 5, f)
    ws["A11"] = "INCOME STATEMENT"
    ws["B12"] = "Cost of sales"
    ws["E12"] = "=E8"
    other = wb.create_sheet("Charts")
    other["A1"] = "=MOD!E8"
    p = str(tmp_path / "m.xlsx")
    wb.save(p)
    return p


def _plan():
    k = lambda lab: f"{SEC} | {lab}"
    return {"layout": [{"section": SEC, "groups": [
        {"title": "Cost of the units", "rows": [k("Units"), k("Cost per unit"), k("Price check"), k("Total cost")],
         "result": k("Total cost"), "note": "What it is: what the units cost.\nUp / down: higher cost, lower margin."},
        {"title": "References", "rows": [k("Guide, low")], "result": None, "reference": True}]}]}


def test_rows_regroup_and_every_formula_follows(tmp_path):
    p, out = _model(tmp_path), str(tmp_path / "o.xlsx")
    layout.layout(p, _plan(), out)
    ws = openpyxl.load_workbook(out)["MOD"]
    labels = [ws.cell(r, 2).value for r in range(5, 14)]
    assert labels == ["Cost of the units", "Units", "Cost per unit", "Price check", "Total cost", None,
                      "References", "Guide, low", None]
    tot = labels.index("Total cost") + 5
    assert ws.cell(tot, 5).value == f"=E{labels.index('Units') + 5}*E{labels.index('Cost per unit') + 5}"
    assert ws["E15"].value == f"=E{tot}"                         # the statement row, shifted down two rows
    assert openpyxl.load_workbook(out)["Charts"]["A1"].value == f"=MOD!E{tot}"


def test_the_look_follows_the_house_rules(tmp_path):
    p, out = _model(tmp_path), str(tmp_path / "o.xlsx")
    layout.layout(p, _plan(), out)
    ws = openpyxl.load_workbook(out)["MOD"]
    look = lambda r: (bool(ws.cell(r, 2).font.b), bool(ws.cell(r, 2).font.i), int(ws.cell(r, 2).alignment.indent or 0))
    assert look(5) == (False, False, 0)          # group name
    assert look(6) == (False, False, 1)          # Units: a typed forecast number = an input
    assert look(8) == (False, True, 2)           # Price check: all formulas = a working step
    assert look(9) == (True, False, 0)           # Total cost: the result, last and bold
    assert ws.cell(9, 5).font.b                  # its numbers bold too
    assert look(12) == (False, True, 1)          # a reference row


def test_rerun_rebuilds_the_same_layout(tmp_path):
    p, o1, o2 = _model(tmp_path), str(tmp_path / "o1.xlsx"), str(tmp_path / "o2.xlsx")
    layout.layout(p, _plan(), o1)
    layout.layout(o1, _plan(), o2)
    with open(o1, "rb") as a, open(o2, "rb") as b:
        assert a.read() == b.read()


def test_a_result_that_is_not_last_stops_the_layout(tmp_path):
    """The result is the last row computed; a result above the rows it is built from would read upside down."""
    p = _model(tmp_path)
    plan = _plan()
    g = plan["layout"][0]["groups"][0]
    g["rows"] = [g["rows"][-1]] + g["rows"][:-1]
    with pytest.raises(ValueError, match="is not its last row"):
        layout.layout(p, plan, str(tmp_path / "o.xlsx"))


def test_a_row_left_out_stops_the_layout(tmp_path):
    p = _model(tmp_path)
    plan = _plan()
    plan["layout"][0]["groups"][1]["rows"] = []
    with pytest.raises(ValueError, match="Guide, low' is in no group"):
        layout.layout(p, plan, str(tmp_path / "o.xlsx"))


def test_a_stale_calc_chain_is_dropped(tmp_path):
    """Excel 'repaired' the user's model after the first layout: calcChain.xml still named the cells' old places. Every
    row move drops it (Excel rebuilds it on open, nothing lost)."""
    import zipfile
    p = _model(tmp_path)
    with zipfile.ZipFile(p) as z:
        data = {n: z.read(n) for n in z.namelist()}
    data["xl/calcChain.xml"] = b'<?xml version="1.0"?><calcChain xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><c r="E8" i="1"/></calcChain>'
    data["[Content_Types].xml"] = data["[Content_Types].xml"].replace(b"</Types>", b'<Override PartName="/xl/calcChain.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml"/></Types>')
    data["xl/_rels/workbook.xml.rels"] = data["xl/_rels/workbook.xml.rels"].replace(b"</Relationships>", b'<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain" Target="calcChain.xml"/></Relationships>')
    with zipfile.ZipFile(p, "w") as z:
        for n, b in data.items():
            z.writestr(n, b)
    out = str(tmp_path / "o.xlsx")
    layout.layout(p, _plan(), out)
    with zipfile.ZipFile(out) as z:
        assert "xl/calcChain.xml" not in z.namelist()
        assert b"calcChain" not in z.read("xl/_rels/workbook.xml.rels") + z.read("[Content_Types].xml")


def _notes(path):
    import re
    import zipfile
    with zipfile.ZipFile(path) as z:
        cx = next(z.read(n).decode() for n in z.namelist() if re.match(r"xl/comments\d*\.xml", n))
        vml = next(z.read(n).decode() for n in z.namelist() if n.endswith(".vml"))
    return dict(re.findall(r'<comment ref="([A-Z]+\d+)".*?<t[^>]*>([^<]*)</t>', cx, re.S)), vml


def test_each_group_explains_itself_on_its_bold_row(tmp_path):
    """Rule: a note on each bold line saying what it is, how it feeds the statements, and what up or down
    means for the business. No result row: the note goes on the group name."""
    p, out = _model(tmp_path), str(tmp_path / "o.xlsx")
    plan = _plan()
    plan["layout"][0]["groups"].insert(1, {"title": "Prices", "rows": [], "result": None, "note": "Prices: why."})
    plan["layout"][0]["groups"][0]["rows"].remove(f"{SEC} | Price check")
    plan["layout"][0]["groups"][1]["rows"] = [f"{SEC} | Price check"]
    layout.layout(p, plan, out)
    notes, vml = _notes(out)
    assert notes["B8"].startswith(layout.GUIDE_NOTE + "What it is")      # Total cost, the bold result
    assert notes["B10"] == layout.GUIDE_NOTE + "Prices: why."            # the group name
    import re
    a = [int(x) for x in re.search(r"<x:Anchor>([^<]*)", vml).group(1).replace(",", " ").split()]
    assert a[0] >= 2 and a[6] - a[2] >= 4                                # right of B, tall enough for the text


def test_a_rerun_rewrites_the_notes_instead_of_stacking_them(tmp_path):
    p, o1, o2 = _model(tmp_path), str(tmp_path / "o1.xlsx"), str(tmp_path / "o2.xlsx")
    layout.layout(p, _plan(), o1)
    layout.layout(o1, _plan(), o2)
    notes, _ = _notes(o2)
    assert list(notes.values()).count(layout.GUIDE_NOTE + "What it is: what the units cost.\nUp / down: higher cost, lower margin.") <= 1
    assert sum(layout.GUIDE_NOTE in v for v in notes.values()) == 1


def test_a_group_without_a_note_stops_the_layout(tmp_path):
    p = _model(tmp_path)
    plan = _plan()
    del plan["layout"][0]["groups"][0]["note"]
    with pytest.raises(ValueError, match="has no note"):
        layout.layout(p, plan, str(tmp_path / "o.xlsx"))


def test_a_group_named_like_its_own_line_survives_a_rerun(tmp_path):
    # ABT 2026-11: group "Total cost" over the line "Total cost". After one layout the empty group-name row came first,
    # took the line's key, and the line became "Total cost #2": the rerun stopped ("in no group") and build.py would
    # have written the line's forecast into the empty group-name row
    from modmap import ModMap
    plan = _plan()
    plan["layout"][0]["groups"][0]["title"] = "Total cost"
    p, o1, o2 = _model(tmp_path), str(tmp_path / "o1.xlsx"), str(tmp_path / "o2.xlsx")
    layout.layout(p, plan, o1)
    r = ModMap(o1).row(f"{SEC} | Total cost")
    assert openpyxl.load_workbook(o1)["MOD"].cell(r, 5).value is not None     # the key is the line, not the group name
    layout.layout(o1, plan, o2)
    ws = openpyxl.load_workbook(o2)["MOD"]
    assert [ws.cell(r, 2).value for r in range(5, 10)] == ["Total cost", "Units", "Cost per unit", "Price check", "Total cost"]
