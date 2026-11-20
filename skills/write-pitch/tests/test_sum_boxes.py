"""sum_boxes.py writes only the SUM boxes write-pitch owns, never over what the user typed, and verify.py proves no
other part of the user's model moved. Every workbook here is a throwaway built in tmp_path (never a live model)."""
import ast
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

import openpyxl
import pytest
from openpyxl.styles import PatternFill

import sum_boxes
import verify

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
PLAN = HERE / "fixtures" / "plan_example.json"
LAYOUT = HERE.parents[1] / "model-summary" / "scripts" / "layout.py"
YELLOW = "FFFFFF00"
# label cells where model-summary's layout puts them for a 9-year grid; the input cell is INPUT_OFFSET away
LABELS = {"Buy price": "B19", "No-brainer price": "B20", "Mgmt contact": "B55", "Thesis Summary": "E30",
          "Trading Plan": "E42", "Valuation Thoughts": "P40"}


def box_ref(label):
    c, r = sum_boxes.split_ref(LABELS[label])
    dc, dr = sum_boxes.INPUT_OFFSET[label]
    return sum_boxes.ref_of(c + dc, r + dr)


def make_model(path, typed=None, bare=()):
    """A small model: MOD with numbers, SUM with the six labelled yellow boxes (empty unless typed) and the
    model-summary formula that reads the buy price."""
    wb = openpyxl.Workbook()
    mod = wb.active
    mod.title = "MOD"
    for r in range(1, 6):
        mod.cell(row=r, column=1, value=f"Line {r}")
        mod.cell(row=r, column=2, value=r * 10.5)
    s = wb.create_sheet("SUM", 0)
    s["B7"], s["C7"] = "Price (date beside it)", 80.0
    s["D19"] = '=IF(ISNUMBER(C19),C19/$C$7-1,"")'
    for label, at in LABELS.items():
        s[at] = label
        if label not in bare:                                       # bare: the box cell has no XML element
            s[box_ref(label)].fill = PatternFill("solid", fgColor=YELLOW)
    s.merge_cells("E31:N40")
    for label, v in (typed or {}).items():
        s[box_ref(label)] = v
    wb.save(path)
    return str(path)


@pytest.fixture
def sum_model(tmp_path):
    return make_model(tmp_path / "XYZ_model.xlsx", {"Trading Plan": "my own plan"})


@pytest.fixture
def sum_model_written_before(tmp_path):
    m = make_model(tmp_path / "XYZ_model.xlsx", {"Thesis Summary": "Old thesis from the last run.",
                                                 "Trading Plan": "my own plan"})
    (tmp_path / "record_from_last_run.json").write_text(json.dumps(
        {"Thesis Summary": {"cell": box_ref("Thesis Summary"), "value": "Old thesis from the last run."}}))
    return m


def run_sum_boxes(tmp_path, model, record=None, plan=PLAN):
    work = tmp_path / "_model_work" / "write-pitch"
    work.mkdir(parents=True, exist_ok=True)
    rec = work / "sum_written.json"
    if record:
        shutil.copyfile(tmp_path / record, rec)
    out = work / "out.xlsx"
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sum_boxes.py"), "--model", model, "--plan", str(plan),
                        "--record", str(rec), "--out", str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return str(out), json.loads(p.stdout)


def run_verify(before, after, expect=None):
    cmd = [sys.executable, "-I", str(SCRIPTS / "verify.py"), "--before", before, "--after", after]
    return subprocess.run(cmd + (["--expect", expect] if expect else []), capture_output=True, text=True).returncode


def read_cell(path, tab, label):
    wb = openpyxl.load_workbook(path)
    return wb[tab][box_ref(label)].value


def raw_cell(path, ref):
    """The <c> element for ref in SUM's sheet XML (to see its style and storage)."""
    z = zipfile.ZipFile(path)
    part = {s[0]: s[3] for s in sum_boxes.Package(path).sheets()}["SUM"]
    _, cells = verify.cells_of(z.read(part).decode())
    return cells[ref][1]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_empty_box_written_typed_box_kept(tmp_path, sum_model):
    out, rep = run_sum_boxes(tmp_path, sum_model, record=None)
    assert "Thesis Summary" in rep["written"] and "Trading Plan" in rep["kept"]
    assert read_cell(out, "SUM", "Trading Plan") == "my own plan"
    assert read_cell(out, "SUM", "Thesis Summary") == "Growth holds, margins expand, cash returns rise."


