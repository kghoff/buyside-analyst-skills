import openpyxl
from analyze import run, GREEN, BLACK

def load(p):
    return openpyxl.load_workbook(p)


def find(ws, label, col=2):
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, col).value == label)


def test_analysis_goes_into_mod_and_every_old_row_keeps_its_value(mod_path, tmp_path):
    # the house layout (2026-11-06): no separate tab; analysis rows sit under the lines they measure, and the
    # rows they push down keep their numbers (formulas re-pointed, e.g. Gross Profit = Revenue + COGS)
    from evaluate import Book
    old = load(mod_path)
    res = run(mod_path, str(tmp_path / "work"))
    assert res["code"] == 0
    wb = load(mod_path)
    assert wb.sheetnames == ["MOD"]
    assert (tmp_path / "work" / "before_analyze.xlsx").exists()
    ws, ob, nb = wb["MOD"], Book(old), Book(wb)
    for lab in ("Revenue:", "Gross Profit", "Net Income", "TOTAL ASSETS:", "Ending Cash:", "Cash Check:"):
        r0, r1 = find(old["MOD"], lab), find(ws, lab)
        assert r1 > r0 or lab == "Revenue:"
        assert ob.value("MOD", f"J{r0}") == nb.value("MOD", f"J{r1}"), lab


def test_revenue_growth_rows_sit_under_revenue(mod_path, tmp_path):
    run(mod_path, str(tmp_path / "work"))
    ws = load(mod_path)["MOD"]
    assert ws["B4"].value == "Revenue:"
    assert ws["B5"].value == "% yoy" and ws["B5"].font.i and ws["B5"].alignment.indent == 2
    assert ws["J5"].value == '=IFERROR(J4/D4-1,"n.a.")' and ws["J5"].font.color.rgb == BLACK
    assert ws["D5"].value is None                                              # Q1 21: no year-ago column
    assert ws["X5"].value == '=IFERROR(X4/R4-1,"")'                            # estimate: blank, not n.a.
    assert ws["J7"].value == '=IFERROR(J4/G4-1,"n.a.")' and ws["N7"].value is None   # qoq: Q1 -> Q4; none for FY
    assert ws["J7"].number_format == "#,##0.0%_);(#,##0.0%)"


def test_sections_sit_inside_the_statements_like_the_dxcm_example_model(mod_path, tmp_path):
    run(mod_path, str(tmp_path / "work"))
    ws = load(mod_path)["MOD"]
    heads = [ws.cell(r, 1).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value]
    assert heads == ["TEST - Model", "INCOME STATEMENT", "BALANCE SHEET", "ASSETS:", "LIABILITIES & EQUITY:",
                     "ROIC, ROE, ROA", "LEVERAGE & CASH CONVERSION", "CASH FLOW STATEMENT",
                     "CASH FLOWS FROM OPERATING ACTIVITIES:", "CASH FLOWS FROM INVESTING ACTIVITIES:",
                     "CASH FLOWS FROM FINANCING ACTIVITIES:", "FREE CASH FLOW"]


import json


def find(ws, label, col=2):
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, col).value == label)


def test_fcf_adjustment_rows_are_blue_with_comments(mod_path, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "filings.json").write_text(json.dumps({
        "Q1 22": {"tables": {"CF": [["Capitalized software", [-1.0]]]}},
        "Q2 22": {"tables": {"CF": [["Capitalized software", [-3.0]]]}},
        "Q3 22": {"tables": {"CF": [["Capitalized software", [-6.0]]]}},
        "FY 22": {"tables": {"CF": [["Capitalized software", [-10.0]]]}}}))
    dec = {"fcf_adjustments": [{"label": "(-) Capitalized software", "pattern": "capitalized software",
                                "note": "Recurring software capex reported outside PP&E."}]}
    run(mod_path, str(work), decisions=dec)
    ws = load(mod_path)["MOD"]
    r = find(ws, "(-) Capitalized software")
    assert ws.cell(r, 2).comment.text.startswith("Recurring software capex")
    assert ws[f"K{r}"].value == f"=-3-J{r}" and ws[f"K{r}"].font.color.rgb == "FF0000FF"
    assert ws[f"K{r}"].comment is not None
    fcf = find(ws, "(+/-) Free Cash Flow")
    assert ws[f"K{fcf}"].value.startswith("=IFERROR(") and f"+K{r}," in ws[f"K{fcf}"].value


