"""A refresh (new prices) must keep what the user and /research-filings added to the three tabs: the user's own text
boxes and arrows on Idio Chart, every typed note, and the tabs' places. And it must never let another tab's formula
quietly read something else afterwards. The fixture is the user's reference model, which carries 26 of their own
shapes on Idio Chart, with five more trading days in the price files."""
import json
import os
import re
import shutil
import subprocess
import sys

import pandas as pd
import pytest

import refresh
from conftest import FIX
from xlsx import Package

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
EXTRA_DAYS = 5


def _run(*args, check=True):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=SCRIPTS)
    if check and r.returncode:
        raise AssertionError(r.stdout + r.stderr)
    return r


def _inputs(w, src_dir):
    """The work folder a normal run leaves: settings, reviewed events and the price files (with extra days)."""
    v = json.load(open(os.path.join(FIX, "reference_values.json")))["events"]
    json.dump({"ticker": "DXCM", "overlay_basis": "non-gaap", "ebitda": True, "roic_role": "roic", "fye_month": 12,
               "etf": "XHE", "etf_label": "medtech"}, open(w / "price_history.json", "w"))
    json.dump({"full": {p: {"date": d, "source": "Source: test"} for p, d in zip(v["periods"], v["full_dates"])},
               "events": [{"date": d, "type": t, "name": n, "timing": tm, "source": "test"}
                          for d, t, n, tm, *_ in v["list"]]}, open(w / "events.json", "w"))
    files = {}
    for k, t in (("stock", "dxcm"), ("spy", "spy"), ("etf", "xhe"), ("mom", "mtum")):
        df = pd.read_csv(os.path.join(FIX, f"{t}_us_d.csv"))
        last = pd.Timestamp(df["Date"].iloc[-1])
        add = pd.bdate_range(last + pd.Timedelta(days=1), periods=EXTRA_DAYS)
        row = df.iloc[-1]
        extra = pd.DataFrame([{**row, "Date": d.date().isoformat(), "Close": row["Close"] * (1 + 0.004 * (i + 1))}
                              for i, d in enumerate(add)])
        p = src_dir / f"{t}_us_d.csv"
        pd.concat([df, extra]).to_csv(p, index=False)
        files[k] = {"path": str(p), "ticker": t}
    json.dump({"files": files}, open(w / "prices.json", "w"))


def _edit(path, tab, fn):
    pkg = Package(path)
    part = refresh.sheet_parts(pkg)[tab]
    pkg.put(part, fn(pkg.text(part)))
    pkg.save(path)


def _formula_cell(xml, ref, formula):
    xml = refresh._set_text(xml, ref, "x")
    return re.sub(rf'<c r="{ref}"[^>]*>.*?</c>', f'<c r="{ref}"><f>{formula}</f></c>', xml, count=1, flags=re.S)


@pytest.fixture(scope="session")
def old_model(reference_model, tmp_path_factory):
    """The reference model as a user would have it: Research's averages repointed from the old P/E column (O, which
    the lean layout moved) to the close, one single-cell link into Px Data, and a typed note on a Px Events row."""
    d = tmp_path_factory.mktemp("old")
    m = str(d / "DXCM_model.xlsx")
    shutil.copy(reference_model, m)
    repoint = lambda x: re.sub(r"(Px Data(?:'|&apos;)!)\$O\$(\d+):\$O\$", r"\1$B$\2:$B$", x)
    _edit(m, "Research", lambda x: _formula_cell(repoint(x), "ZZ1", "'Px Data'!$A$1002"))
    _edit(m, "Px Events", lambda x: refresh._set_text(x, "S6", "My own note on this event"))
    return m


@pytest.fixture(scope="session")
def refreshed(old_model, tmp_path_factory):
    d = tmp_path_factory.mktemp("refresh")
    w = d / "w"
    w.mkdir()
    (d / "src").mkdir()
    _inputs(w, d / "src")
    _run("refresh.py", "extract", "--model", old_model, "--work", str(w))
    _run("build.py", "--model", old_model, "--work", str(w), "--out", str(d / "built.xlsx"), "--refresh")
    r = _run("refresh.py", "restore", "--model", old_model, "--built", str(d / "built.xlsx"), "--work", str(w),
             "--out", str(d / "final.xlsx"))
    return {"w": w, "final": str(d / "final.xlsx"), "report": json.loads(r.stdout),
            "carry": json.load(open(w / "carry.json")), "layout": json.load(open(w / "layout.json"))}


def test_every_shape_the_user_drew_comes_back_unchanged(old_model, refreshed):
    """The user's 13 text boxes and 13 arrows are theirs; nothing can recreate them, so each must come back exactly
    (same cells, same text, same style). Only the drawing id may change."""
    old = Package(old_model)
    od = refresh.drawing_of(old, refresh.sheet_parts(old)["Idio Chart"])
    theirs = [a.group(0) for a in refresh.ANCHOR.finditer(old.text(od)) if "drawingml/2006/chart" not in a.group(0)]
    assert len(theirs) == 26
    new = Package(refreshed["final"])
    nd = refresh.drawing_of(new, refresh.sheet_parts(new)["Idio Chart"])
    now = {refresh.strip_id(a.group(0)) for a in refresh.ANCHOR.finditer(new.text(nd))}
    assert all(refresh.strip_id(a) in now for a in theirs)
    ids = re.findall(r'<(?:xdr:)?cNvPr\b[^>]*\bid="(\d+)"', new.text(nd))
    assert len(ids) == len(set(ids)) == 30                     # 4 charts + 26 shapes, no duplicate ids
    assert refreshed["report"]["shapes"] == 26


