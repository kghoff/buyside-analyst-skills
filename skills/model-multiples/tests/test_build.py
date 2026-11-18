"""End to end on a COPY of the reference model: build the Multiples tab, recalculate it in LibreOffice and check it
against engine.py. Never writes any file but the copies in tmp_path."""
import datetime as dt
import json
import math
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


def write_export(path, header, rows):
    with open(path, "w") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")


@pytest.fixture(scope="module")
def built_paid(tmp_path_factory):
    """Paid path: synthetic vendor exports (subject + one core peer), weekly for three years, smooth values."""
    w = tmp_path_factory.mktemp("paid")
    model = w / "model.xlsx"
    shutil.copy(REFERENCE, model)                      # a copy: never the live file
    os.makedirs(w / "comps")
    for t, e in (("DXCM", 3.1), ("PODD", 4.0), ("TNDM", -1.0)):
        json.dump(comp_snap(t, e), open(w / "comps" / f"{t}.json", "w"))
    days = [dt.date(2023, 11, 17) + dt.timedelta(days=7 * i) for i in range(156)]
    write_export(w / "dxcm_export.csv",
                 ["Date", "Price", "EPS", "EV", "MCAP", "EBITDA", "GP", "SALES", "LTM FCF", "NTM FCF", "S&P 500 NTM P/E"],
                 [(d.isoformat(), round(80 + 20 * math.sin(i / 9), 4), round(2 + 0.01 * i, 4),
                   round(30000 + 50 * i + 3000 * math.sin(i / 9), 2), round(31000 + 50 * i + 3000 * math.sin(i / 9), 2),
                   round(1200 + 4 * i, 2), round(2400 + 6 * i, 2), round(4000 + 10 * i, 2), round(600 + 2 * i, 2),
                   round(700 + 2 * i, 2), round(20 + math.cos(i / 13), 4)) for i, d in enumerate(days)])
    write_export(w / "abt_export.csv", ["Date", "Price", "EPS"],
                 [(d.isoformat(), round(110 + 5 * math.cos(i / 7), 4), round(5 + 0.005 * i, 4))
                  for i, d in enumerate(days)])
    json.dump({"subject": "DXCM", "core": ["ABT"],
               "comps": [{"ticker": "PODD", "group": "Diabetes devices"}, {"ticker": "TNDM", "group": "Diabetes devices"}],
               "files": {"DXCM": {"export": str(w / "dxcm_export.csv")}, "ABT": {"export": str(w / "abt_export.csv")}}},
              open(w / "comps.json", "w"))
    json.dump({"mode": "paid"}, open(w / "mode.json", "w"))
    out = w / "out.xlsx"
    summary = build.build(str(model), str(w), "DXCM", str(out))
    return model, out, w, summary


@pytest.fixture(scope="module")
def built_ng(built, tmp_path_factory):
    """The free path with Px Data on the non-GAAP basis (the reference model has a non-GAAP EPS row)."""
    model, _, w0, _ = built
    w = tmp_path_factory.mktemp("ng")
    shutil.copytree(w0, w, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("values", "verify", "out.xlsx", "*.png", "layout.json"))
    out = w / "out.xlsx"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(build.S, "eps_basis", lambda m: "ng")
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


@pytest.mark.slow
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


@pytest.mark.slow
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


@pytest.mark.slow
def test_paid_path_recalculates_and_carries_ntm_fcf_yield(built_paid):
    # The paid path's sixth multiple, NTM FCF yield, has its own weekly column and range row, and the whole tab
    # recalculates to engine.py's numbers just as the free path does.
    model, out, w, s = built_paid
    r = verify.run(str(model), str(out), str(w))
    assert r["failed"] == [] and r["errors"] == [] and r["changed_parts"] == [] and r["ok"], r
    ws = openpyxl.load_workbook(r["recalculated"], data_only=True)["Multiples"]
    labels = [ws.cell(i, 1).value for i in range(5, 20)]
    assert "FCF yield (NTM)" in labels
    lay = json.load(open(w / "layout.json"))
    hdr = {c.value: c.column_letter for c in ws[lay["W0"] - 1] if c.value}
    col = hdr["NTM FCF yield"]
    assert isinstance(ws[f"{col}{lay['WN']}"].value, float) and f"{col}{lay['WN']}" in lay["expected"]


def reachable(path):
    """Every part reachable from the workbook's sheets through their rels (drawings, charts, comments, VML...)."""
    from xlsx import Package, relpath_of, resolve
    pkg = Package(path)
    todo, seen = [p for *_, p in pkg.sheets()], set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        todo += [resolve(p, t) for _, (_, t) in pkg.rels(relpath_of(p)).items() if "TargetMode" not in t]
    return seen


