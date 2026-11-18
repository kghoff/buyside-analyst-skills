import datetime, os

from fixtures import make_model
from modeldata import _number, extract, price_from_csv, price_from_tab


def test_line_rows_are_read_with_formulas_calculated(tmp_path):
    rows = extract(make_model(str(tmp_path / "m.xlsx")))
    v = {(r["metric"], r["period"]): r["value"] for r in rows}
    assert v[("INCOME STATEMENT | Revenue", "Q1 2024")] == 100
    assert v[("INCOME STATEMENT | Gross Profit", "Q2 2024")] == 66          # =E5+E7
    assert v[("INCOME STATEMENT | Revenue", "FY2024")] == 460               # =SUM(D5:G5)
    assert next(r for r in rows if r["period"] == "Q1 2024")["source"].startswith("Model, MOD!D")


def test_analysis_rows_and_estimate_columns_are_skipped(tmp_path):
    # the filings research is history; driver math recomputes growth and margins itself
    rows = extract(make_model(str(tmp_path / "m.xlsx")))
    assert not any("% yoy" in r["metric"] for r in rows)
    assert not any(r["period"].startswith("Q1 2025") for r in rows)


def test_same_label_in_a_section_gets_its_row_number(tmp_path):
    names = {r["metric"] for r in extract(make_model(str(tmp_path / "m.xlsx")))}
    assert "NON-GAAP METRICS | Gross Profit" in names and "NON-GAAP METRICS | Gross Profit (row 12)" in names


def test_price_from_the_models_px_data_tab(tmp_path):
    p = make_model(str(tmp_path / "m.xlsx"), px_rows=[(datetime.datetime(2024, 1, 2), 120.5, 470.1)])
    assert price_from_tab(p) == [("2024-01-02", 120.5, 470.1)]


def test_price_from_stooq_csvs_joins_ticker_and_spy_by_date(tmp_path):
    d = tmp_path / "Price Data"
    d.mkdir()
    hdr = "Date,Open,High,Low,Close,Volume\n"
    (d / "test_us_d.csv").write_text(hdr + "2024-01-02,1,1,1,10.5,9\n2024-01-03,1,1,1,11,9\n")
    (d / "spy_us_d.csv").write_text(hdr + "2024-01-02,1,1,1,470,9\n")
    assert price_from_csv(str(d), "TEST") == [("2024-01-02", 10.5, 470.0), ("2024-01-03", 11.0, None)]


def test_price_from_yahoo_csvs_uses_adj_close_for_returns(tmp_path):
    # Returns must be total return: a Yahoo file's Adj Close (dividends in), not the traded Close.
    d = tmp_path / "Price Data"
    d.mkdir()
    hdr = "Date,Open,High,Low,Close,Adj Close,Volume\n"
    (d / "test_us_d.csv").write_text(hdr + "2024-01-02,1,1,1,10.5,10.1,9\n")
    (d / "spy_us_d.csv").write_text(hdr + "2024-01-02,1,1,1,470,460,9\n")
    assert price_from_csv(str(d), "TEST") == [("2024-01-02", 10.1, 460.0)]


def test_sub_headers_prefix_the_rows_under_them_until_a_blank_row(tmp_path):
    names = {r["metric"] for r in extract(make_model(str(tmp_path / "m.xlsx")))}
    assert "KPIS | Employee Count | United States" in names
    assert "KPIS | Distributor | United States" in names
    assert not any(n.endswith("| Employee Count") or n.endswith("| Distributor") for n in names)


def test_section_title_in_row_2_applies_to_rows_below(tmp_path):
    names = {r["metric"] for r in extract(make_model(str(tmp_path / "m.xlsx")))}
    assert "PROJECTIONS | Orders" in names


def test_percent_labels_are_analysis_but_reported_kpis_stay(tmp_path):
    names = {r["metric"] for r in extract(make_model(str(tmp_path / "m.xlsx")))}
    assert not any("% of Total" in n or "FCF conversion" in n for n in names)
    assert any(n.endswith("Organic Revenue Growth") for n in names)


def test_cached_value_used_when_evaluator_cannot_calculate():
    from evaluate import ERR
    assert _number(ERR, 12.5) == 12.5
    assert _number(3, 12.5) == 3
    assert _number(ERR, "x") is None


def _px(tmp_path, headers, row):
    # a throwaway Px Data tab: title, note, blank, headers in row 4, one day of data in row 5
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Px Data"
    ws["A1"] = "title"
    for i, h in enumerate(headers):
        ws.cell(row=4, column=i + 1, value=h)
    for i, v in enumerate(row):
        ws.cell(row=5, column=i + 1, value=v)
    p = str(tmp_path / "m.xlsx")
    wb.save(p)
    return p


def test_price_from_tab_reads_the_total_return_column_when_there_is_one(tmp_path):
    # Yahoo-era Px Data: B is the traded price, D the total return. The driver math compares the stock with SPY (a
    # total return), so it must read D, or a dividend payer looks worse than it did every year.
    p = _px(tmp_path, ["Date", "ABT close", "SPY close", " ABT total return (dividends in) ", "ABT daily return"],
            [datetime.datetime(2024, 1, 2), 100.0, 470.1, 104.0, None])
    assert price_from_tab(p) == [("2024-01-02", 104.0, 470.1)]


def test_price_from_tab_reads_column_b_on_models_without_a_total_return_column(tmp_path):
    # older stooq models: B is already dividend-adjusted and D is the daily return
    p = _px(tmp_path, ["Date", "DXCM close", "SPY close", "DXCM daily return"],
            [datetime.datetime(2024, 1, 2), 100.0, 470.1, 0.01])
    assert price_from_tab(p) == [("2024-01-02", 100.0, 470.1)]
