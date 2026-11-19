"""SUM must be the first tab. Excel ties print areas (definedName localSheetId) and the open tab (activeTab) to a
sheet's POSITION, so inserting at 0 without shifting them silently moves a print area onto the wrong sheet, and a
rerun (remove SUM, add it again) must not drift the open tab one place right each time."""
import os
import sys

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from tabkit import move_first  # noqa: E402
from xlsx import Package, Styles  # noqa: E402


def _book(path):
    wb = openpyxl.Workbook()
    wb.active.title = "MOD"
    wb["MOD"].print_area = "A1:D10"
    wb.create_sheet("DCF")
    wb.create_sheet("Valuation")
    wb.active = 2                                    # the user left Valuation open
    wb.save(path)
    return path


def _add_sum(src, out):
    pkg = Package(src)
    if "SUM" in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet("SUM")
    pkg.add_sheet("SUM", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet '
                         'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
    move_first(pkg, "SUM")
    pkg.save(out)
    return out


def test_sum_first_keeps_print_area_and_open_tab(tmp_path):
    out = _add_sum(_book(str(tmp_path / "a.xlsx")), str(tmp_path / "b.xlsx"))
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["SUM", "MOD", "DCF", "Valuation"]
    assert wb["MOD"].print_area is not None          # still on MOD, not on SUM
    assert wb.active.title == "Valuation"


def test_rerun_does_not_drift(tmp_path):
    a = _add_sum(_book(str(tmp_path / "a.xlsx")), str(tmp_path / "b.xlsx"))
    b = _add_sum(a, str(tmp_path / "c.xlsx"))
    c = _add_sum(b, str(tmp_path / "d.xlsx"))
    wb = openpyxl.load_workbook(c)
    assert wb.sheetnames == ["SUM", "MOD", "DCF", "Valuation"]
    assert wb.active.title == "Valuation"
    assert wb["MOD"].print_area is not None


def test_dxf_fill_and_font():
    st = Styles('<styleSheet><cellStyles count="0"/></styleSheet>')
    k = st.dxf("FFC6EFCE", "FF006100")
    x = st.render()
    assert k == 0 and '<bgColor rgb="FFC6EFCE"/>' in x and '<color rgb="FF006100"/>' in x
