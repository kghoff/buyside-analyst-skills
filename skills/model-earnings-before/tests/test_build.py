# skills/model-earnings-before/tests/test_build.py
"""The tab is written without touching anything else in the workbook, in the house colours; the Consensus block is
filled only when it is the skeleton or our own (else the build stops and the user is asked); a rerun keeps the
user's own values and the forecast frozen for the same quarter. No LibreOffice here: test_recalc does the one
recalculation."""
import json
import os
import shutil
import zipfile

import openpyxl
import pytest

import build
import make_fixture as mf


def _find(ws, label):
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == label)


def _promote(work):
    for n in ("inputs_written", "variance_written"):
        p = os.path.join(work, f"{n}.next.json")
        if os.path.exists(p):
            os.replace(p, os.path.join(work, f"{n}.json"))


@pytest.fixture
def built(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    return model, work, out, build.build(model, work, "TEST", out, variance="consensus")


def test_only_the_new_tab_and_the_consensus_block_change(built):
    model, work, out, res = built
    assert res["changed_parts"] == [] and res["variance"]["where"] == "consensus"
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    mine = {build.tab_part(out), build.sheet_part(out, "Consensus")}
    for n in a.namelist():
        if n.startswith("xl/worksheets/sheet") and n not in mine:
            assert a.read(n) == b.read(n), n


def test_house_colours(built):
    _, _, out, _ = built
    ws = openpyxl.load_workbook(out)["Earnings"]
    st = ws.cell(_find(ws, build.LABEL["stance"]), 2)
    assert st.fill.fgColor.rgb == "FFFFFF00" and st.font.color.rgb == "FF0000FF"      # input: blue on yellow
    assert ws.cell(_find(ws, "Price"), 2).font.color.rgb == "FF0000FF"                 # typed
    assert ws.cell(_find(ws, "P/E percentile, last 5 years (Multiples)"), 2).font.color.rgb == "FF008000"   # link
    assert ws.cell(_find(ws, "Revenue"), 2).font.color.rgb == "FF000000"               # model-check formula


def test_consensus_block_filled_with_links_and_typed_means(built):
    _, _, out, res = built
    c = openpyxl.load_workbook(out)["Consensus"]
    assert str(c["F22"].value).startswith("=MOD!$") and c["C22"].value == 140.0
    assert c["L21"].value.startswith("Filled by /model-earnings-before")
    assert c["I22"].value.startswith("=IF(OR(C22")                                      # model-consensus's, untouched
    lay = json.load(open(os.path.join(built[1], "layout.json")))
    assert lay["expected_cons"]["F22"] == pytest.approx(mf.series()["Q4 26E"]["rev"])


def test_grid_on_the_earnings_tab_when_asked(model, work, tmp_path):
    out = str(tmp_path / "o.xlsx")
    res = build.build(model, work, "TEST", out, variance="earnings")
    assert res["variance"]["where"] == "earnings"
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    cp = build.sheet_part(model, "Consensus")
    assert a.read(cp) == b.read(cp)
    ws = openpyxl.load_workbook(out)["Earnings"]
    r = next(r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 1).value or "").startswith("6. VARIANCE GRID"))
    assert ws.cell(r + 1, 3).value == "Consensus Q4 26E" and ws.cell(r + 2, 1).value == "Revenue"


def test_users_own_variance_entries_stop_the_build_until_they_choose(tmp_path, work):
    m = mf.build(str(tmp_path / "d.xlsx"), variance="data")
    with pytest.raises(SystemExit, match="Ask the user"):
        build.build(m, work, "TEST", str(tmp_path / "o.xlsx"), variance="consensus")
    build.build(m, work, "TEST", str(tmp_path / "o2.xlsx"), variance="consensus", force_variance=True)
    assert str(openpyxl.load_workbook(str(tmp_path / "o2.xlsx"))["Consensus"]["F22"].value).startswith("=MOD!$")


