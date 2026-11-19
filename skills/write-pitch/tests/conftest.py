# skills/write-pitch/tests/conftest.py
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def tab_render(tmp_path_factory):
    """One LibreOffice run on a small two-tab workbook (a line chart on tab 2); shared by every slow test."""
    import openpyxl
    from openpyxl.chart import LineChart, Reference
    import render_tabs
    d = tmp_path_factory.mktemp("tabs_fx")
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Notes"
    ws1["A1"] = "Plain notes tab with no chart"
    ws2 = wb.create_sheet("Charts")
    ws2["A1"] = "Price history"
    for i in range(1, 21):
        ws2.cell(row=i + 1, column=1, value=i)
        ws2.cell(row=i + 1, column=2, value=i * i)
    ch = LineChart()
    ch.add_data(Reference(ws2, min_col=2, min_row=2, max_row=21))
    ws2.add_chart(ch, "D2")
    src = str(d / "T_model.xlsx")
    wb.save(src)
    out = str(d / "tabs")
    return out, render_tabs.render(src, out)