def test_days_in_period_from_manifest(mod_path, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "_manifest.json").write_text(json.dumps({"items": {
        "10-K:2021-12-31": {"label": "TEST 2021 10-K"}, "10-Q:2022-03-31": {"label": "TEST Q1 22 10-Q"}}}))
    res = run(mod_path, str(tmp_path / "work"), src=str(src))
    ws = load(mod_path)["MOD"]
    r = find(ws, "Days in Fiscal Period")
    assert ws[f"J{r}"].value == 90 and ws[f"J{r}"].font.color.rgb == "FF0000FF"     # from the dates
    assert ws[f"K{r}"].value == 91                                                  # date missing -> 91, logged
    assert ws[f"N{r}"].value == f"=SUM(J{r}:M{r})"
    assert ws[f"AB{r}"].value == 365                                                # annual-only estimate column
    assert any(t == "Days in period" for t, _, _ in res["log"])


def test_partial_year_tax_rate_gets_a_comment(mod_path, tmp_path):
    run(mod_path, str(tmp_path / "work"))
    ws = load(mod_path)["MOD"]
    r = find(ws, "Full Year Tax Rate")
    assert "FY 2023" in ws[f"V{r}"].comment.text


def test_rerun_stops_and_replace_rebuilds_the_same_rows(mod_path, tmp_path):
    # a second run must never stack a second set of rows; --replace removes this skill's rows first
    work = str(tmp_path / "work")
    first = run(mod_path, work)
    snap = {c.coordinate: c.value for row in load(mod_path)["MOD"].iter_rows() for c in row}
    res = run(mod_path, work)
    assert res["code"] == 2 and "--replace" in res["message"]
    assert run(mod_path, work, replace=True)["rows"] == first["rows"]
    assert {c.coordinate: c.value for row in load(mod_path)["MOD"].iter_rows() for c in row} == snap


def test_replace_keeps_users_own_rows(mod_path, tmp_path):
    work = str(tmp_path / "work")
    run(mod_path, work)
    wb = load(mod_path); ws = wb["MOD"]
    r = find(ws, "Revenue:")
    ws.insert_rows(r + 4)                                          # the user adds their own row under revenue's % qoq
    ws.cell(r + 4, 2, "% of Total Rev"); ws.cell(r + 4, 10, f"=J{r}/J{r}")
    wb.save(mod_path)
    assert run(mod_path, work, replace=True)["code"] == 0
    ws = load(mod_path)["MOD"]
    k = find(ws, "% of Total Rev")
    assert ws.cell(k, 10).value == f"=J{find(ws, 'Revenue:')}/J{find(ws, 'Revenue:')}"


def test_outlier_flags_comment_the_cell_and_log(mod_path, tmp_path):
    work = tmp_path / "work"
    res = run(mod_path, str(work), decisions={"outlier_notes": {"FY 2022": "one-time valuation-allowance release"}})
    ws = load(mod_path)["MOD"]
    r = find(ws, "Income Tax Rate")
    assert "Outlier" in ws[f"N{r}"].comment.text and "valuation-allowance" in ws[f"N{r}"].comment.text
    assert any(t == "Outlier" and "FY 2022" in w for t, w, _ in res["flags"])
    text = (work / "ANALYZE_JUDGMENT_CALLS.md").read_text()
    assert "## Outlier flags" in text and "FY 2022" in text and "No FCF adjustments" in text


def test_analysis_cells_keep_mods_font_name_and_size(mod_path, tmp_path):
    from openpyxl.styles import Font
    wb = load(mod_path)
    mod = wb["MOD"]
    mod["B4"].font = Font(name="Arial", sz=9)
    for c in range(4, mod.max_column + 1):
        mod.cell(4, c).font = Font(name="Aptos", sz=11)
    wb.save(mod_path)
    run(mod_path, str(tmp_path / "work"))
    ws = load(mod_path)["MOD"]
    assert ws["B5"].font.name == "Arial" and ws["B5"].font.sz == 9 and ws["B5"].font.i      # metric label
    assert ws["J5"].font.name == "Aptos" and ws["J5"].font.sz == 11                        # metric cell
    r = find(ws, "NOPAT")
    assert ws.cell(r, 2).font.name == "Arial" and ws.cell(r, 2).font.b                    # KPI label
    assert ws[f"J{r}"].font.name == "Aptos" and ws[f"J{r}"].font.sz == 11                 # KPI cell
    d = find(ws, "Days in Fiscal Period")
    assert ws[f"J{d}"].font.name == "Aptos"


