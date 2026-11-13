"""KPI values only reach the user's model if the printed number is on the cited line; full years follow the metric's kind."""
import json
import os
import subprocess
import sys

import openpyxl
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
REL = "Press Releases/_md/{q} 25 TEST release 2025-{m}-30.md"
TEXT = {
    "Q1": "Customers reached 1,000 at quarter end.\nOrganic revenue growth was 10.0% and procedures were 50.",
    "Q2": "Customers reached 1,100 at quarter end.\nOrganic revenue growth was 11.0% and procedures were 60.",
    "Q3": "Customers reached 1,200 at quarter end.\nOrganic revenue growth was 12.0% and procedures were 70.",
    "Q4": "Customers reached 1,300 at quarter end.\nOrganic revenue growth was 13.0% and procedures were 80.\n"
          "For the full year, organic revenue growth was 11.5%, procedures were 260 and Q1 procedures are restated to 55.",
}
PLAN = {"metrics": [
    {"key": "customers", "label": "Customers", "units": "#", "kind": "stock", "patterns": ["customers"], "definition": "d", "why": "w"},
    {"key": "organic", "label": "Organic Revenue Growth", "units": "%", "kind": "rate", "patterns": ["organic"], "definition": "d", "why": "w"},
    {"key": "procs", "label": "Procedures", "units": "#", "kind": "flow", "patterns": ["procedures"], "definition": "d", "why": "w"}],
    "analysis": []}


def entry(q, value, raw, line, scale=1, period=None):
    return {"period": period or f"{q} 25", "value": value, "raw": raw, "scale": scale, "line": line,
            "file": REL.format(q=q, m={"Q1": "04", "Q2": "07", "Q3": "10", "Q4": "12"}[q])}


@pytest.fixture
def case(tmp_path):
    src = tmp_path / "src"; (src / "Press Releases" / "_md").mkdir(parents=True)
    for q, t in TEXT.items():
        (src / REL.format(q=q, m={"Q1": "04", "Q2": "07", "Q3": "10", "Q4": "12"}[q])).write_text(t)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    for i, h in enumerate(["Q1 25", "Q2 25", "Q3 25", "Q4 25", 2025]): ws.cell(1, 4 + i, h)
    ws["A2"] = "INCOME STATEMENT"; ws["B4"] = "Revenue"; ws["D4"] = 100; ws["A10"] = "BALANCE SHEET"; ws["B11"] = "Cash"; ws["D11"] = 5
    ws["D12"] = "=D11*2"
    model = str(tmp_path / "TEST_model.xlsx"); wb.save(model)
    w = tmp_path / "w"; (w / "values").mkdir(parents=True); (w / "kpi_plan.json").write_text(json.dumps(PLAN))
    vals = {
        "customers": [entry(q, v, f"{v:,}", 1) for q, v in zip(["Q1", "Q2", "Q3", "Q4"], [1000, 1100, 1200, 1300])],
        "organic": [entry(q, v / 100, f"{v}%", 2, 0.01) for q, v in zip(["Q1", "Q2", "Q3", "Q4"], [10.0, 11.0, 12.0, 13.0])]
                   + [entry("Q4", 0.115, "11.5%", 3, 0.01, "FY 25")],
        "procs": [entry(q, v, str(v), 2) for q, v in zip(["Q1", "Q2", "Q3", "Q4"], [50, 60, 70, 80])]
                 + [entry("Q4", 260, "260", 3, period="FY 25"), entry("Q4", 55, "55", 3, period="Q1 25")],
    }
    for k, v in vals.items(): (w / "values" / f"{k}.json").write_text(json.dumps(v))
    return str(src), str(w), model


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)


def check(src, w, model, *extra):
    return run("kpi_check.py", "--src", src, "--work", w, "--plan", os.path.join(w, "kpi_plan.json"), "--model", model, *extra)


def test_numbers_not_on_the_cited_line_are_rejected(case):
    # a reader that misreads or invents a number must never get it into the model
    src, w, model = case
    bad = [entry("Q1", 1050, "1,050", 1), entry("Q2", 1100, "1,100", 2), entry("Q3", 1200.0, "1,200", 1, scale=10)]
    open(os.path.join(w, "values", "customers.json"), "w").write(json.dumps(bad))
    assert check(src, w, model).returncode == 0
    report = open(os.path.join(w, "kpi_check.md")).read()
    assert report.count("customers Q") == 3 and "not printed" in report and "x 10" in report
    assert json.load(open(os.path.join(w, "kpi_values.json")))["customers"] == {}


