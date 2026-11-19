import openpyxl, json, subprocess, sys, pathlib, datetime
from conftest import FIX
PF = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "preflight.py"

def mk(tmp, tabs, files):
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    for t in tabs:
        ws = wb.create_sheet(t)
        if t == "MOD": ws["C2"], ws["D2"] = "FY 25", "FY 26E"
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
    wb = openpyxl.load_workbook(m); wb["MOD"]["D2"] = "FY 26"; wb.save(m)
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and any("/model-forecast" in x["fix"] for x in j["missing"])

def fresh(tmp, note_date):
    m = mk(tmp, ALL + ["Px Events"], REQ + [f"Valuation/{note_date} XYZ Valuation Note.md"])
    wb = openpyxl.load_workbook(m)
    wb["MOD"]["E2"], wb["MOD"]["F2"] = "Q3 26", "Q4 26E"
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
