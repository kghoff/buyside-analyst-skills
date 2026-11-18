import openpyxl

import move_rows as M
from modmap import ModMap
from test_modmap import _book


def test_rows_move_into_a_planned_section_the_model_does_not_have_yet(tmp_path):
    # move_rows runs before build.py, so a REVENUE BUILD the plan creates (driver_sections) must exist by the move;
    # a fresh model has none, and the move used to stop with "no section 'REVENUE BUILD'"
    src = _book(tmp_path)
    wb = openpyxl.load_workbook(src)
    ws = wb["MOD"]
    ws["A15"], ws["B16"], ws["B17"], ws["D16"], ws["D17"] = "KEY OPERATING METRICS", "Units", "Price", 5, 7
    wb.save(src)
    plan = {"driver_sections": [{"title": "REVENUE BUILD", "after": "KEY OPERATING METRICS"}],
            "move_rows": [{"from": "KEY OPERATING METRICS | Units", "through": "KEY OPERATING METRICS | Price",
                           "to": "REVENUE BUILD", "why": "x"}]}
    out, fn = M.move(src, plan, str(tmp_path / "o.xlsx"))
    m = ModMap(out)
    assert m.row("REVENUE BUILD | Units") < m.row("REVENUE BUILD | Price")
    w = openpyxl.load_workbook(out)["MOD"]
    assert w.cell(fn(16), 2).value == "Units" and w.cell(fn(16), 4).value == 5      # the row map follows the rows
    assert w.cell(fn(5), 2).value == "Revenue:"


def test_a_rerun_skips_a_move_that_is_already_done(tmp_path):
    # the forecast is rerun on the model it built: the rows already sit in REVENUE BUILD, and the move used to stop
    # with "no MOD row 'KEY OPERATING METRICS | Units'"
    src = _book(tmp_path)
    wb = openpyxl.load_workbook(src)
    ws = wb["MOD"]
    ws["A15"], ws["B16"], ws["B17"], ws["D16"], ws["D17"] = "KEY OPERATING METRICS", "Units", "Price", 5, 7
    wb.save(src)
    plan = {"driver_sections": [{"title": "REVENUE BUILD", "after": "KEY OPERATING METRICS"}],
            "move_rows": [{"from": "KEY OPERATING METRICS | Units", "through": "KEY OPERATING METRICS | Price",
                           "to": "REVENUE BUILD", "why": "x"}]}
    once, _ = M.move(src, plan, str(tmp_path / "o1.xlsx"))
    twice, fn = M.move(once, plan, str(tmp_path / "o2.xlsx"))
    a, b = ModMap(once), ModMap(twice)
    assert a.keys == b.keys and all(fn(r) == r for r in range(1, 30))
