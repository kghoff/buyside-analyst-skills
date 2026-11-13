import openpyxl
from analyze import run
from verify import check


def test_clean_run_passes(mod_path, tmp_path):
    work = str(tmp_path / "work")
    run(mod_path, work)
    fails, n = check(mod_path, work)
    assert fails == [] and n > 1000


def test_a_wrong_formula_is_caught(mod_path, tmp_path):
    work = str(tmp_path / "work")
    run(mod_path, work)
    wb = openpyxl.load_workbook(mod_path)
    ws = wb["MOD"]
    ws["P5"] = '=IFERROR(P4/D4-1,"n.a.")'          # % yoy pointing two years back instead of one
    wb.save(mod_path)
    fails, _ = check(mod_path, work)
    assert any("P5" in f for f in fails)


def test_mod_change_is_caught(mod_path, tmp_path):
    work = str(tmp_path / "work")
    run(mod_path, work)
    wb = openpyxl.load_workbook(mod_path)
    wb["MOD"]["J4"] = 999.0                          # a revenue cell changed while the rows were being moved
    wb.save(mod_path)
    fails, _ = check(mod_path, work)
    assert any("MOD changed" in f for f in fails)


def test_a_row_that_is_not_ours_is_caught(mod_path, tmp_path):
    work = str(tmp_path / "work")
    run(mod_path, work)
    wb = openpyxl.load_workbook(mod_path); ws = wb["MOD"]
    blank = next(r for r in range(1, ws.max_row) if ws.cell(r, 1).value == "FREE CASH FLOW") - 1   # our spacer row
    ws.cell(blank, 2, "Something else"); ws.cell(blank, 10, 1.0)
    wb.save(mod_path)
    assert any("not one of this skill's rows" in f for f in check(mod_path, work)[0])


def _zero_cogs(mod_path):
    wb = openpyxl.load_workbook(mod_path)
    ws = wb["MOD"]
    for c in range(4, ws.max_column + 1):
        if ws.cell(5, c).value is not None: ws.cell(5, c).value = 0
    wb.save(mod_path)


def test_zero_denominators_become_na_and_verify_passes(mod_path, tmp_path):
    work = str(tmp_path / "work")
    _zero_cogs(mod_path)
    run(mod_path, work)
    ws = openpyxl.load_workbook(mod_path)["MOD"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value and str(ws.cell(r, 2).value).startswith("Days Inventory"))
    assert ws[f"J{r}"].value.startswith('=IFERROR(') and ws[f"J{r}"].value.endswith(',"n.a.")')
    from evaluate import Book, ERR
    b = Book(openpyxl.load_workbook(mod_path))
    assert b.value("MOD", f"J{r}") == "n.a." and b.value("MOD", f"V{r}") == "n.a."
    fails, _ = check(mod_path, work)
    assert fails == []
    assert not any(b.value("MOD", c.coordinate) is ERR for row in ws.iter_rows() for c in row)


def test_plain_links_stay_unwrapped(mod_path, tmp_path):
    run(mod_path, str(tmp_path / "work"))
    ws = openpyxl.load_workbook(mod_path)["MOD"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == "Invested Capital (asset based)")
    assert ws[f"J{r}"].value.startswith('=IFERROR(')
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == "(-) Capital Expenditure")
    assert not ws[f"J{r}"].value.startswith("=IFERROR")


def test_missing_role_gives_na_dependents_and_verify_does_not_crash(mod_path, tmp_path):
    from evaluate import Book
    wb = openpyxl.load_workbook(mod_path)
    wb["MOD"]["B34"] = None                                   # no "Short-term marketable securities" row
    wb.save(mod_path)
    work = str(tmp_path / "work")
    res = run(mod_path, work)
    assert any("STSEC" in str(x) for x in res["log"])
    fails, _ = check(mod_path, work)
    assert fails == []
    wb = openpyxl.load_workbook(mod_path)
    ws, b = wb["MOD"], Book(wb)
    def row(label): return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == label)
    for label in ("Net Leverage / (Cash) Ratio",):                # leverage needs securities: n.a.
        assert b.value("MOD", f"V{row(label)}") == "n.a.", label
    # invested capital just leaves the missing line out, and says so
    assert any(t == "Invested capital" and "STSEC" in w for t, w, _ in res["log"])
    assert isinstance(b.value("MOD", f"V{row('Invested Capital (asset based)')}"), (int, float))


def _manifest(tmp_path):
    import json
    src = tmp_path / "src"
    src.mkdir()
    (src / "_manifest.json").write_text(json.dumps({"items": {
        "10-K:2021-12-31": {"label": "TEST 2021 10-K"}, "10-Q:2022-03-31": {"label": "TEST Q1 22 10-Q"}}}))
    return str(src)


def test_days_checked_against_manifest(mod_path, tmp_path):
    src, work = _manifest(tmp_path), str(tmp_path / "work")
    run(mod_path, work, src=src)
    fails, _ = check(mod_path, work, src=src)
    assert fails == []
    wb = openpyxl.load_workbook(mod_path)
    ws = wb["MOD"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == "Days in Fiscal Period")
    assert ws[f"J{r}"].value == 90
    ws[f"J{r}"] = 89
    wb.save(mod_path)
    fails, _ = check(mod_path, work, src=src)
    assert any(f"J{r}" in f and "Days" in f for f in fails)


def test_assumed_values_carry_comments(mod_path, tmp_path):
    src, work = _manifest(tmp_path), str(tmp_path / "work")
    wb = openpyxl.load_workbook(mod_path)
    wb["MOD"]["B34"] = None
    wb.save(mod_path)
    run(mod_path, work, src=src)
    wb = openpyxl.load_workbook(mod_path)
    ws = wb["MOD"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == "Days in Fiscal Period")
    assert "manifest" in ws.cell(r, 2).comment.text and "365" in ws.cell(r, 2).comment.text
    assert ws[f"J{r}"].comment is None                                     # 90 from the dates
    assert ws[f"K{r}"].comment.text == "Assumed 91 days: no period-end date for this quarter in the /collect-documents manifest."
    r2 = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == "Net Leverage / (Cash) Ratio")
    assert ws[f"J{r2}"].comment.text == "n.a.: MOD has no row for STSEC."
    assert check(mod_path, work, src=src)[0] == []
    ws[f"K{r}"].comment = None
    wb.save(mod_path)
    assert any("comment" in f for f in check(mod_path, work, src=src)[0])