def test_typed_notes_return_to_the_row_with_the_same_date_or_event(old_model, refreshed):
    """A note belongs to a day or an event, not to a row number: the build may reorder the rows."""
    new = Package(refreshed["final"])
    parts = refresh.sheet_parts(new)
    ev = refresh.cells(new, parts["Px Events"])
    row = next(r for r, iso, name in refreshed["layout"]["event_rows"]
               if [iso, name] == refreshed["carry"]["notes"]["Px Events"][0]["key"])
    assert ev[f"S{row}"][1] == "My own note on this event"
    ic = refresh.cells(new, parts["Idio Chart"])
    carried = refreshed["carry"]["notes"]["Idio Chart"]
    assert len(carried) == 3
    by_date = {iso: r for r, iso in refreshed["layout"]["idio_rows"]}
    for n in carried:
        if n["key"][0] in by_date:
            assert ic[f"AB{by_date[n['key'][0]]}"][1] == n["note"]
    placed = refreshed["report"]["notes_placed"]
    assert placed + len(refreshed["report"]["notes_not_placed"]) == 4      # every note accounted for


def test_tabs_keep_their_places_and_nothing_else_changes(old_model, refreshed):
    """A rebuild appends tabs at the end; a refresh puts them back. Every part outside the three tabs is untouched."""
    old, new = Package(old_model), Package(refreshed["final"])
    assert [s[0] for s in new.sheets()] == [s[0] for s in old.sheets()]
    mine = refresh.tab_parts(old) | refresh.tab_parts(new)
    allowed = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml",
               "xl/calcChain.xml", "docProps/app.xml"}
    changed = [p for p in old.parts if p not in allowed | mine and old.parts[p] != new.parts.get(p)]
    assert changed == []


def test_range_that_ends_at_the_old_last_row_is_a_warning(refreshed):
    """Research averages 'Px Data'!$B$5:$B$3234: after five new days it misses them. Not wrong, but stale: say so."""
    w = refreshed["report"]["reference_warnings"]
    assert any("Research reads 'Px Data'!B5:B3234" in x and "miss the new days" in x for x in w)


def test_a_reference_to_a_moved_column_stops_the_refresh(reference_model, tmp_path):
    """The untouched reference model's Research tab averages old column O (TTM non-GAAP P/E); the lean layout moved
    it. A refresh would quietly feed those averages another column, so it must stop and name the cells."""
    w = tmp_path / "w"
    w.mkdir()
    (tmp_path / "src").mkdir()
    _inputs(w, tmp_path / "src")
    m = str(tmp_path / "m.xlsx")
    shutil.copy(reference_model, m)
    _run("refresh.py", "extract", "--model", m, "--work", str(w))
    _run("build.py", "--model", m, "--work", str(w), "--out", str(tmp_path / "b.xlsx"), "--refresh")
    r = _run("refresh.py", "restore", "--model", m, "--built", str(tmp_path / "b.xlsx"), "--work", str(w),
             "--out", str(tmp_path / "f.xlsx"), check=False)
    assert r.returncode == 3 and not os.path.exists(tmp_path / "f.xlsx")
    stops = json.loads(r.stdout)["stops"]
    assert any("'Px Data'!O5:O3234: column O was 'P/E (TTM non-GAAP)'" in s and "Z15" in s for s in stops)


def test_single_cell_link_must_still_read_the_same_day():
    """Multiples and Consensus link single Px Data cells by row: the row must still hold the same date."""
    old = {"A1002": ("n", 45000.0, 45000.0), "A4": ("s", "Date", "Date")}
    same = refresh._row_key(old, "Px Data", 1002) == refresh._row_key(dict(old), "Px Data", 1002)
    moved = refresh._row_key(old, "Px Data", 1002) == refresh._row_key({"A1002": ("n", 45001.0, 45001.0)}, "Px Data", 1002)
    assert same and not moved


def test_a_note_whose_day_left_the_table_is_reported_not_dropped():
    placed, unplaced = refresh.place_notes([{"key": ["2020-03-16"], "note": "kept"},
                                            {"key": ["2019-01-02"], "note": "gone from the top 20"}],
                                           {("2020-03-16",): "AB7"})
    assert placed == {"AB7": "kept"} and [n["note"] for n in unplaced] == ["gone from the top 20"]


@pytest.mark.slow
def test_verify_passes_a_refresh_and_counts_the_shapes(old_model, refreshed):
    """The full gate (LibreOffice recalculation against the prototype, errors, byte-identity, tab order, shapes)."""
    r = _run("verify.py", "--before", old_model, "--built", refreshed["final"], "--work", str(refreshed["w"]),
             "--refresh", check=False)
    assert r.returncode == 0, r.stdout[-3000:]
    assert "your shapes carried back unchanged: 26 of 26" in r.stdout