def test_period_own_document_wins_and_the_restatement_is_reported(case):
    # Q1 procedures: 50 in the Q1 release, 55 restated in the Q4 release -> keep 50 (as originally reported), flag 55
    src, w, model = case
    check(src, w, model)
    v = json.load(open(os.path.join(w, "kpi_values.json")))["procs"]["Q1 25"]
    assert v["value"] == 50 and "55" in v["conflict"][0]
    assert "Different values for the same period" in open(os.path.join(w, "kpi_check.md")).read()


def test_document_cannot_report_a_later_period(case):
    src, w, model = case
    open(os.path.join(w, "values", "customers.json"), "w").write(json.dumps([entry("Q1", 1000, "1,000", 1, period="Q3 25")]))
    check(src, w, model)
    assert "older than Q3 25" in open(os.path.join(w, "kpi_check.md")).read()


def test_build_fills_full_years_by_kind_and_passes_its_own_check(case):
    src, w, model = case
    check(src, w, model)
    out = model.replace(".xlsx", "_out.xlsx")
    r = run("kpi_build.py", "--model", model, "--work", w, "--plan", os.path.join(w, "kpi_plan.json"), "--out", out)
    assert r.returncode == 0, r.stderr
    ws = openpyxl.load_workbook(out)["MOD"]
    rows = {ws.cell(i, 2).value: i for i in range(1, ws.max_row + 1)}
    assert ws.cell(rows["Customers"], 8).value == "=G%d" % rows["Customers"]          # stock: year-end = Q4 (link)
    assert ws.cell(rows["Procedures"], 8).value == "=SUM(D{0}:G{0})".format(rows["Procedures"])  # flow: sum
    assert ws.cell(rows["Organic Revenue Growth"], 8).value == 0.115                   # rate: reported FY
    assert ws.cell(rows["Customers"], 4).font.color.rgb == "FF0000FF" and ws.cell(rows["Customers"], 4).comment
    assert ws.cell(rows["Customers"], 8).font.color.rgb == "FF008000"
    # The user's layout (2026-11-06): company metrics sit at the top, above the income statement
    assert rows["Customers"] < rows["Revenue"] and ws.cell(rows["Cash"] + 1, 4).value == f"=D{rows['Cash']}*2"
    assert next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "KEY OPERATING METRICS") > 1   # header row stays first
    assert check(src, w, out, "--built").returncode == 0


def test_built_check_catches_a_hand_edited_number(case):
    src, w, model = case
    check(src, w, model)
    out = model.replace(".xlsx", "_out.xlsx")
    run("kpi_build.py", "--model", model, "--work", w, "--plan", os.path.join(w, "kpi_plan.json"), "--out", out)
    wb = openpyxl.load_workbook(out); ws = wb["MOD"]
    r = next(i for i in range(1, ws.max_row + 1) if ws.cell(i, 2).value == "Procedures"); ws.cell(r, 5).value = 61; wb.save(out)
    res = check(src, w, out, "--built")
    assert res.returncode == 1 and "Q2 25" in res.stdout


def test_prefer_restated_years_switch_only_those_years(case):
    # a metric redefined in 2018 with 2017 restated: 2017's quarters must all use the new definition to sum to FY17
    src, w, model = case
    plan = json.load(open(os.path.join(w, "kpi_plan.json"))); plan["metrics"][2]["prefer_restated"] = [2025]
    open(os.path.join(w, "kpi_plan.json"), "w").write(json.dumps(plan))
    check(src, w, model)
    assert json.load(open(os.path.join(w, "kpi_values.json")))["procs"]["Q1 25"]["value"] == 55


def test_older_layout_keeps_the_section_before_the_balance_sheet(case):
    # models built before 2026-11-06 have INCOME STATEMENT on the period-header row: inserting above it would push
    # the period headers down, so the section goes where it used to
    src, w, model = case
    wb = openpyxl.load_workbook(model); ws = wb["MOD"]
    for c in range(4, 9): ws.cell(2, c, ws.cell(1, c).value); ws.cell(1, c).value = None
    wb.save(model)
    check(src, w, model)
    out = model.replace(".xlsx", "_out.xlsx")
    assert run("kpi_build.py", "--model", model, "--work", w, "--plan", os.path.join(w, "kpi_plan.json"), "--out", out).returncode == 0
    ws = openpyxl.load_workbook(out)["MOD"]
    rows = {ws.cell(i, 2).value: i for i in range(1, ws.max_row + 1)}
    assert rows["Revenue"] < rows["Customers"] < rows["Cash"] and ws.cell(2, 4).value == "Q1 25"