@pytest.mark.slow
def test_rebuild_replaces_the_tab_cleanly(built, verified, tmp_path):
    # A rerun (each print) builds over a model that already has the tab: one tab, no orphan parts left behind,
    # every other part byte-identical, and the same numbers as the first build.
    _, out1, w, _ = built
    w2 = tmp_path / "work2"
    shutil.copytree(w, w2, ignore=shutil.ignore_patterns("values", "verify", "*.xlsx", "*.png", "layout.json"))
    out2 = w2 / "out2.xlsx"
    build.build(str(out1), str(w2), "DXCM", str(out2))
    assert openpyxl.load_workbook(out2, read_only=True).sheetnames.count("Multiples") == 1
    names = zipfile.ZipFile(out2).namelist()
    owned = [n for n in names if n.startswith(("xl/charts/", "xl/drawings/", "xl/comments")) and "/_rels/" not in n]
    assert set(owned) <= reachable(str(out2)), set(owned) - reachable(str(out2))
    r = verify.run(str(out1), str(out2), str(w2))
    assert r["ok"] and r["failed"] == [] and r["errors"] == [] and r["changed_parts"] == [], r
    a = openpyxl.load_workbook(verified["recalculated"], data_only=True)["Multiples"]
    b = openpyxl.load_workbook(r["recalculated"], data_only=True)["Multiples"]
    assert a["B7"].value == pytest.approx(b["B7"].value) and isinstance(a["B7"].value, float)


def weekly_header(path, w):
    lay = json.load(open(w / "layout.json"))
    ws = openpyxl.load_workbook(path)["Multiples"]
    return ws, lay, {c.value: c.column_letter for c in ws[lay["W0"] - 1] if c.value}


@pytest.mark.slow
def test_relative_rows_use_gaap_pe_on_a_non_gaap_basis(built_ng):
    # multpl's S&P P/E and the peers' XBRL EPS are GAAP, so with non-GAAP history the relative columns subtract from a
    # GAAP P/E column of their own, and the tab still recalculates to engine.py's numbers.
    model, out, w, _ = built_ng
    r = verify.run(str(model), str(out), str(w))
    assert r["ok"] and r["failed"] == [] and r["errors"] == [], r
    ws, lay, hdr = weekly_header(out, w)
    n = lay["WN"]
    assert ws[f"{hdr['GAAP P/E − S&P 500 P/E']}{n}"].value == f"=IFERROR({hdr['P/E (GAAP)']}{n}-{hdr['S&P 500 P/E']}{n},NA())"
    assert ws[f"{hdr['GAAP P/E − core-peer median']}{n}"].value.startswith(f"=IFERROR({hdr['P/E (GAAP)']}{n}-")
    rec = openpyxl.load_workbook(r["recalculated"], data_only=True)["Multiples"]
    assert rec[f"{hdr['P/E']}{n}"].value != pytest.approx(rec[f"{hdr['P/E (GAAP)']}{n}"].value)


def test_gaap_basis_has_one_pe_column_and_gaap_labels(built):
    # On the GAAP basis the P/E column already is the GAAP P/E: no duplicate column, and the relative rows use it.
    _, out, w, _ = built
    ws, lay, hdr = weekly_header(out, w)
    n = lay["WN"]
    assert "P/E (GAAP)" not in hdr and "EPS (GAAP)" not in hdr
    assert ws[f"{hdr['GAAP P/E − S&P 500 P/E']}{n}"].value == f"=IFERROR({hdr['P/E']}{n}-{hdr['S&P 500 P/E']}{n},NA())"
    labels = [ws.cell(i, 1).value for i in range(1, lay["W0"])]
    assert "GAAP P/E − S&P 500 P/E" in labels and "GAAP P/E − core-peer median" in labels
    assert "Street EPS (Yahoo consensus, analysts' basis)" in labels


def test_paid_peer_pe_is_a_formula_on_typed_ntm_eps(built_paid):
    # A peer's P/E is price ÷ its NTM EPS, live (black), from a typed (blue) EPS column, not a typed ratio.
    _, out, w, _ = built_paid
    ws, lay, hdr = weekly_header(out, w)
    n = lay["WN"]
    pe, eps, px = hdr["ABT P/E"], hdr["ABT NTM EPS"], hdr["ABT close"]
    assert ws[f"{pe}{n}"].value == f"=IFERROR(IF({eps}{n}>0,{px}{n}/{eps}{n},NA()),NA())"
    assert f"{pe}{n}" in lay["formulas"] and f"{pe}{n}" in lay["expected"] and f"{eps}{n}" in lay["typed"]
    assert "FCF yield (LTM)" in hdr
    assert "FCF yield (LTM)" in [ws.cell(i, 1).value for i in range(5, 20)]
    assert "GAAP P/E − S&P 500 P/E" not in hdr                  # paid: NTM vs NTM, not GAAP


