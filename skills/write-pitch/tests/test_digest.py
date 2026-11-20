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
    t = run_digest(wb, tmp_path)
    assert "Bulk blocks" in t and "Close: first (2) 102" in t and "last (301) 401" in t
    assert "=250" not in t                     # a listed row would print B150=250; none may be listed
    assert "B3: Buy" in t and "agent call; anchor Multiples!D9" in t and "r5 (Price): B=72.4" in t


def price_sheet(wb, n, title="Px", extra=None):
    ws = wb.active; ws.title = title
    ws["A1"], ws["B1"] = "Date", "Close"
    for i in range(2, n + 2):
        ws.cell(i, 1, i); ws.cell(i, 2, 100 + i)
    return ws


def test_threshold_200_rows_listed_201_rows_summarized(tmp_path):
    # why: the rule says more than 200 rows; 200 rows of data (201 with the header) is the first summarized size
    wb = openpyxl.Workbook(); price_sheet(wb, 199)           # rows 1-200
    assert "Bulk blocks\n(none)" in run_digest(wb, tmp_path)
    wb = openpyxl.Workbook(); price_sheet(wb, 200)           # rows 1-201
    assert "Close: first (2) 102" in run_digest(wb, tmp_path)


def test_block_under_80_percent_numeric_is_listed(tmp_path):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Mixed"
    for i in range(1, 301):
        ws.cell(i, 1, f"item {i}" if i % 2 else i)           # half text: a table, not a series
    t = run_digest(wb, tmp_path)
    assert "A5: item 5" in t and "r2: A=2" in t and "A=item 1 (A1)" in t and "Bulk blocks\n(none)" in t


def test_mod_over_200_rows_is_never_summarized(tmp_path):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    ws["D2"] = "2025"
    for i in range(3, 260):
        ws.cell(i, 2, f"line {i}"); ws.cell(i, 4, i)
    t = run_digest(wb, tmp_path)
    assert "Bulk blocks\n(none)" in t and "| r100 line 100 | 100 |" in t


def test_side_table_sharing_rows_with_a_series_is_listed(tmp_path):
    # why: an annual table to the right of daily prices shares its rows; summarizing per block would drop it
    wb = openpyxl.Workbook(); ws = price_sheet(wb, 300)
    for k in range(5):
        ws.cell(2 + k, 5, 2020 + k); ws.cell(2 + k, 6, 1.5 + k)
    t = run_digest(wb, tmp_path)
    assert "Close: first (2) 102" in t and "r3: E=2021, F=2.5" in t


def test_text_column_in_bulk_block_leaves_a_trace(tmp_path):
    wb = openpyxl.Workbook(); ws = price_sheet(wb, 300)
    ws["C1"] = "Event"
    for i in range(2, 302):
        ws.cell(i, 3, "earnings" if i % 2 else "split")
    t = run_digest(wb, tmp_path)
    assert "col C Event: 300 text cells, 2 distinct" in t and "split; earnings" in t


def test_mixed_date_and_number_column_is_not_skipped(tmp_path):
    import datetime
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Mix"
    ws["A1"] = "When"
    for i in range(2, 302):
        ws.cell(i, 1, datetime.datetime(2020, 1, 1) + datetime.timedelta(days=i) if i < 250 else i)
    t = run_digest(wb, tmp_path)
    assert "When (dates): first (2) 2020-01-03" in t and "When (numbers): first (250) 250" in t


def test_hidden_sheet_marked(tmp_path):
    wb = openpyxl.Workbook(); wb.active.title = "Seen"
    wb.create_sheet("Secret").sheet_state = "hidden"
    t = run_digest(wb, tmp_path)
    assert "## Secret (hidden)" in t and "## Seen\n" in t


def test_mod_label_fallback_pipe_escape_skipped_columns_and_notes(tmp_path):
    import datetime
    from openpyxl.comments import Comment
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    ws["D2"], ws["E2"], ws["F2"] = "2025", datetime.datetime(2025, 12, 31), "Q4 26E"
    ws["A5"] = "Only A label"; ws["D5"] = 7
    ws["B6"] = "a|b"; ws["D6"] = 8
    ws["E6"].comment = Comment("dropped column note", "x")
    ws["D6"].comment = Comment("kept column note", "x")
    t = run_digest(wb, tmp_path)
    assert "| r5 Only A label |" in t and "| r6 a\\|b |" in t
    assert "skipped columns: E=2025-12-31" in t
    assert "kept column note" in t and "dropped column note" not in t and "1 notes on dropped" in t


def test_mod_keeps_annual_last_8_actual_and_forecast_quarters(tmp_path):
    # why: the agent needs the recent run-rate and the forecast, not 10 years of quarters (token budget)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    heads = [f"Q{q} {y}" for y in (23, 24, 25) for q in (1, 2, 3, 4)] + ["Q1 26", "Q2 26", "Q3 26", "Q4 26E", "Q1 27E", 2025, "2026E"]
    for k, h in enumerate(heads):
        ws.cell(2, 4 + k, h)
        ws.cell(5, 4 + k, 1000 + k)
    ws["A4"], ws["B5"] = "INCOME STATEMENT", "Revenue"
    t = run_digest(wb, tmp_path)
    assert "Q1 23=" not in t and "Q4 23=" not in t                          # older than the last 8 actual quarters
    assert "Q4 24=" in t and "Q3 26=" in t                                  # last 8 actual: Q4 24 .. Q3 26
    assert "Q4 26E=" in t and "Q1 27E=" in t                                # all forecast quarters
    assert "2025=" in t and "2026E=" in t                                   # annual columns
    assert "| r5 Revenue |" in t and "1000" not in t                         # row kept (anchor = row + column letter), Q1 23 value dropped


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
    assert "r310 (Beta): B=1.25" in t and "B500: end" in t


def test_error_cells_are_not_headers_and_collapse_to_a_range_line(tmp_path):
    # why: an #N/A between a header and its numbers must not become the column header, nor flood Text
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Px"
    ws["B1"] = "NTM EPS"
    for i in range(2, 6):
        ws.cell(i, 2, "#N/A")
    ws["B6"], ws["B7"] = 0.15, 0.16
    ws["C3"] = "#DIV/0!"
    t = run_digest(wb, tmp_path)
    assert "headers: B=NTM EPS (B1)" in t and "r6: B=0.15" in t and "#N/A (B" not in t
    assert "errors: B2:B5 #N/A (4 cells), C3 #DIV/0! (1 cell)" in t and "B3: #N/A" not in t


def test_error_cells_in_a_bulk_column_do_not_become_its_header(tmp_path):
    wb = openpyxl.Workbook(); ws = price_sheet(wb, 300)
    ws["B2"] = "#N/A"
    t = run_digest(wb, tmp_path)
    assert "Close: first (3) 103" in t and "errors: B2 #N/A (1 cell)" in t
