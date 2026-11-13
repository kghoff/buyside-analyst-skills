"""modfill: The user's MOD fill convention (quarters plain, years grey, section title rows in their colour; a year column
with no quarters, like 2050E, left alone). The user kept re-colouring cells by hand after agents wrote MOD; every MOD-writing
skill now runs fix at the end of its build and fails its check on any break."""
import os
import sys
import zipfile

import openpyxl
from openpyxl.styles import PatternFill

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import modfill  # noqa: E402

GREY = PatternFill("solid", fgColor="FFD9D9D9")
NAVY = PatternFill("solid", fgColor="FF002060")
BSGREY = PatternFill("solid", fgColor="FFBFBFBF")
HDR = ["Q1 24", "Q2 24", "Q3 24", "Q4 24", 2024, None, "Q1 25", "Q2 25", "Q3 25", "Q4 25", 2025, None,
       "Q1 26", "Q2 26E", "Q3 26E", "Q4 26E", "2026E", None, "2050E"]


def _model(tmp_path, breaks=True, drop_row8=False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(HDR):
        ws.cell(2, 4 + k, v)
    cols = {v: 4 + k for k, v in enumerate(HDR) if v is not None}
    qs = [c for v, c in cols.items() if str(v).startswith("Q")]
    ys = [cols[2024], cols[2025], cols["2026E"]]
    ws["A4"], ws["A9"] = "INCOME STATEMENT", "BALANCE SHEET"
    for r, fill in ((4, NAVY), (9, BSGREY)):
        for c in qs + ys:
            ws.cell(r, c).fill = fill
    for r in (5, 6, 7, 10, 11):
        ws.cell(r, 2, f"line {r}")
        for c in qs:
            ws.cell(r, c, 1.0)
        for c in ys:
            ws.cell(r, c, 4.0).fill = GREY
    if not drop_row8:                                    # a blank spacer row: the year column is still grey
        for c in ys:
            ws.cell(8, c).fill = GREY
    ws.cell(5, cols["2050E"], 9.0)                       # a plain terminal column
    if breaks:
        ws.cell(5, cols["Q2 26E"]).fill = GREY           # a forecast quarter turned grey
        ws.cell(6, cols["2026E"]).fill = PatternFill()   # a forecast year lost its grey
        ws.cell(9, cols["2026E"]).fill = PatternFill()   # a section title row with a hole
    p = str(tmp_path / "m.xlsx")
    wb.save(p)
    return p, cols


def test_clean_model_passes(tmp_path):
    p, _ = _model(tmp_path, breaks=False)
    assert modfill.check(p) == []


def test_check_finds_each_kind_of_break(tmp_path):
    p, cols = _model(tmp_path)
    L = openpyxl.utils.get_column_letter
    bad = {ref for ref, _, _ in modfill.check(p)}
    assert bad == {f"{L(cols['Q2 26E'])}5", f"{L(cols['2026E'])}6", f"{L(cols['2026E'])}9"}


def test_fix_restores_the_convention_and_touches_nothing_else(tmp_path):
    p, cols = _model(tmp_path)
    out = str(tmp_path / "o.xlsx")
    assert modfill.fix(p, out) == 3
    assert modfill.check(out) == []
    a, b = openpyxl.load_workbook(p)["MOD"], openpyxl.load_workbook(out)["MOD"]
    assert all(a[c.coordinate].value == c.value for row in b.iter_rows() for c in row)
    assert b.cell(5, cols["2050E"]).fill.fill_type is None           # 2050E (no quarters) is left alone
    za, zb = zipfile.ZipFile(p), zipfile.ZipFile(out)
    assert za.namelist() == zb.namelist()
    assert sorted(n for n in za.namelist() if za.read(n) != zb.read(n)) == ["xl/styles.xml", "xl/worksheets/sheet1.xml"]


def test_fix_fills_a_blank_year_cell_in_a_blank_row(tmp_path):
    """the house template greys the year column even on blank spacer rows."""
    p, cols = _model(tmp_path, breaks=False, drop_row8=True)      # row 8: no cells at all
    out = str(tmp_path / "o.xlsx")
    assert modfill.fix(p, out) == 3                      # 2024, 2025, 2026E of row 8
    assert modfill.check(out) == []


def test_a_model_without_the_convention_is_left_alone(tmp_path):
    """If most year cells are plain (a model never shaded), fix must not strip the few shaded ones: no majority of
    wrong cells is ever spread."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for k, v in enumerate(HDR):
        ws.cell(2, 4 + k, v)
    ws["A4"] = "INCOME STATEMENT"
    for r in (5, 6, 7):
        ws.cell(r, 8, 1.0)
    ws.cell(5, 8).fill = GREY
    p = str(tmp_path / "plain.xlsx")
    wb.save(p)
    assert modfill.check(p) == [] and modfill.fix(p, str(tmp_path / "o.xlsx")) == 0


def test_a_coloured_label_on_an_ordinary_row_breaks_the_convention(tmp_path):
    """DXCM: driver-row labels came out navy like a section title."""
    p, cols = _model(tmp_path, breaks=False)
    wb = openpyxl.load_workbook(p)
    wb["MOD"]["B6"].fill = NAVY
    wb.save(p)
    assert [ref for ref, _, _ in modfill.check(p)] == ["B6"]