def test_paid_export_in_dollars_stops(built_paid, tmp_path):
    # A vendor export in dollars against a model in millions would make every EV multiple a million times off.
    model, _, w, _ = built_paid
    import importer
    rows = importer.load(str(w / "dxcm_export.csv"))
    dollars = importer.Rows(dict(r, sales_ntm=r["sales_ntm"] * 1e6) for r in rows)
    with pytest.raises(SystemExit, match=r"dxcm_export.csv: the export's sales .* differ by about [\d,]+x\. The export "
                                         r"looks like it's in dollars while MOD is in millions"):
        build.paid_unit_check(str(w / "dxcm_export.csv"), dollars, str(model), str(model))
    assert build.paid_unit_check(str(w / "dxcm_export.csv"), rows, str(model), str(model)) == []
    bare = importer.Rows({"date": r["date"], "price": r["price"], "eps_ntm": r["eps_ntm"]} for r in rows)
    assert "not checked" in build.paid_unit_check("x.csv", bare, str(model), str(model))[0]


def test_missing_typed_value_is_a_black_na_formula_not_a_typed_number():
    # NA() is not a number from a source: it must not be blue or listed as typed (which would claim a source note).
    from xlsx import Package, Styles
    w = build.W(Styles(Package(REFERENCE).text("xl/styles.xml")))
    w.typed_("A1", None, build.X)
    w.typed_("A2", 1.5, build.X)
    assert w.typed == ["A2"] and w.formulas == ["A1"]
    assert w.sh.cells[(1, 1)] == ("f", "NA()", w.style(build.BLACK, build.X))
    assert w.sh.cells[(2, 1)][2] == w.style(build.BLUE, build.X)


def test_price_date_warning_and_as_of_headers(built):
    # Px Data in the fixture ends weeks before the comp snapshot's asof: the two "today" prices must be called out.
    _, out, _, summary = built
    w = [x for x in summary["warnings"] if x.startswith("Px Data ends ")]
    assert len(w) == 1 and "comp prices are 2026-11-17" in w[0] and "/model-price-history" in w[0]
    ws = openpyxl.load_workbook(out)["Multiples"]
    heads = [c.value for r in ws.iter_rows(max_col=1) for c in r if isinstance(c.value, str)]
    assert any(h.startswith("RANGES (as of 20") for h in heads) and any(h.startswith("FORWARD (price and EV as of 20") for h in heads)


def test_chart_titles_use_plain_hyphen(built):
    import zipfile
    _, out, _, _ = built
    z = zipfile.ZipFile(out)
    xml = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/charts/chart"))
    import re
    titles = [re.sub("<[^>]+>", "", t) for x in re.findall(r"<c:title>.*?</c:title>", xml) for t in [x]]
    assert any("P/E - S&P 500 P/E" in t.replace("&amp;", "&") for t in titles) and not any("\u2212" in t for t in titles)


@pytest.mark.slow
def test_include_toggle_is_yellow_kept_on_rerun_and_moves_the_averages(built, verified, tmp_path):
    # The user's ask (2026-11-18): flip an outlier off and see the averages, the line and the core-peer median move.
    # Each comp gets a yellow Include? cell (1 by default); a 0 the user typed survives the rebuild, and the averages,
    # the line and the weekly peer median then recalculate without that peer, still matching engine.py.
    _, out1, w, s = built
    ws = openpyxl.load_workbook(out1)["Multiples"]
    rows = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value in ("DXCM", "PODD", "TNDM")}
    assert ws.cell(min(rows.values()) - 1, 20).value == build.INC_HEAD            # header right above the comps
    for t, r in rows.items():
        c = ws.cell(r, 20)
        assert c.value == 1 and c.fill.fgColor.rgb == build.YELLOW and c.font.color.rgb == "FF0000FF", t
    assert s["line"]["n"] == 1 and s["line"]["reading"] == build.C.SAYS_NOTHING   # one peer with numbers: no reading
    edited = tmp_path / "edited.xlsx"                     # the user's edit, on a test copy (never a live model)
    wb = openpyxl.load_workbook(out1)
    wb["Multiples"].cell(rows["PODD"], 20).value = 0
    wb.save(edited)
    w2 = tmp_path / "work2"
    shutil.copytree(w, w2, ignore=shutil.ignore_patterns("values", "verify", "*.xlsx", "*.png", "layout.json"))
    out2 = w2 / "out2.xlsx"
    s2 = build.build(str(edited), str(w2), "DXCM", str(out2))
    assert s2["left_out"] == ["PODD"]
    assert openpyxl.load_workbook(out2)["Multiples"].cell(rows["PODD"], 20).value == 0
    r = verify.run(str(edited), str(out2), str(w2))
    assert r["failed"] == [] and r["errors"] == [], r
    rec = openpyxl.load_workbook(r["recalculated"], data_only=True)["Multiples"]
    avg = next(i for i in range(1, rec.max_row + 1) if str(rec.cell(i, 1).value).startswith("Average"))
    assert rec.cell(avg, 17).value == pytest.approx(100 / 3.1)       # P/E FY1 average: DXCM alone once PODD is out


def test_peer_median_chart_and_fitted_scatter_are_drawn(built):
    # The two new charts: the subject's P/E beside the core-peer median, and the scatter with its fitted line.
    _, out, _, _ = built
    z = zipfile.ZipFile(out)
    xml = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/charts/chart"))
    assert "P/E vs core-peer median P/E (TTM, GAAP)" in xml
    assert '<c:trendlineType val="linear"/>' in xml
