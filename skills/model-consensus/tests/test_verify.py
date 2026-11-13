import os
import shutil
import subprocess
import sys

import pytest

import build
import lo
from conftest import REFERENCE, snap_path

HERE = os.path.dirname(__file__)


@pytest.mark.skipif(lo.SOFFICE is None, reason="LibreOffice not installed")
def test_verify_passes_on_a_fresh_build(tmp_path):
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    shutil.copy(snap_path("DXCM"), w / "snapshots")
    out = str(w / "built.xlsx")
    build.build(REFERENCE, str(w), "DXCM", out)
    r = subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "verify.py"), "--before", REFERENCE,
                        "--built", out, "--work", str(w)], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout and os.path.exists(w / "consensus.png")


def test_same_treats_blank_and_na_as_empty():
    import verify
    assert verify.same(None, None) and verify.same(None, "") and verify.same(None, "#N/A")
    assert verify.same(1.0, 1.0 + 1e-12) and not verify.same(1.0, 1.1) and not verify.same(1.0, None)


def test_dates_compare_as_excel_serials():
    import datetime
    import verify
    assert verify.serial(datetime.datetime(1900, 1, 1)) == 2.0
    assert verify.serial(datetime.datetime(2026, 1, 1, 12)) == 46023.5
    assert verify.serial(datetime.date(2026, 1, 1)) == 46023
    assert verify.same(46023.0, verify.serial(datetime.datetime(2026, 1, 1)))


# ---- final review 5: verify reads the built sheet itself for notes and colours, not build's own bookkeeping
import json  # noqa: E402

import openpyxl  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

import verify  # noqa: E402


def _built(tmp_path):
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    shutil.copy(snap_path("DXCM"), w / "snapshots")
    out = str(w / "built.xlsx")
    build.build(REFERENCE, str(w), "DXCM", out)
    return out, json.load(open(w / "layout.json"))


def test_scan_passes_a_fresh_build(tmp_path):
    out, L = _built(tmp_path)
    assert L["header_noted"] and L["user"]
    r = verify.scan(out, L)
    assert r == {"no_note": [], "colour": []}


def test_scan_catches_a_missing_note_and_wrong_colours(tmp_path):
    out, L = _built(tmp_path)
    wb = openpyxl.load_workbook(out)
    ws = wb[build.TAB]
    ws["F3"].comment = None                                               # the price, typed, now unexplained
    ws["Z2"] = 42                                                         # a stray typed number: no note, black
    ws["Z3"] = "=1+1"; ws["Z3"].font = Font(color="FF0000FF")              # a formula dressed as an input
    vb = L["variance_band"]
    ws.cell(vb + 2, 3).value = 5800                                       # the user's own input: exempt
    p = str(tmp_path / "edited.xlsx")
    wb.save(p)                                                            # a test copy, never the user's file
    r = verify.scan(p, L)
    assert "F3" in r["no_note"] and "Z2" in r["no_note"]
    assert any(x.startswith("Z2") for x in r["colour"]) and any(x.startswith("Z3") for x in r["colour"])
    assert f"C{vb + 2}" not in r["no_note"] and not any(x.startswith(f"C{vb + 2} ") for x in r["colour"])


def test_in_ranges():
    assert verify.in_ranges("B5", ["A1:C9"]) and not verify.in_ranges("D5", ["A1:C9"])
    assert verify.in_ranges("T120", ["T10:T1300"]) and not verify.in_ranges("T9", ["T10:T1300"])