def test_box_still_equal_to_last_write_is_refreshed(tmp_path, sum_model_written_before):
    out, rep = run_sum_boxes(tmp_path, sum_model_written_before, record="record_from_last_run.json")
    assert "Thesis Summary" in rep["written"]
    assert read_cell(out, "SUM", "Thesis Summary") == "Growth holds, margins expand, cash returns rise."


def test_box_the_user_edited_after_our_write_is_kept(tmp_path, sum_model_written_before):
    # the record says we wrote one thing, the cell now holds another: the user rewrote it, so it is theirs
    (tmp_path / "rec.json").write_text(json.dumps({"Thesis Summary": {"cell": "E31", "value": "What we wrote."}}))
    out, rep = run_sum_boxes(tmp_path, sum_model_written_before, record="rec.json")
    assert "Thesis Summary" in rep["kept"]
    assert read_cell(out, "SUM", "Thesis Summary") == "Old thesis from the last run."


def test_other_parts_byte_identical(tmp_path, sum_model):
    out, rep = run_sum_boxes(tmp_path, sum_model, record=None)
    assert run_verify(sum_model, out) == 0
    expect = tmp_path / "rep.json"
    expect.write_text(json.dumps(rep))
    assert run_verify(sum_model, out, str(expect)) == 0
    assert run_verify(sum_model, out, str(tmp_path / "_model_work" / "write-pitch" / "sum_written.next.json")) == 0


def test_prices_written_as_numbers(tmp_path, sum_model):
    # SUM's "% vs price" formula is IF(ISNUMBER(C19),...): a price stored as text would silently show blank
    out, rep = run_sum_boxes(tmp_path, sum_model)
    numbers = json.loads(PLAN.read_text())["numbers"]
    for label, key in (("Buy price", "buy_price"), ("No-brainer price", "nobrainer_price")):
        v = read_cell(out, "SUM", label)
        assert isinstance(v, float) and v == numbers[key]["value"]
        assert rep["cells"][label] == {"cell": box_ref(label), "value": numbers[key]["value"]}


def test_placeholders_substituted_with_shown(tmp_path, sum_model):
    # text never carries a typed number: {key} becomes numbers[key].shown, the form the deck prints
    out, _ = run_sum_boxes(tmp_path, sum_model)
    assert read_cell(out, "SUM", "Valuation Thoughts") == "Target $130 in three years, IRR 21.5%."


def test_null_box_skipped_and_untouched(tmp_path):
    m = make_model(tmp_path / "XYZ_model.xlsx", {"Mgmt contact": "CFO, met at conference"})
    before = raw_cell(m, box_ref("Mgmt contact"))
    out, rep = run_sum_boxes(tmp_path, m)
    assert rep["skipped_null"] == ["Mgmt contact"]
    assert raw_cell(out, box_ref("Mgmt contact")) == before


def test_yellow_style_survives(tmp_path, sum_model):
    # the yellow fill says "an input you own"; a write that dropped the style would make the box look computed
    out, rep = run_sum_boxes(tmp_path, sum_model)
    for label in rep["written"]:
        ref = box_ref(label)
        assert verify.style(raw_cell(out, ref)) == verify.style(raw_cell(sum_model, ref)) is not None
        assert openpyxl.load_workbook(out)["SUM"][ref].fill.fgColor.rgb == YELLOW


def test_model_never_written(tmp_path, sum_model):
    before = sha(sum_model)
    run_sum_boxes(tmp_path, sum_model)
    assert sha(sum_model) == before


def test_out_must_not_be_the_model(tmp_path, sum_model):
    with pytest.raises(SystemExit):
        sum_boxes.run(sum_model, str(PLAN), None, sum_model)