def test_rerun_keeps_the_users_values_and_does_not_ask_about_its_own_fill(built, tmp_path):
    _, work, out, _ = built
    _promote(work)
    m2 = str(tmp_path / "m2.xlsx")                      # a test workbook: the user's edits, saved by openpyxl
    wb = openpyxl.load_workbook(out)
    ws = wb["Earnings"]
    ws.cell(_find(ws, build.LABEL["stance"]), 2).value = "add"
    ws.cell(_find(ws, build.LABEL["up_pe"]), 2).value = 19.5
    wb.save(m2)
    res = build.build(m2, work, "TEST", str(tmp_path / "o2.xlsx"), variance="consensus")
    assert build.LABEL["stance"] in res["users_kept"] and build.LABEL["up_pe"] in res["users_kept"]
    assert res["variance"]["status"] == "ours"
    ws2 = openpyxl.load_workbook(str(tmp_path / "o2.xlsx"))["Earnings"]
    assert ws2.cell(_find(ws2, build.LABEL["stance"]), 2).value == "add"
    assert res["stance_rule"] in ("hold", "hedge", "add", "trim")


def test_frozen_forecast_kept_for_the_same_quarter(built, tmp_path):
    _, work, out, _ = built
    _promote(work)
    p = os.path.join(work, "context.json")
    ctx = json.load(open(p))
    for x in ctx["frozen"]:
        if x["label"] == "INCOME STATEMENT | Revenue":
            x["q"] = 1.0                                     # the forecast moved after the freeze
    json.dump(ctx, open(p, "w"))
    keep = build.build(out, work, "TEST", str(tmp_path / "k.xlsx"), variance="earnings")
    assert keep["frozen"]["kept"] is True
    ws = openpyxl.load_workbook(str(tmp_path / "k.xlsx"))["Earnings"]
    assert ws.cell(_find(ws, "INCOME STATEMENT | Revenue"), 2).value == pytest.approx(mf.series()["Q4 26E"]["rev"])
    new = build.build(out, work, "TEST", str(tmp_path / "n.xlsx"), variance="earnings", refreeze=True)
    assert new["frozen"]["kept"] is False
    ws = openpyxl.load_workbook(str(tmp_path / "n.xlsx"))["Earnings"]
    assert ws.cell(_find(ws, "INCOME STATEMENT | Revenue"), 2).value == 1.0


def test_rule_cell_and_the_agents_stance(built):
    _, work, _, res = built
    lay = json.load(open(os.path.join(work, "layout.json")))
    assert res["stance_rule"] == "hold" and res["stance_used"] == "hold"
    assert lay["expected"][lay["refs"]["rule"].replace("$", "")] == "hold"


def test_stale_variance_record_is_removed_when_this_run_fills_nothing(model, work, tmp_path):
    """A variance_written.next.json left by an earlier, unpromoted run must not be promoted after a run that wrote
    nothing on the Consensus tab: the gate would then call the user's later entries 'ours' and overwrite them."""
    stale = os.path.join(work, "variance_written.next.json")
    open(stale, "w").write('{"C22": 1}')
    build.build(model, work, "TEST", str(tmp_path / "o.xlsx"), variance="earnings")
    assert not os.path.exists(stale)


def test_report_date_typed_as_a_real_date(tmp_path):
    """The user types the announced date in Excel: it reads back as a datetime (or a serial number from a values
    copy). It must count as a date both in Python and on the tab, not become text."""
    import datetime as dt
    from tabkit import W
    from xlsx import Styles
    assert build._days(dt.datetime(2027, 2, 10), "2026-11-18") == 84
    assert build._days(dt.date(2027, 2, 10), "2026-11-18") == 84
    assert build._days(46428, "2026-11-18") == 84                        # Excel serial of 2027-02-10
    assert build._days("2027-02-10", "2026-11-18") == 84
    assert build._days("type the date", "2026-11-18") is None
    st = Styles(zipfile.ZipFile(mf.build(str(tmp_path / "d7.xlsx"))).read("xl/styles.xml").decode())
    w = W(st)
    w.input_("B5", "Report date", dt.datetime(2027, 2, 10), "General", "note")
    kind, val, _ = w.sh.cells[(5, 2)]
    assert (kind, val) == ("n", 46428) and w.fmt["B5"] == "yyyy-mm-dd"


