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