def test_verify_fails_when_another_part_changed(tmp_path, sum_model):
    out, _ = run_sum_boxes(tmp_path, sum_model)
    bad = tmp_path / "tampered.xlsx"
    with zipfile.ZipFile(out) as zi, zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zo:
        for i in zi.infolist():
            data = zi.read(i.filename)
            if i.filename == "xl/worksheets/sheet2.xml":            # MOD (SUM was created first in tab order)
                data = data.replace(b"<v>10.5</v>", b"<v>99</v>")
                assert b"<v>99</v>" in data
            zo.writestr(i, data)
    assert run_verify(sum_model, str(bad)) == 1


def test_verify_fails_when_an_unreported_sum_cell_changed(tmp_path, sum_model):
    out, rep = run_sum_boxes(tmp_path, sum_model)
    rep["cells"].pop("Thesis Summary")                               # pretend sum_boxes never wrote it
    expect = tmp_path / "rep.json"
    expect.write_text(json.dumps(rep))
    assert run_verify(sum_model, out, str(expect)) == 1


def test_rerun_on_own_output_refreshes_ours_and_keeps_users(tmp_path, sum_model):
    # second run reads inline strings and numbers it wrote itself; with the promoted record they are still ours
    out, _ = run_sum_boxes(tmp_path, sum_model)
    work = tmp_path / "_model_work" / "write-pitch"
    shutil.move(work / "sum_written.next.json", work / "sum_written.json")
    model2 = tmp_path / "XYZ_model_v2.xlsx"
    shutil.copyfile(out, model2)
    nxt = json.loads((work / "sum_written.json").read_text())
    assert set(nxt) == {"Thesis Summary", "Valuation Thoughts", "Buy price", "No-brainer price"}
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sum_boxes.py"), "--model", str(model2), "--plan",
                        str(PLAN), "--record", str(work / "sum_written.json"), "--out", str(work / "out2.xlsx")],
                       capture_output=True, text=True)
    rep = json.loads(p.stdout)
    assert sorted(rep["written"]) == sorted(nxt) and rep["kept"] == ["Trading Plan"]


def test_missing_label_reported_not_crash(tmp_path):
    m = make_model(tmp_path / "XYZ_model.xlsx")
    wb = openpyxl.load_workbook(m)
    wb["SUM"][LABELS["Valuation Thoughts"]] = None
    wb.save(m)
    out, rep = run_sum_boxes(tmp_path, m)
    assert rep["missing"] == ["Valuation Thoughts"] and "Thesis Summary" in rep["written"]


def test_offsets_match_model_summary_layout():
    # the boxes are found by label + offset; if model-summary moves a box relative to its label, this must follow
    tree = ast.parse(LAYOUT.read_text())
    node = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "INPUT_OFFSET" for t in n.targets))
    theirs = {k.value: ast.literal_eval(v) for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    assert {k: theirs[k] for k in sum_boxes.INPUT_OFFSET} == sum_boxes.INPUT_OFFSET
    assert set(sum_boxes.INPUT_OFFSET) == set(sum_boxes.common.SUM_BOXES)


def plan_with(tmp_path, **boxes):
    """plan_example.json with some sum_boxes replaced (a value of ... drops the box from the plan)."""
    P = json.loads(PLAN.read_text())
    for k, v in boxes.items():
        k = k.replace("_", " ")
        if v is ...:
            P["sum_boxes"].pop(k)
        else:
            P["sum_boxes"][k] = v
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(P))
    return p


def sum_part_rewrite(path, fn):
    """Rewrite SUM's sheet XML in place in a throwaway workbook (to fake what Excel or a tamper leaves)."""
    part = {s[0]: s[3] for s in sum_boxes.Package(path).sheets()}["SUM"]
    tmp = str(path) + ".tmp"
    with zipfile.ZipFile(path) as zi, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for i in zi.infolist():
            data = zi.read(i.filename)
            zo.writestr(i, fn(data.decode()).encode() if i.filename == part else data)
    shutil.move(tmp, path)


