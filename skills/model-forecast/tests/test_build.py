import json
import re
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest
from openpyxl.comments import Comment
from openpyxl.styles import Font

import build as B
from modmap import ModMap
from test_modmap import LAB

FC = set("MNPQRST")            # forecast columns of the fixture: Q4 26E, 2026E, Q1-Q4 27E, 2027E
HIST = list("DEFGHJKL")        # history period columns


def _model(tmp_path, comment=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(LAB):
        ws.cell(2, 4 + k, v)
    ws["A4"], ws["B5"], ws["C5"], ws["B6"] = "INCOME STATEMENT", "Revenue:", "$ M", "% yoy"
    ws["B7"], ws["B8"] = "(-) R&D", "% of sales"
    for c, v in zip(HIST, [90, 95, 100, 110, 395, 105, 110, 120]):
        ws[f"{c}5"] = v
        ws[f"{c}5"].number_format = "#,##0.0"
        ws[f"{c}7"] = -v / 8
    ws["H8"] = "=-H7/H5"
    ws["H8"].number_format = "0.0%"
    ws["A10"], ws["B11"], ws["B12"] = "ASSETS:", "Cash & Equivalents", "Other Assets"
    ws["B13"], ws["H13"] = "Balance Check:", "=H11-H12"
    ws["P12"] = 7                              # the user's typed experiment in a forecast column
    ws["A15"], ws["B16"], ws["C16"] = "REVENUE BUILD", "Total units", "M"
    ws["A18"], ws["B19"] = "KEY OPERATING", "United States"
    for c, v in zip(HIST, [50, 52, 54, 60, 216, 58, 60, 66]):
        ws[f"{c}19"] = v
    ws["H19"].number_format = "#,##0.0"
    if comment:
        ws["H5"].comment = Comment("the user: FY25 from 10-K", "the user")
    p = tmp_path / "m.xlsx"
    wb.save(p)
    return str(p)


PLAN = {"ticker": "TEST",
        "new_rows": [{"key": "REVENUE BUILD | US revenue", "after": "REVENUE BUILD", "unit": "$ M",
                      "history": "KEY OPERATING | United States", "analysis": ["% yoy"]}],
        "rows": [
            {"key": "REVENUE BUILD | US revenue", "method": "seasonal", "kind": "flow",
             "annual_growth": {"2026E": 0.14, "2027E": 0.12}, "shares": {"Q1": 0.22, "Q2": 0.245, "Q3": 0.255, "Q4": 0.28},
             "source": "guide 12-13% [2026 Q3 release] & the filings research"},
            {"key": "INCOME STATEMENT | (-) R&D", "method": "pct_of", "kind": "flow", "of": "INCOME STATEMENT | Revenue:",
             "sign": -1, "rates": {"2026E": 0.125}, "source": "LRP opex 12-12.5% [Investor Day, S73]"}]}


def _cells(path):
    ws = openpyxl.load_workbook(path)["MOD"]
    return {(c.row, c.column_letter): c.value for row in ws.iter_rows() for c in row if c.value is not None}


def test_build_inserts_linked_rows_writes_the_plan_and_leaves_history_alone(tmp_path):
    src, out = _model(tmp_path), str(tmp_path / "out.xlsx")
    before = _cells(src)
    rep = B.build(src, PLAN, out)
    m = ModMap(out)
    # the new line sits at the end of REVENUE BUILD, under Total units, with its % yoy and the seasonality row
    r = m.row("REVENUE BUILD | US revenue")
    assert r == 17 and m.analysis("REVENUE BUILD | US revenue", "% yoy") == 18
    assert m.analysis("REVENUE BUILD | US revenue", "seasonality") == 19
    assert m.row("KEY OPERATING | United States") == 22
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws[f"C{r}"].value == "$ M"
    for c in HIST:                                          # history links to the source row, green
        assert ws[f"{c}{r}"].value == f"={c}22" and ws[f"{c}{r}"].font.color.rgb == "FF008000"
    assert ws["M20"].value is None                          # nothing left in the old position
    # Task 4's formulas are in place, styled by convention, with the row's number format
    assert ws["M7"].value == "=-M5*M8" and ws["N7"].value == "=SUM(J7:M7)"
    assert ws["M7"].font.color.rgb == "FF000000"
    assert ws["M8"].value == 0.125 and ws["M8"].font.color.rgb == "FF0000FF" and ws["M8"].number_format == "0.0%"
    assert ws[f"N{r}"].value == f"=H{r}*(1+N18)" and ws["N18"].value == 0.14 and ws["N18"].font.color.rgb == "FF0000FF"
    assert ws[f"P{r}"].value == f"=T{r}*P19" and ws["P19"].value == 0.22
    # typed inputs carry the source as a note; the user's existing note survives
    assert "LRP opex 12-12.5%" in ws["M8"].comment.text
    assert "2026 Q3 release" in ws["N18"].comment.text and "2026 Q3 release" in ws["M19"].comment.text
    assert ws["H5"].comment.text.startswith("the user: FY25")
    # nothing outside the forecast columns changed, apart from the inserted rows (17-19)
    after = _cells(out)
    moved = {((rr + 3 if rr >= 17 else rr), c): v for (rr, c), v in before.items()}
    for (rr, c), v in moved.items():
        if c not in FC:
            assert after.get((rr, c)) == v, (rr, c)
    for (rr, c), v in after.items():
        if c not in FC and rr not in (17, 18, 19):
            assert (rr, c) in moved, (rr, c)
    assert rep["rows_inserted"] and "P12" in rep["stale_cells"] and rep["cells_written"] > 0


def test_build_refuses_a_cell_outside_the_forecast_columns(tmp_path, monkeypatch):
    # history is the user's record: a plan (or a bug) that would overwrite it must stop the build, not write a file
    src, out = _model(tmp_path), tmp_path / "out.xlsx"
    real = B.cells_for
    monkeypatch.setattr(B, "cells_for", lambda m, e: {**real(m, e), "L5": ("n", 1.0, "blue")})
    with pytest.raises(ValueError, match="L5"):
        B.build(src, {"rows": [PLAN["rows"][1]]}, str(out))
    assert not out.exists()


def test_build_creates_a_comments_part_when_mod_has_none_and_the_cli_prints_the_report(tmp_path):
    src, out = _model(tmp_path, comment=False), tmp_path / "out.xlsx"
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"rows": [PLAN["rows"][1]]}))
    script = Path(__file__).parent.parent / "scripts" / "build.py"
    res = subprocess.run([sys.executable, str(script), "--model", src, "--plan", str(plan), "--out", str(out)],
                         capture_output=True, text=True, check=True)
    rep = json.loads(res.stdout)
    assert rep["rows_written"] == ["INCOME STATEMENT | (-) R&D"]
    ws = openpyxl.load_workbook(out)["MOD"]
    assert "S73" in ws["M8"].comment.text and ws["M8"].font.color.rgb == "FF0000FF"


