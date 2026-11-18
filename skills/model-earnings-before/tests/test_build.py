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
