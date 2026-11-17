"""End to end on a COPY of the reference model: build the Multiples tab, recalculate it in LibreOffice and check it
against engine.py. Never writes any file but the copies in tmp_path."""
import datetime as dt
import json
import os
import shutil
import zipfile

import openpyxl
import pytest

import build
import verify
from conftest import FIX, REFERENCE


def comp_snap(t, eps1):
    return {"ticker": t, "asof": "2026-11-17", "price": 100.0, "currency": "USD", "marketCap": 4e10, "adv3m": 3e6,
            "financial": {"totalDebt": 2e9, "totalCash": 3e9, "ebitda": 1.2e9, "financialCurrency": "USD"},
            "trend": [{"period": "0y", "endDate": "2026-12-31T00:00:00.000Z", "earningsEstimate": {"avg": 2.7},
                       "revenueEstimate": {"avg": 5.2e9}},
                      {"period": "+1y", "endDate": "2027-12-31T00:00:00.000Z", "earningsEstimate": {"avg": eps1},
                       "revenueEstimate": {"avg": 5.8e9}}]}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    w = tmp_path_factory.mktemp("work")
    model = w / "model.xlsx"
    shutil.copy(REFERENCE, model)                      # a copy: never the live file
    os.makedirs(w / "comps")
    for t, e in (("DXCM", 3.1), ("PODD", 4.0), ("TNDM", -1.0)):
        json.dump(comp_snap(t, e), open(w / "comps" / f"{t}.json", "w"))
    shutil.copy(os.path.join(FIX, "abt_xbrl.json"), w / "ABT_xbrl.json")
    with open(w / "abt_us_d.csv", "w") as f:           # synthetic closes: one a week, 2016 on
        f.write("Date,Open,High,Low,Close,Volume\n")
        d = dt.date(2016, 1, 4)
        while d < dt.date(2026, 11, 14):
            f.write(f"{d.isoformat()},1,1,1,{100 + (d.toordinal() % 50)},1\n")
            d += dt.timedelta(days=7)
    from sp500 import parse, save
    save(str(w / "sp500.json"), parse(open(os.path.join(FIX, "multpl.html"), encoding="utf-8").read()),
         dt.date.today().isoformat())
    json.dump({"subject": "DXCM", "core": ["ABT"],
               "comps": [{"ticker": "PODD", "group": "Diabetes devices"}, {"ticker": "TNDM", "group": "Diabetes devices"}],
               "files": {"ABT": {"xbrl": str(w / "ABT_xbrl.json"), "prices": str(w / "abt_us_d.csv")}}},
              open(w / "comps.json", "w"))
    json.dump({"mode": "free"}, open(w / "mode.json", "w"))
    out = w / "out.xlsx"
    summary = build.build(str(model), str(w), "DXCM", str(out))
    return model, out, w, summary


@pytest.fixture(scope="module")
def verified(built):
    model, out, w, _ = built
    return verify.run(str(model), str(out), str(w))


def test_tab_added_and_every_other_part_byte_identical(built):
    model, out, w, _ = built
    assert "Multiples" in openpyxl.load_workbook(out, read_only=True).sheetnames
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    same = [n for n in a.namelist() if n not in verify.ALLOWED]
    assert all(a.read(n) == b.read(n) for n in same)


def test_recalculated_tab_matches_engine(verified):
    # Every checked cell recalculates in LibreOffice to engine.py's number: the live formulas and the Python agree.
    r = verified
    assert r["failed"] == [] and r["errors"] == [] and r["changed_parts"] == [] and r["checked"] > 500, r


def test_colours_follow_house_rules(built):
    model, out, w, _ = built
    lay = json.load(open(w / "layout.json"))
    ws = openpyxl.load_workbook(out)["Multiples"]
    for ref in lay["typed"][:50]:
        assert ws[ref].font.color.rgb == "FF0000FF", ref         # typed numbers blue
    for ref in lay["links"][:50]:
        assert ws[ref].font.color.rgb == "FF008000", ref         # links to other tabs green
    for ref in lay["formulas"][:50]:
        assert ws[ref].font.color.rgb == "FF000000", ref         # formulas black
    for ref in lay["typed"][:20]:
        assert ws[ref].comment is None or ws[ref].comment.text   # source notes live on the column headers


def test_comp_sheet_ranked_and_nm_peer_shown(built, verified):
    # Ranked most expensive first on next year's P/E; a loss-maker (TNDM, EPS FY1 < 0) is NM and sorts last, shown as
    # #N/A rather than a negative multiple; the subject's row stands out in bold.
    _, out, w, s = built
    assert [c["ticker"] for c in s["comps"]] == ["DXCM", "PODD", "TNDM"]
    assert all(isinstance(x, str) for x in s["warnings"])
    rec = openpyxl.load_workbook(verified["recalculated"], data_only=True)["Multiples"]
    rows = {rec.cell(r, 1).value: r for r in range(1, rec.max_row + 1) if rec.cell(r, 1).value in ("DXCM", "PODD", "TNDM")}
    assert rows["DXCM"] < rows["PODD"] < rows["TNDM"]
    assert rec.cell(rows["PODD"], 17).value == pytest.approx(25.0)                       # P/E FY1 = 100 / 4.0
    assert rec.cell(rows["TNDM"], 17).value == "#N/A"                                    # P/E FY1 on a loss: NM
    built_ws = openpyxl.load_workbook(out)["Multiples"]
    assert built_ws.cell(rows["DXCM"], 1).font.b and not built_ws.cell(rows["PODD"], 1).font.b