def test_stale_dimension_does_not_hide_a_typed_box(tmp_path, sum_model):
    # read-only openpyxl trusts <dimension>; one cut between a label and its box would make the user's text read as
    # empty and get overwritten
    sum_part_rewrite(sum_model, lambda x: re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1:P42"/>', x))
    out, rep = run_sum_boxes(tmp_path, sum_model)
    assert "Trading Plan" in rep["kept"]
    assert read_cell(out, "SUM", "Trading Plan") == "my own plan"


def test_box_left_out_of_plan_stays_on_record(tmp_path, sum_model_written_before):
    # a plan that omits a box must not forget we wrote it, or the next run would treat our text as the user's
    plan = plan_with(tmp_path, Thesis_Summary=...)
    run_sum_boxes(tmp_path, sum_model_written_before, record="record_from_last_run.json", plan=plan)
    nxt = json.loads((tmp_path / "_model_work" / "write-pitch" / "sum_written.next.json").read_text())
    assert nxt["Thesis Summary"]["value"] == "Old thesis from the last run."


def test_missing_label_stays_on_record(tmp_path):
    m = make_model(tmp_path / "XYZ_model.xlsx")
    wb = openpyxl.load_workbook(m)
    wb["SUM"][LABELS["Valuation Thoughts"]] = None
    wb.save(m)
    (tmp_path / "rec.json").write_text(json.dumps({"Valuation Thoughts": {"cell": "P41", "value": "Ours."}}))
    run_sum_boxes(tmp_path, m, record="rec.json")
    nxt = json.loads((tmp_path / "_model_work" / "write-pitch" / "sum_written.next.json").read_text())
    assert nxt["Valuation Thoughts"] == {"cell": "P41", "value": "Ours."}


def test_line_breaks_normalised(tmp_path, sum_model):
    out, _ = run_sum_boxes(tmp_path, sum_model, plan=plan_with(tmp_path, Thesis_Summary="One.\r\nTwo.\rThree."))
    assert read_cell(out, "SUM", "Thesis Summary") == "One.\nTwo.\nThree."


@pytest.mark.parametrize("box, text, why", [
    ("Thesis_Summary", "=Valuation!C30 is the target", "formula"),
    ("Thesis_Summary", "bell\x07 here", "control characters"),
    # Excel holds at most 32,767 characters in a cell; a longer string makes it repair (truncate) the user's file
    pytest.param("Thesis_Summary", "x" * 32768, "32,767", id="over-the-cell-limit"),
])
def test_bad_text_stops(tmp_path, sum_model, box, text, why):
    with pytest.raises(SystemExit, match=why):
        sum_boxes.run(sum_model, str(plan_with(tmp_path, **{box: text})), None, str(tmp_path / "out.xlsx"))


def test_nan_price_stops(tmp_path, sum_model):
    # NaN would be written as <v>nan</v>: Excel calls the file corrupt
    P = json.loads(PLAN.read_text())
    P["numbers"]["buy_price"]["value"] = float("nan")
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(P))
    with pytest.raises(SystemExit, match="finite"):
        sum_boxes.run(sum_model, str(p), None, str(tmp_path / "out.xlsx"))


def test_calcpr_open_close_form_gets_full_calc():
    wb = '<workbook><sheets/><calcPr calcId="191029"></calcPr></workbook>'
    assert sum_boxes.full_calc_on_load(wb) == '<workbook><sheets/><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'


def test_no_record_warning_only_when_file_absent(tmp_path, sum_model):
    (tmp_path / "empty.json").write_text("{}")
    _, rep = run_sum_boxes(tmp_path, sum_model, record="empty.json")
    assert not any("No sum_written.json" in w for w in rep["warnings"])
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _, rep = run_sum_boxes(fresh, sum_model)
    assert any("No sum_written.json" in w for w in rep["warnings"])


def test_added_row_still_checks_other_rows(tmp_path):
    # the box cell (and its row) may have to be created; verify must still catch a change to any other row
    m = make_model(tmp_path / "XYZ_model.xlsx", bare=("Valuation Thoughts",))
    out, rep = run_sum_boxes(tmp_path, m)
    assert "Valuation Thoughts" in rep["written"]
    assert read_cell(out, "SUM", "Valuation Thoughts") == "Target $130 in three years, IRR 21.5%."
    assert run_verify(m, out) == 0
    sum_part_rewrite(out, lambda x: x.replace('<row r="19"', '<row r="19" ht="40" customHeight="1"', 1))
    assert run_verify(m, out) == 1
