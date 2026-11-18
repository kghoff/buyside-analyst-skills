# skills/model-short/tests/test_build.py
"""The tab is written without touching anything else in the workbook, in the house colours, and a rerun keeps the
user's own values. No LibreOffice here: test_recalc does the one recalculation."""
import json
import os
import shutil
import zipfile

import openpyxl
import pytest

import build


@pytest.fixture
def built(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    res = build.build(model, work, "TEST", out)
    return model, work, out, res


def test_only_the_new_tab_and_workbook_parts_change(built):
    model, work, out, res = built
    assert res["changed_parts"] == []
    assert "Short Check" in openpyxl.load_workbook(out, read_only=True).sheetnames
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    for n in a.namelist():
        if n.startswith("xl/worksheets/sheet") and n in b.namelist() and "Short" not in n:
            assert a.read(n) == b.read(n) or n == build.tab_part(out)


def test_colours_follow_the_house_rules(built):
    _, work, out, _ = built
    lay = json.load(open(os.path.join(work, "layout.json")))
    ws = openpyxl.load_workbook(out)["Short Check"]
    want = {"typed": "FF0000FF", "link": "FF008000", "formula": "FF000000", "input": "FF0000FF"}
    for ref, kind in lay["kinds"].items():
        if kind in want:
            assert ws[ref].font.color.rgb == want[kind], (ref, kind)
        if kind == "input":
            assert ws[ref].fill.fgColor.rgb == "FFFFFF00" and ws[ref].comment is not None, ref
        if kind == "typed":
            assert ws[ref].comment is not None, ref           # every typed number names its source


def test_expected_values_come_from_shortmath(built):
    _, work, _, _ = built
    lay = json.load(open(os.path.join(work, "layout.json")))
    r = lay["refs"]
    assert lay["expected"][r["verdict_rule"]] == "Filler short"
    assert lay["expected"][r["max_pos"].replace("$", "")] == pytest.approx(5.0 / lay["expected"][r["risk"].replace("$", "")])


def test_unknown_borrow_says_check_with_pb_and_a_rate_is_used(model, work, tmp_path):
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Short Check"]
    lay = json.load(open(os.path.join(work, "layout.json")))
    assert ws[lay["refs"]["borrow"].replace("$", "")].value == "check with PB"
    build.build(model, work, "TEST", out, borrow=0.03)
    ws = openpyxl.load_workbook(out)["Short Check"]
    assert ws[lay["refs"]["borrow"].replace("$", "")].value == 0.03


def test_rerun_keeps_the_users_change(model, work, tmp_path):
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    lay = json.load(open(os.path.join(work, "layout.json")))
    wb = openpyxl.load_workbook(out)                      # a test copy, never a user's model
    wb["Short Check"][lay["refs"]["hurdle"].replace("$", "")] = 0.10
    wb.save(out)
    shutil.copy(out, model)
    out2 = str(tmp_path / "o2.xlsx")
    res = build.build(model, work, "TEST", out2)
    assert "IRR hurdle" in res["users_kept"]
    assert openpyxl.load_workbook(out2)["Short Check"][lay["refs"]["hurdle"].replace("$", "")].value == 0.10


def test_unverified_inputs_are_marked(model, work, tmp_path):
    json.dump(["reward_eps"], open(os.path.join(work, "unverified.json"), "w"))
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    ws = openpyxl.load_workbook(out)["Short Check"]
    lay = json.load(open(os.path.join(work, "layout.json")))
    row = lay["refs"]["reward_eps"].split("$")[-1]
    assert ws[f"G{row}"].value.startswith("UNVERIFIED")


def test_a_tick_typed_over_a_code_formula_survives_a_rerun(model, work, tmp_path):
    """The user's ✗ over code's ✓ is their call: a rerun keeps it, and the verdict math counts it. The other code
    tick formulas must read back as code's (not as the user's), or every rerun would freeze them."""
    out = str(tmp_path / "o.xlsx")
    build.build(model, work, "TEST", out)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    lay = json.load(open(os.path.join(work, "layout.json")))
    ref = lay["refs"]["tick_decel"].replace("$", "")
    assert lay["kinds"][ref] == "formula" and lay["expected"][ref] == "✓"
    wb = openpyxl.load_workbook(out)                      # a test copy, never a user's model
    wb["Short Check"][ref] = "✗"
    wb.save(out)
    shutil.copy(out, model)
    res = build.build(model, work, "TEST", str(tmp_path / "o2.xlsx"))
    lab = dict((rid, lab) for rid, _, lab, _ in build.sm.ROWS)["decel"]
    assert res["users_kept"] == [lab]
    ws = openpyxl.load_workbook(str(tmp_path / "o2.xlsx"))["Short Check"]
    assert ws[ref].value == "✗"
    lay2 = json.load(open(os.path.join(work, "layout.json")))
    assert lay2["summary"]["ticks"]["decel"] == "no"
    assert lay2["expected"][lay2["refs"]["count_F"].replace("$", "")] == lay["expected"][lay["refs"]["count_F"].replace("$", "")] - 1


def test_build_stops_and_deletes_out_if_another_part_changed(model, work, tmp_path, monkeypatch):
    """Every part but the workbook-level ones and this tab's own must stay byte-identical; if not, no file is left."""
    real = build.write_tab

    def meddle(pkg, w):
        other = next(s[3] for s in pkg.sheets() if s[0] == "MOD")
        pkg.put(other, pkg.parts[other] + b" ")
        return real(pkg, w)
    monkeypatch.setattr(build, "write_tab", meddle)
    out = str(tmp_path / "o.xlsx")
    with pytest.raises(SystemExit, match="must not touch"):
        build.build(model, work, "TEST", out)
    assert not os.path.exists(out)
