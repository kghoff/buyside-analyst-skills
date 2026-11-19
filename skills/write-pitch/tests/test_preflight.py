import datetime
import json
import os
import pathlib
import subprocess
import sys

import openpyxl
PF = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "preflight.py"

def mk(tmp, tabs, files):
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    for t in tabs:
        ws = wb.create_sheet(t)
        if t == "MOD": ws["D2"], ws["E2"] = "2025", "2026E"
    m = tmp / "XYZ_model.xlsx"; wb.save(m)
    for f in files:
        p = tmp / "R" / f; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("# x\n")
    return m

def run(m, r):
    out = subprocess.run([sys.executable, str(PF), "--model", str(m), "--research", str(r), "--ticker", "XYZ"],
                         capture_output=True, text=True)
    return json.loads(out.stdout)

REQ = ["Filings Research/2026-11-09 XYZ Filings Research Report.md", "Street Research/2026-11-11 XYZ Street Research Report.md"]
ALL = ["MOD", "DCF", "Multiples", "Valuation", "SUM"]

def test_missing_valuation_stops_and_names_skill(tmp_path):
    m = mk(tmp_path, ["MOD", "DCF", "Multiples", "SUM"], REQ)
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and any("/model-valuation" in x["fix"] for x in j["missing"])

def test_all_present_first_mode(tmp_path):
    m = mk(tmp_path, ALL, REQ)
    j = run(m, tmp_path / "R")
    assert j["status"] == "ok" and j["mode"] == "first" and "Short Check" in j["optional_missing"]

def test_plate_file_means_rerun(tmp_path):
    m = mk(tmp_path, ALL, REQ + ["Pitch/_work/plate.md"])
    assert run(m, tmp_path / "R")["mode"] == "rerun"

def test_long_version_report_alone_is_not_present(tmp_path):
    long_only = ["Filings Research/2026-11-09 XYZ Filings Research Report (long version).md", REQ[1]]
    j = run(mk(tmp_path, ALL, long_only), tmp_path / "R")
    assert j["status"] == "stop" and any("/research-filings" in x["fix"] for x in j["missing"])

def test_mod_without_forecast_names_forecast(tmp_path):
    m = mk(tmp_path, ALL, REQ)
    wb = openpyxl.load_workbook(m); wb["MOD"]["E2"] = "2026"; wb.save(m)
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and any("/model-forecast" in x["fix"] for x in j["missing"])

def fresh(tmp, note_date):
    m = mk(tmp, ALL + ["Px Events"], REQ + [f"Valuation/{note_date} XYZ Valuation Note.md"])
    wb = openpyxl.load_workbook(m)
    wb["MOD"]["D2"], wb["MOD"]["E2"], wb["MOD"]["F2"] = "Q3 26", "Q4 26E", "2026E"
    ws = wb["Px Events"]
    ws["A3"], ws["B3"] = "Period", "Full-results release date"
    ws["A4"], ws["B4"] = "Q3 26", datetime.datetime(2026, 11, 5)
    wb.save(m)
    return m

def test_release_after_note_is_stale(tmp_path):
    j = run(fresh(tmp_path, "2026-11-01"), tmp_path / "R")
    assert j["status"] == "stop" and j["stale"]["quarter"] == "Q3 26"
    assert "rerun /model-valuation, then /model-summary" in j["stale"]["fix"]

def test_note_after_release_is_fresh(tmp_path):
    j = run(fresh(tmp_path, "2026-11-08"), tmp_path / "R")
    assert j["status"] == "ok" and j["stale"] is None

def test_unjudgeable_freshness_warns_not_stops(tmp_path):
    j = run(mk(tmp_path, ALL, REQ), tmp_path / "R")
    assert j["status"] == "ok" and j["stale"] is None and j["warnings"]

def test_summary_work_older_than_release_is_stale_even_with_fresh_note(tmp_path):
    m = fresh(tmp_path, "2026-11-08")
    f = tmp_path / "_model_work" / "model-summary" / "build.json"
    f.parent.mkdir(parents=True); f.write_text("{}")
    old = datetime.datetime(2026, 11, 2).timestamp()
    os.utime(f, (old, old))
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and j["stale"]["quarter"] == "Q3 26"

def test_newest_note_by_date_decides(tmp_path):
    m = fresh(tmp_path, "2026-11-01")
    (tmp_path / "R" / "Valuation" / "2026-11-08 XYZ Valuation Note.md").write_text("# x\n")
    j = run(m, tmp_path / "R")
    assert j["status"] == "ok" and j["stale"] is None


# why: the skill runs every script with python3 -I, which hides `pip install --user` packages; without this check the
# run would get through the agents (an hour of work) and die at the deck build on a missing python-pptx
def test_missing_package_stops_before_anything_else(tmp_path):
    import preflight
    m = mk(tmp_path, ALL, REQ)

    def importer(name):
        if name in ("pptx", "fitz"):
            raise ImportError(name)
    out = preflight.check("XYZ", str(m), str(tmp_path / "R"), importer)
    assert out["status"] == "stop"
    assert [x["what"] for x in out["missing"]] == ["python-pptx", "pymupdf"]
    fix = out["missing"][0]["fix"]
    assert fix.startswith("python3 -m pip install") and "python-pptx" in fix and "--user" not in fix
    assert preflight.check("XYZ", str(m), str(tmp_path / "R"), lambda n: None)["status"] == "ok"


# why: the same, end to end through the real import machinery: a package that won't import names itself
def test_hidden_package_cli(tmp_path):
    m = mk(tmp_path, ALL, REQ)
    code = ("import sys, runpy; sys.modules['docx'] = None; sys.argv = sys.argv[1:];"
            " runpy.run_path(sys.argv[0], run_name='__main__')")
    out = subprocess.run([sys.executable, "-c", code, str(PF), "--model", str(m), "--research", str(tmp_path / "R"),
                          "--ticker", "XYZ"], capture_output=True, text=True)
    res = json.loads(out.stdout)
    assert res["status"] == "stop" and [x["what"] for x in res["missing"]] == ["python-docx"]
