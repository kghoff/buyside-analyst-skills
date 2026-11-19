import openpyxl, subprocess, sys, pathlib
D = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "digest.py"


def run_digest(wb, tmp_path):
    p = tmp_path / "m.xlsx"
    wb.save(p)
    out = tmp_path / "d.md"
    subprocess.run([sys.executable, str(D), "--values", str(p), "--out", str(out)], check=True)
    return out.read_text()


def test_bulk_block_is_summarized_and_text_and_notes_kept(tmp_path):
    from openpyxl.comments import Comment
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Px Data"
    ws["A1"], ws["B1"] = "Date", "Close"
    for i in range(2, 302):
        ws.cell(i, 1, i); ws.cell(i, 2, 100 + i)
    v = wb.create_sheet("Valuation")
    v["A3"], v["B3"] = "Verdict", "Buy"
    v["B3"].comment = Comment("agent call; anchor Multiples!D9", "x")
    v["A5"], v["B5"] = "Price", 72.4
    p = tmp_path / "m.xlsx"; wb.save(p)
    out = tmp_path / "d.md"
    subprocess.run([sys.executable, str(D), "--values", str(p), "--out", str(out)], check=True)
    t = out.read_text()
    assert "Bulk blocks" in t and "Close: first (2) 102" in t and "last (301) 401" in t
    assert "B150" not in t                     # no row-by-row dump of the bulk block
    assert "B3: Buy" in t and "agent call; anchor Multiples!D9" in t and "B5 (Price" in t


def test_mod_keeps_annual_last_8_actual_and_forecast_quarters(tmp_path):
    # why: the agent needs the recent run-rate and the forecast, not 10 years of quarters (token budget)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    heads = [f"Q{q} {y}" for y in (23, 24, 25) for q in (1, 2, 3, 4)] + ["Q1 26", "Q2 26", "Q3 26", "Q4 26E", "Q1 27E", 2025, "2026E"]
    for k, h in enumerate(heads):
        ws.cell(2, 4 + k, h)
        ws.cell(5, 4 + k, 1000 + k)
    ws["A4"], ws["B5"] = "INCOME STATEMENT", "Revenue"
    t = run_digest(wb, tmp_path)
    assert "(Revenue | Q1 23)" not in t and "(Revenue | Q4 23)" not in t    # older than the last 8 actual quarters
    assert "(Revenue | Q4 24)" in t and "(Revenue | Q3 26)" in t            # last 8 actual: Q4 24 .. Q3 26
    assert "(Revenue | Q4 26E)" in t and "(Revenue | Q1 27E)" in t          # all forecast quarters
    assert "(Revenue | 2025)" in t and "(Revenue | 2026E)" in t             # annual columns


def test_big_tab_bulk_summarized_but_small_labelled_block_below_listed(tmp_path):
    # why: price history must not be dumped, but the labelled stats under it must still reach the agent
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Big"
    ws["A1"], ws["B1"] = "Date", "Px"
    for i in range(2, 302):
        ws.cell(i, 1, i); ws.cell(i, 2, i * 0.1)
    ws["A310"], ws["B310"] = "Beta", 1.25
    ws["A500"], ws["B500"] = "Note", "end"
    t = run_digest(wb, tmp_path)
    assert "Px: first (2) 0.2" in t and "B150" not in t
    assert "B310 (Beta" in t and "B500: end" in t