def test_shading_matches_the_dxcm_example_model(mod_path, tmp_path):
    # the DXCM example model: every FY column is grey (theme 2 "Background 2", darker 10%) so years stand out from
    # quarters; the inserted ROIC / leverage / FCF headers are the lighter theme-3 sub-section colour
    run(mod_path, str(tmp_path / "work"))
    ws = load(mod_path)["MOD"]
    fill = lambda ref: (ws[ref].fill.fgColor.theme, round(ws[ref].fill.fgColor.tint, 2)) if ws[ref].fill.fill_type else None
    lev = find(ws, "LEVERAGE & CASH CONVERSION", col=1)
    for r in (5, lev + 3, ws.max_row):
        assert fill(f"H{r}") == (2, -0.1), r                   # FY 2021
        assert fill(f"Z{r}") == (2, -0.1) and fill(f"AB{r}") == (2, -0.1)   # 2024E, 2025E
        assert fill(f"G{r}") is None and fill(f"I{r}") is None # Q4 21 and the spacer stay white
    for t in ("ROIC, ROE, ROA", "LEVERAGE & CASH CONVERSION", "FREE CASH FLOW"):
        assert fill(f"A{find(ws, t, col=1)}") == (3, 0.25) and fill(f"H{find(ws, t, col=1)}") == (3, 0.25)


def test_kpi_row_styles_match_the_dxcm_example_model(mod_path, tmp_path):
    # The user's TotalRowCycle convention: subtotal = thin line above; total = thin above + double below.
    # TTM rows look like analysis rows (italic, indented); NOWC components are indented.
    run(mod_path, str(tmp_path / "work"))
    ws = load(mod_path)["MOD"]
    for lab in ("NOPAT", "Invested Capital (asset based)",
                "ROIC asset (Invested Cap Avg) TTM", "Cash Conversion Cycle (CCC)"):
        r = find(ws, lab)
        assert ws.cell(r, 2).border.top.style == "thin" and ws[f"J{r}"].border.top.style == "thin", lab
        assert ws[f"I{r}"].border.top.style == "thin" and ws.cell(r, 2).border.bottom.style is None, lab
    r = find(ws, "(+/-) Free Cash Flow")
    assert ws[f"J{r}"].border.top.style == "thin" and ws[f"J{r}"].border.bottom.style == "double"
    for lab in ("TTM NOPAT", "FCF TTM", "TTM", "EBITDA TTM"):
        c = ws.cell(find(ws, lab), 2)
        assert c.font.i and c.alignment.indent == 2, lab


def test_other_tabs_and_non_gaap_rows_keep_pointing_at_the_same_lines(mod_path, tmp_path):
    # the DXCM example file has Research / Px tabs that link into MOD, and /model-kpis may already have run:
    # after the inserts, every link must still read the same line (Net Income), not whatever moved into its row
    from evaluate import Book
    from verify import check
    wb = load(mod_path); ws = wb["MOD"]
    ws.insert_rows(31, 3)                      # the fixture has no formulas yet, so a plain insert is safe here
    ws["A31"] = "NON-GAAP METRICS"; ws["B32"] = "GAAP Net Income"
    for c in range(4, 30):
        if ws.cell(25, c).value is not None: ws.cell(32, c, f"={ws.cell(25, c).column_letter}25")
    wb.create_sheet("Research")["A1"] = "=MOD!J25*2"
    wb.save(mod_path)
    work = str(tmp_path / "work")
    assert run(mod_path, work)["code"] == 0
    wb = load(mod_path); ws, b = wb["MOD"], Book(wb)
    ni = find(ws, "Net Income")
    assert wb["Research"]["A1"].value == f"=MOD!J{ni}*2"
    assert ws.cell(find(ws, "GAAP Net Income"), 10).value == f"=J{ni}"
    assert ws.cell(find(ws, "GAAP Net Income") + 1, 2).value != "% yoy"          # non-GAAP rows get no new rows
    assert check(mod_path, work)[0] == []


def test_command_line_stop_prints_the_question_for_the_user(mod_path, tmp_path):
    # exit 2 is how the skill knows to stop and ask the user; it must not look like a crash (exit 1)
    import subprocess, sys, os
    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "analyze.py")
    args = [sys.executable, script, "--model", mod_path, "--work", str(tmp_path / "w")]
    assert subprocess.run(args, capture_output=True).returncode == 0
    r = subprocess.run(args, capture_output=True, text=True)
    assert r.returncode == 2 and "--replace" in r.stdout