def test_note_inputs_kept_in_layout_calc(built):
    """A user's formula in an input is worked at its recalculated value; note.py needs those values, not the
    formula text, so layout.json keeps them."""
    _, work, _, _ = built
    lay = json.load(open(os.path.join(work, "layout.json")))
    assert set(lay["calc"]["inputs"]) == set(build.em.AGENT_INPUTS)


def _no_labels(path):
    m = mf.build(path)
    wb = openpyxl.load_workbook(m)
    for r in range(22, 31):
        wb["Consensus"][f"B{r}"] = None
    wb.save(m)
    return m


def test_variance_block_without_rows_does_not_crash(work, tmp_path):
    m = _no_labels(str(tmp_path / "e.xlsx"))
    out = str(tmp_path / "o.xlsx")
    res = build.build(m, work, "TEST", out, variance="consensus", force_variance=True)
    assert res["variance"]["rows"] == []
    wb = openpyxl.load_workbook(out)
    texts = [c.value for row in wb[build.TAB].iter_rows() for c in row if isinstance(c.value, str)]
    assert any("the Consensus tab's variance block" in t for t in texts)


def _add_wrap(path):
    """Stand in for model-earnings-after: its title row and band 9 under the tab, and a Call Notes tab."""
    wb = openpyxl.load_workbook(path)
    ws = wb[build.TAB]
    r = ws.max_row + 2
    ws.cell(r, 1, "TEST after the print: Q4 26E (model-earnings-after, 2026-11-19)")
    ws.cell(r + 1, 1, "9. ACTUAL VS FROZEN: Q4 26E (test)")
    wb.create_sheet("Call Notes").cell(1, 1, "Call notes kept")
    wb.save(path)


def _col_a(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    a = [v for (v,) in wb[build.TAB].iter_rows(min_col=1, max_col=1, values_only=True) if isinstance(v, str)]
    names = wb.sheetnames
    wb.close()
    return a, names


def test_same_quarter_rerun_stops_before_clearing_the_wrap(model, work, tmp_path):
    """Bands 9-15 hold the after-print wrap: a same-quarter preview rerun would wipe it, so it stops and says how
    to bring it back, unless the user said to clear it. Call Notes is its own tab and survives either way."""
    out1 = str(tmp_path / "o1.xlsx")
    first = build.build(model, work, "TEST", out1, variance="earnings")
    assert first["after_cleared"] is False
    _promote(work)
    _add_wrap(out1)
    with pytest.raises(SystemExit, match=r"/model-earnings-after TEST --rebuild"):
        build.build(out1, work, "TEST", str(tmp_path / "o2.xlsx"), variance="earnings")
    assert not os.path.exists(tmp_path / "o2.xlsx")
    out3 = str(tmp_path / "o3.xlsx")
    res = build.build(out1, work, "TEST", out3, variance="earnings", clear_after=True)
    assert res["after_cleared"] is True
    a, names = _col_a(out3)
    assert not any(build.AFTER_RE.match(t) or "(model-earnings-after," in t for t in a)
    assert "Call Notes" in names


def test_new_quarter_clears_the_wrap_without_stopping(model, work, tmp_path):
    """A preview for the next quarter replaces last quarter's wrap (it lives on in the after-print note and Call
    Notes): no stop, but the result says it was cleared so the user is told."""
    out1 = str(tmp_path / "o1.xlsx")
    build.build(model, work, "TEST", out1, variance="earnings")
    _promote(work)
    _add_wrap(out1)
    p = os.path.join(work, "context.json")
    ctx = json.load(open(p))
    ctx["quarter"] = "Q1 27E"
    json.dump(ctx, open(p, "w"))
    out2 = str(tmp_path / "o2.xlsx")
    res = build.build(out1, work, "TEST", out2, variance="earnings")
    assert res["after_cleared"] is True and res["frozen"]["kept"] is False
    a, names = _col_a(out2)
    assert not any(build.AFTER_RE.match(t) for t in a)
    assert "Call Notes" in names
