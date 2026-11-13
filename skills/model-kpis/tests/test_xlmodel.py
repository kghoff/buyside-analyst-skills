"""Row insert/delete must behave like Excel: a model whose links point at the wrong row shows wrong numbers silently."""
import os

import openpyxl
import pytest

from xlmodel import insert_rows, delete_rows, shift_formula


def two_tabs():
    wb = openpyxl.Workbook(); mod = wb.active; mod.title = "MOD"; an = wb.create_sheet("ANALYZED")
    mod["B40"] = "Revenue"; mod["C40"] = 100; mod["C41"] = "=C40*2"; mod["C42"] = "=MOD!C40"; mod["C43"] = "=SUM(C40:C41)"
    mod["C10"] = "=C40"; mod["C11"] = "=SUM(40:41)"
    an["C5"] = "=MOD!C40"; an["C6"] = "='MOD'!C40/MOD!$C$41"; an["C7"] = "=C5"; an["C8"] = '="MOD!C40"'
    return wb, mod, an


def test_insert_shifts_links_on_other_tabs():
    # the ANALYZED tab links into MOD; both claude.ai drafts left these pointing at the old rows
    wb, mod, an = two_tabs()
    insert_rows(mod, 31, 38)
    assert an["C5"].value == "=MOD!C78"
    assert an["C6"].value == "='MOD'!C78/MOD!$C$79"
    assert an["C7"].value == "=C5"                      # references to its own tab don't move
    assert an["C8"].value == '="MOD!C40"'               # text is not a reference


def test_insert_shifts_same_sheet_references_including_qualified_ones():
    wb, mod, an = two_tabs()
    insert_rows(mod, 31, 38)
    assert mod["C79"].value == "=C78*2"
    assert mod["C80"].value == "=MOD!C78"               # v2 missed 'MOD!' references on MOD itself
    assert mod["C81"].value == "=SUM(C78:C79)"
    assert mod["C10"].value == "=C78"                   # rows above the insert still follow their target
    assert mod["C11"].value == "=SUM(78:79)"            # whole-row range
    assert mod["B78"].value == "Revenue"


def test_delete_is_the_inverse_of_insert():
    wb, mod, an = two_tabs()
    before = {(s.title, c.coordinate): c.value for s in wb.worksheets for row in s.iter_rows() for c in row}
    insert_rows(mod, 31, 38); delete_rows(mod, 31, 38)
    after = {(s.title, c.coordinate): c.value for s in wb.worksheets for row in s.iter_rows() for c in row}
    assert {k: v for k, v in after.items() if v is not None} == {k: v for k, v in before.items() if v is not None}


def test_delete_refuses_when_another_tab_points_into_the_deleted_rows():
    # --replace deletes the old section; silently turning a link into #REF! would break the user's model
    wb = openpyxl.Workbook(); mod = wb.active; mod.title = "MOD"; an = wb.create_sheet("ANALYZED")
    mod["C40"] = 100; mod["C41"] = "=C40"; an["C5"] = "=MOD!C40"
    with pytest.raises(ValueError, match="ANALYZED!C5"):
        delete_rows(mod, 40, 2)


def test_freeze_panes_and_row_heights_move_with_their_rows():
    wb, mod, an = two_tabs()
    mod.freeze_panes = "C50"; mod.row_dimensions[45].height = 30
    insert_rows(mod, 31, 5)
    assert mod.freeze_panes == "C55" and mod.row_dimensions[50].height == 30


def test_shift_formula_leaves_other_sheets_alone():
    assert shift_formula("=Other!C40+C40", "MOD", 31, 2) == "=Other!C40+C42"
