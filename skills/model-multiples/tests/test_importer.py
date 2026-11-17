import datetime as dt
import os

import pytest

import importer
from conftest import FIX


def test_brett_layout_is_recognised_without_help():
    m, unknown, missing = importer.detect(["Date", "Price", "EPS", "EV", "MCAP", "EBITDA", "GP", "SALES", "LTM FCF",
                                           "NTM FCF"])
    assert missing == [] and unknown == []
    assert m["eps_ntm"] == 2 and m["sales_ntm"] == 7 and m["fcf_ltm"] == 8


def test_abt_row_reproduces_the_chapter_multiples():
    rows = importer.load(os.path.join(FIX, "brett_pull.csv"))
    r = next(x for x in rows if x["date"] == dt.date(2022, 10, 25))
    m = importer.multiples(r)
    assert round(m["pe"], 1) == 21.4 and round(m["ev_ebitda"], 1) == 16.7 and round(m["ev_gp"], 1) == 8.0
    assert round(m["ev_rev"], 1) == 4.5 and round(m["fcf_yield"], 3) == 0.053 and round(m["fcf_yield_ntm"], 3) == 0.052


def test_unknown_headers_need_a_mapping():
    m, unknown, missing = importer.detect(["Datum", "Kurs", "Gewinn"])
    assert set(missing) >= {"date", "price", "eps_ntm"} and unknown == ["Datum", "Kurs", "Gewinn"]
    with pytest.raises(SystemExit, match="mapping.json"):
        importer.require(m, missing, "x.csv")


def test_mapping_override(tmp_path):
    p = tmp_path / "f.csv"
    p.write_text("Datum,Kurs,Gewinn\n2024-01-05,10,1\n2024-01-12,11,1\n")
    rows = importer.load(str(p), {"date": "Datum", "price": "Kurs", "eps_ntm": "Gewinn"})
    assert [r["price"] for r in rows] == [10.0, 11.0]


def test_daily_export_becomes_weekly_last_observation(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("Date,Price,EPS\n2024-01-08,10,1\n2024-01-12,12,1\n2024-01-15,13,1\n")
    rows = importer.load(str(p))
    assert [(r["date"].isoformat(), r["price"]) for r in rows] == [("2024-01-12", 12.0), ("2024-01-15", 13.0)]


def test_unparseable_dates_are_counted_not_dropped_silently(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("Date,Price,EPS\n2024-01-05,10,1\nTOTAL,,\nnot a date,5,1\n2024-01-12,11,n/a\n")
    rows = importer.load(str(p))
    assert len(rows) == 2 and rows.skipped == 2


def test_bad_number_cells_become_none_and_cannot_crash(tmp_path):
    p = tmp_path / "n.csv"
    p.write_text("Date,Price,EPS,EV\n2024-01-05,#N/A,--,\n2024-01-12,11,n/a\n2024-01-19,12\n")
    rows = importer.load(str(p))
    assert rows[0]["price"] is None and rows[0]["eps_ntm"] is None and rows[1]["eps_ntm"] is None
    assert rows[2]["price"] == 12.0 and rows[2]["eps_ntm"] is None
    assert importer.multiples(rows[1])["pe"] is None


def test_no_recognisable_header_row_fails_loudly(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Datum,Kurs\n2024-01-05,10\n")
    with pytest.raises(SystemExit, match="mapping.json"):
        importer.load(str(p))


def test_mapping_naming_a_missing_header_fails_loudly(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text("Date,Price,EPS\n2024-01-05,10,1\n")
    with pytest.raises(SystemExit, match="Nope"):
        importer.load(str(p), {"date": "Date", "price": "Price", "eps_ntm": "Nope"})


def _w(tmp_path, text, name="t.csv"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_multi_ticker_file_needs_a_choice_and_filters(tmp_path):
    p = _w(tmp_path, "Date,Ticker,Price,EPS\n2024-01-05,ABT US Equity,10,1\n2024-01-05,DXCM,50,2\n"
                     "2024-01-12,abt,11,1\n")
    with pytest.raises(SystemExit, match="ABT.*DXCM"):
        importer.load(p)
    assert [r["price"] for r in importer.load(p, ticker="ABT")] == [10.0, 11.0]
    assert [r["price"] for r in importer.load(p, ticker="dxcm")] == [50.0]


def test_single_ticker_file_ignores_ticker_argument(tmp_path):
    p = _w(tmp_path, "Date,Ticker,Price,EPS\n2024-01-05,ABT,10,1\n")
    assert len(importer.load(p, ticker="ZZZ")) == 1


def test_semicolon_file_uses_decimal_comma(tmp_path):
    p = _w(tmp_path, "Date;Price;EPS\n2024-01-05;1.234,5;2,5\n")
    r = importer.load(p)[0]
    assert r["price"] == 1234.5 and r["eps_ntm"] == 2.5


def test_comma_file_thousands_ok_stray_comma_stops(tmp_path):
    ok = _w(tmp_path, 'Date,Price,EPS\n2024-01-05,"1,234.5",2\n')
    assert importer.load(ok)[0]["price"] == 1234.5
    bad = _w(tmp_path, 'Date,Price,EPS\n2024-01-05,"12,5",2\n', "b.csv")
    with pytest.raises(SystemExit, match=r"b\.csv.*row 1.*12,5"):
        importer.load(bad)


def test_parentheses_and_percent():
    assert importer._num("(1.23)") == -1.23 and importer._num("5.3%") == pytest.approx(0.053)
    assert all(importer._num(x) is None for x in ("n/a", "--", "#N/A", ""))


def test_two_columns_for_one_field_is_refused_unless_mapped(tmp_path):
    p = _w(tmp_path, "Date,Price,Close,EPS\n2024-01-05,10,10.5,1\n")
    with pytest.raises(SystemExit, match="Price.*Close.*mapping.json"):
        importer.load(p)
    assert importer.load(p, {"date": "Date", "price": "Close", "eps_ntm": "EPS"})[0]["price"] == 10.5


def test_later_empty_row_does_not_replace_valid_one(tmp_path):
    p = _w(tmp_path, "Date,Price,EPS\n2024-01-08,10,1\n2024-01-12,,\n")
    assert importer.load(p)[0]["price"] == 10.0


def test_mapping_without_date_is_a_clear_error(tmp_path):
    p = _w(tmp_path, "Date,Price,EPS\n2024-01-05,10,1\n")
    with pytest.raises(SystemExit, match='"date"'):
        importer.load(p, {"price": "Price", "eps_ntm": "EPS"})
