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
    summary_record(tmp_path, datetime.datetime(2026, 11, 2))
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and j["stale"]["quarter"] == "Q3 26"


def summary_record(tmp, when, name="inputs_written.json"):
    """A model-summary work file dated `when`. inputs_written.json is the one copyover.py promotes only after the
    built SUM was copied over the model, so it dates the last successful /model-summary."""
    f = tmp / "_model_work" / "model-summary" / name
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text("{}")
    os.utime(f, (when.timestamp(), when.timestamp()))
    return f


# why: an aborted /model-summary run (built, never copied over) leaves fresh work files; dating SUM by the newest of
# any file would call an old SUM fresh and the pitch would quote last quarter's cap table and targets
def test_aborted_summary_run_does_not_count_as_fresh(tmp_path):
    m = fresh(tmp_path, "2026-11-08")
    summary_record(tmp_path, datetime.datetime(2026, 11, 2))
    summary_record(tmp_path, datetime.datetime(2026, 11, 9), "layout.json")
    summary_record(tmp_path, datetime.datetime(2026, 11, 9), "inputs_written.next.json")
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and j["stale"]["quarter"] == "Q3 26"


def test_summary_copied_after_release_is_fresh(tmp_path):
    m = fresh(tmp_path, "2026-11-08")
    summary_record(tmp_path, datetime.datetime(2026, 11, 9))
    j = run(m, tmp_path / "R")
    assert j["status"] == "ok" and j["stale"] is None


# why: work files but no copy-over record means /model-summary never finished here; say so rather than guess
def test_summary_work_without_record_warns(tmp_path):
    m = fresh(tmp_path, "2026-11-08")
    summary_record(tmp_path, datetime.datetime(2026, 11, 9), "layout.json")
    j = run(m, tmp_path / "R")
    assert j["stale"] is None and any("inputs_written.json" in w for w in j["warnings"])


def with_event(m, period, day):
    """Add an earnings event row to Px Events' event block (model-price-history names it '<period> earnings')."""
    wb = openpyxl.load_workbook(m)
    ws = wb["Px Events"]
    ws["D3"], ws["E3"], ws["F3"] = "Event date", "Type", "Event"
    ws["D4"], ws["E4"], ws["F4"] = datetime.datetime(2026, 11, 5), "Earnings", "Q3 26 earnings"
    ws["D5"], ws["E5"], ws["F5"] = day, "Earnings", f"{period} earnings"
    wb.save(m)
    return m


# why: a quarter the company has already reported but MOD still shows as a forecast means every number in the pitch
# (actuals, estimates, valuation) is a quarter old; the valuation note can still look fresh against MOD's own quarter
def test_reported_quarter_missing_from_mod_stops(tmp_path):
    m = with_event(fresh(tmp_path, "2026-11-08"), "Q4 26", datetime.datetime(2026, 11, 12))
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and j["stale"]["quarter"] == "Q4 26"
    assert j["stale"]["fix"] == "run /model-update, then /model-valuation and /model-summary"


def test_scheduled_release_after_today_does_not_stop(tmp_path):
    m = with_event(fresh(tmp_path, "2026-11-08"), "Q4 26", datetime.datetime(2099, 2, 1))
    j = run(m, tmp_path / "R")
    assert j["status"] == "ok" and j["stale"] is None

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


def stale_dimension(m, ref="A1:B2"):
    """Rewrite every sheet's <dimension> to a range that cuts rows and columns off (Excel and other writers can leave
    one stale; read-only openpyxl trusts it)."""
    import re
    import shutil
    import zipfile
    tmp = m.with_suffix(".tmp")
    with zipfile.ZipFile(m) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet"):
                data = re.sub(rb'<dimension ref="[^"]*"/>', f'<dimension ref="{ref}"/>'.encode(), data)
            zout.writestr(item, data)
    shutil.move(tmp, m)


# why: a stale <dimension> hid MOD's period headers from column D on, so a model with a forecast was told to run
# /model-forecast, and the user would rerun a skill for nothing
def test_stale_dimension_does_not_hide_mod_headers(tmp_path):
    m = mk(tmp_path, ALL, REQ)
    stale_dimension(m)
    j = run(m, tmp_path / "R")
    assert j["status"] == "ok", j["missing"]


# why: the same cut hid Px Events' release rows, so a quarter reported after the last valuation note slipped through
# as "freshness not checked" and the pitch was built on a stale valuation
def test_stale_dimension_does_not_hide_the_newest_release(tmp_path):
    m = fresh(tmp_path, "2026-11-01")
    stale_dimension(m)
    j = run(m, tmp_path / "R")
    assert j["status"] == "stop" and j["stale"] and j["stale"]["quarter"] == "Q3 26"