def test_new_note_ids_stay_inside_the_drawings_listed_idmap_blocks():
    # Excel repairs (drops) notes whose shape id lies outside the VML's o:idmap blocks; block 3 is another drawing's
    vml = ('<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
           '<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="1"/></o:shapelayout>'
           '<v:shape id="_x0000_s2040"/></xml>')
    new, ids = B._alloc_ids(vml, 20, others={3})
    assert 'data="1,2"' in new and len(ids) == len(set(ids)) == 20
    assert all(i % 1024 and i // 1024 in (1, 2) for i in ids) and ids[0] == 2041
    new, ids = B._alloc_ids(vml, 20, others={2})        # block 2 taken elsewhere: skip to 3
    assert 'data="1,3"' in new and all(i // 1024 in (1, 3) and i % 1024 for i in ids)


def _rezip(src, dst, fix):
    import zipfile
    zi, zo = zipfile.ZipFile(src), zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    for i in zi.infolist():
        d = zi.read(i.filename)
        zo.writestr(i, fix(i.filename, d.decode()) if i.filename.endswith("sheet1.xml") else d)
    zo.close()


def test_replacing_a_shared_formula_master_keeps_its_children(tmp_path):
    # Excel stores fill-right formulas as one master + children; overwriting the master must not orphan the user's children
    src = _model(tmp_path)
    wb = openpyxl.load_workbook(src)
    wb["MOD"]["M7"], wb["MOD"]["M9"] = "=L7+1", "=L9+1"
    wb.save(src)
    shared = str(tmp_path / "shared.xlsx")
    _rezip(src, shared, lambda n, x: re.sub(r'<c r="M9"([^>]*)><f>L9\+1</f>(<v>[^<]*</v>|<v/>)?</c>',
                                            r'<c r="M9"\1><f t="shared" si="0"/></c>',
                                            re.sub(r'<c r="M7"([^>]*)><f>L7\+1</f>', r'<c r="M7"\1><f t="shared" ref="M7:M9" si="0">L7+1</f>', x)))
    assert 't="shared"' in __import__("zipfile").ZipFile(shared).read("xl/worksheets/sheet1.xml").decode()
    out = str(tmp_path / "out.xlsx")
    B.build(shared, {"rows": [PLAN["rows"][1]]}, out)
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws["M7"].value == "=-M5*M8" and ws["M9"].value == "=L9+1"


def test_users_notes_are_kept_and_plan_notes_are_replaced_on_rerun(tmp_path):
    # a note the user wrote is their research; only the build's own 'Plan: ' notes may be rewritten
    src = _model(tmp_path)
    wb = openpyxl.load_workbook(src)
    wb["MOD"]["M8"].comment = Comment("the user: my guess is 13%", "the user")
    wb.save(src)
    out1, out2 = str(tmp_path / "o1.xlsx"), str(tmp_path / "o2.xlsx")
    B.build(src, PLAN, out1)
    B.build(out1, PLAN, out2)
    # the notes drawing must stay well-formed XML (Excel drops every note otherwise) and a rerun adds no styles
    import zipfile
    import xlverify
    assert xlverify.bad_parts(out1) == [] and xlverify.bad_parts(out2) == []
    st = [zipfile.ZipFile(o).read("xl/styles.xml") for o in (out1, out2)]
    assert st[0] == st[1]
    ws = openpyxl.load_workbook(out2)["MOD"]
    t = ws["M8"].comment.text
    assert t.startswith("the user: my guess is 13%") and t.count("Plan: LRP opex") == 1
    assert ws["N18"].comment.text.startswith("Plan: guide") and ws["N18"].comment.text.count("Plan:") == 1


def test_number_format_comes_from_the_newest_history_cell(tmp_path):
    # The user reformats lines over time; the forecast should look like the latest year, not 2015
    src = _model(tmp_path)
    wb = openpyxl.load_workbook(src)
    wb["MOD"]["D8"] = 0.1
    wb["MOD"]["D8"].number_format = "0.00"
    wb["MOD"]["L8"] = 0.12
    wb["MOD"]["L8"].number_format = "0.0%"
    wb.save(src)
    out = str(tmp_path / "out.xlsx")
    B.build(src, {"rows": [PLAN["rows"][1]]}, out)
    assert openpyxl.load_workbook(out)["MOD"]["M8"].number_format == "0.0%"


FLAT_REV = {"key": "INCOME STATEMENT | Revenue:", "method": "flat", "kind": "flow", "source": "x"}


def test_analysis_rows_under_plan_lines_carry_the_users_history_formulas_forward(tmp_path):
    # The user reads % yoy / % of sales across the forecast like history; the build extends THEIR formulas, replaces their
    # typed experiments there, and never touches the plan's own driver cells
    src = _model(tmp_path)
    wb = openpyxl.load_workbook(src)
    ws = wb["MOD"]
    ws["L6"], ws["H6"], ws["P6"] = "=L5/F5-1", "=H5/100-1", 0.3
    wb.save(src)
    out = str(tmp_path / "out.xlsx")
    rep = B.build(src, {"rows": [FLAT_REV, PLAN["rows"][1]]}, out)
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws["M6"].value == "=M5/G5-1" and ws["P6"].value == "=P5/J5-1" and ws["N6"].value == "=N5/100-1"
    assert ws["N8"].value == "=-N7/N5" and ws["T8"].value == "=-T7/T5"        # FY from the last actual FY
    assert ws["M8"].value == 0.125                                           # plan driver untouched
    assert ws["P6"].font.color.rgb == "FF000000"
    assert rep["replaced_stale"] == ["P6"] and rep["analysis_filled"] == 9    # row 6: 5 quarters + 2 FY; row 8: 2 FY
    assert "P6" not in rep["stale_cells"]


def test_analysis_cells_without_a_history_formula_are_left_and_reported(tmp_path):
    src = _model(tmp_path)
    wb = openpyxl.load_workbook(src)
    wb["MOD"]["L6"], wb["MOD"]["P6"] = 0.05, 0.3        # typed history, typed experiment
    wb.save(src)
    out = str(tmp_path / "out.xlsx")
    rep = B.build(src, {"rows": [FLAT_REV]}, out)
    assert openpyxl.load_workbook(out)["MOD"]["P6"].value == 0.3
    assert "P6" in rep["stale_cells"] and rep["replaced_stale"] == []


def test_a_new_row_without_history_stays_blank_in_the_past(tmp_path):
    """A driver row the company never reported (e.g. a calibration share) must not show fake zeros for past years."""
    import openpyxl as _o
    from test_modmap import _book as _b
    import build as B
    src = _b(tmp_path)
    plan = {"new_rows": [{"key": "INCOME STATEMENT | Share", "after": "INCOME STATEMENT", "unit": "%"}],
            "rows": [{"key": "INCOME STATEMENT | Share", "method": "annual", "kind": "annual",
                      "values": {"2026E": 0.5}, "source": "x"}]}
    out = str(tmp_path / "o.xlsx")
    B.build(src, plan, out)
    ws = _o.load_workbook(out)["MOD"]
    r = next(c.row for c in ws["B"] if c.value == "Share")
    assert ws.cell(r, 8).value is None                      # 2025 history column: blank, not a link
    assert ws[f"N{r}"].value == 0.5 and ws[f"N{r}"].number_format == "0.0%"


def test_an_unknown_plan_field_stops_the_build():
    """A starting value once sat on a field the build ignored: 2026 International customers came out 0.18M, not 1.28M,
    and every check still passed. Unknown fields now stop the build."""
    import build as B
    assert B.unknown_fields({"rows": [{"key": "k", "method": "annual", "kind": "annual", "values": {}, "start_value": 1}]})
    assert B.unknown_fields({"new_rows": [{"key": "k", "after": "S", "history_values": {"2025": 1.1}}]}) == []


def test_driver_section_is_created_styled_like_a_title_and_keep_rows_are_refused(tmp_path):
    import openpyxl as _o
    from openpyxl.styles import PatternFill
    from test_modmap import _book as _b
    import build as B
    import pytest as _p
    src = _b(tmp_path)
    wb = _o.load_workbook(src)
    ws = wb["MOD"]
    ws.insert_rows(4, 3)                          # room for a REVENUE BUILD section above the income statement
    ws["A4"], ws["B5"] = "REVENUE BUILD", "Units"
    for c in range(1, 23):
        ws.cell(4, c).fill = PatternFill("solid", fgColor="FF002060")
    wb.save(src)
    plan = {"driver_sections": [{"title": "COST DRIVERS", "after": "REVENUE BUILD"}],
            "new_rows": [{"key": "COST DRIVERS | Gross margin", "after": "COST DRIVERS", "unit": "%"}],
            "rows": [{"key": "COST DRIVERS | Gross margin", "method": "annual", "kind": "annual", "values": {"2026E": 0.6},
                      "source": "x"}]}
    out = str(tmp_path / "o.xlsx")
    B.build(src, plan, out)
    w = _o.load_workbook(out)["MOD"]
    t = next(c.row for c in w["A"] if c.value == "COST DRIVERS")
    assert w.cell(t, 4).fill.fgColor.rgb == "FF002060"           # title row styled like REVENUE BUILD's
    assert w.cell(t + 1, 2).value == "Gross margin" and w.cell(t + 1, 14).value == 0.6
    assert next(c.row for c in w["A"] if c.value == "INCOME STATEMENT") > t      # the section sits above the IS
    plan["keep"] = [{"key": "COST DRIVERS | Gross margin", "why": "the user's"}]
    with _p.raises(ValueError, match="keep"):
        B.build(out, plan, str(tmp_path / "o2.xlsx"))


def test_new_rows_under_a_section_title_do_not_copy_the_titles_style(tmp_path):
    """DXCM: 123 driver-row labels came out white bold on navy, copied from the section title above them."""
    import openpyxl as _o
    from openpyxl.styles import Font, PatternFill
    from test_modmap import _book as _b
    import build as B
    src = _b(tmp_path)
    wb = _o.load_workbook(src)
    ws = wb["MOD"]
    ws.insert_rows(4, 3)
    ws["A4"], ws["B5"] = "REVENUE BUILD", "Units"
    for c in range(1, 4):
        ws.cell(4, c).fill = PatternFill("solid", fgColor="FF002060")
        ws.cell(4, c).font = Font(color="FFFFFFFF", bold=True)
    wb.save(src)
    plan = {"driver_sections": [{"title": "COST DRIVERS", "after": "REVENUE BUILD"}],
            "new_rows": [{"key": "COST DRIVERS | Gross margin", "after": "COST DRIVERS", "unit": "%"}],
            "rows": [{"key": "COST DRIVERS | Gross margin", "method": "annual", "kind": "annual", "values": {"2026E": 0.6}, "source": "x"}]}
    out = str(tmp_path / "o.xlsx")
    B.build(src, plan, out)
    w = _o.load_workbook(out)["MOD"]
    r = next(c.row for c in w["B"] if c.value == "Gross margin")
    assert w.cell(r, 2).fill.fill_type is None and not w.cell(r, 2).font.b


def test_a_stated_format_survives_a_rerun(tmp_path):
    """DXCM 'SBC, % of revenue' read 0.0274 instead of 2.7%: on a rerun the row's own General style won over the
    plan's 0.0%. A format the plan states always applies (colour and fill kept)."""
    import openpyxl as _o
    from test_modmap import _book as _b
    import build as B
    src = _b(tmp_path)
    plan = {"new_rows": [{"key": "INCOME STATEMENT | R&D share", "after": "INCOME STATEMENT", "unit": "%"}],
            "rows": [{"key": "INCOME STATEMENT | R&D share", "method": "annual", "kind": "annual",
                      "values": {"2026E": 0.1}, "history_template": "-{INCOME STATEMENT | (-) R&D}/{INCOME STATEMENT | Revenue:}",
                      "source": "x"}]}
    o1, o2 = str(tmp_path / "o1.xlsx"), str(tmp_path / "o2.xlsx")
    B.build(src, plan, o1)
    wb = _o.load_workbook(o1)                               # the row's cells already carry General (as in DXCM)
    r = next(c.row for c in wb["MOD"]["B"] if c.value == "R&D share")
    for c in "HN":
        wb["MOD"][f"{c}{r}"].number_format = "General"
    wb.save(o1)
    B.build(o1, plan, o2)
    ws = _o.load_workbook(o2)["MOD"]
    assert ws[f"H{r}"].number_format == "0.0%" and ws[f"N{r}"].number_format == "0.0%"
