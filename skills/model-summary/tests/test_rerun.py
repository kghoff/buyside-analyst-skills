"""write-pitch (or the user) owns the yellow cells: a rerun must keep a typed Buy price, Thesis Summary, band and an
Action typed over Valuation's verdict, and still rebuild every link."""
import os
import shutil

import openpyxl

import build
from conftest import no_fetch


def test_rerun_keeps_typed_cells(built, tmp_path):
    out1, _, work1 = built
    m = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(out1, m)
    wb = openpyxl.load_workbook(m)                    # a test copy, never a user's model
    ws = wb["SUM"]
    ws["C19"], ws["E21"], ws["C51"], ws["C3"] = 45.0, "Three reasons the Street is wrong.", 0.05, "Small Buy"
    wb.save(m)
    work = str(tmp_path / "w")
    shutil.copytree(work1, work)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    out2 = str(tmp_path / "out2.xlsx")
    rep = build.build(m, work, "TEST", out2, research_dir=str(tmp_path), fetch=no_fetch)
    s = openpyxl.load_workbook(out2)["SUM"]
    assert (s["C19"].value, s["E21"].value, s["C51"].value, s["C3"].value) == (
        45.0, "Three reasons the Street is wrong.", 0.05, "Small Buy")
    assert s["C3"].fill.fgColor.rgb == "FFFFFF00"                 # typed over: now a yellow input
    assert s["C39"].value == "=Valuation!$B$39"                   # links rebuilt
    assert set(rep["users_kept"]) == {"Buy price", "Thesis Summary", "Street variance band (±)", "Action"}
    assert rep["action_follows_valuation"] is False and any("Action holds" in x for x in rep["warnings"])


def test_untouched_rerun_keeps_the_action_link(built, tmp_path):
    out1, _, work1 = built
    m = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(out1, m)
    work = str(tmp_path / "w")
    shutil.copytree(work1, work)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    rep = build.build(m, work, "TEST", str(tmp_path / "o.xlsx"), research_dir=str(tmp_path), fetch=no_fetch)
    assert rep["users_kept"] == [] and rep["action_follows_valuation"] is True
    wb = openpyxl.load_workbook(str(tmp_path / "o.xlsx"))
    assert wb.sheetnames.count("SUM") == 1 and wb.sheetnames[0] == "SUM" and wb.active.title == "Valuation"
