# skills/model-earnings-before/tests/test_variance.py
"""The gate must never overwrite what the user typed without asking, must not ask about its own earlier fill, and
the grid it writes must link our numbers to MOD and type only the consensus numbers a source prints."""
import os
import zipfile

import pytest

import make_fixture as mf
import variance as va
from xlsx import Package, Styles


def test_status_of_each_block(tmp_path):
    sk = va.inspect(mf.build(str(tmp_path / "a.xlsx")))
    assert sk["status"] == "skeleton" and sk["rows"] == list(range(22, 31)) and sk["header"] == 21
    d = va.inspect(mf.build(str(tmp_path / "b.xlsx"), variance="data"))
    assert d["status"] == "data" and d["filled"] == ["F22"]
    assert va.inspect(mf.build(str(tmp_path / "c.xlsx"), variance="none"))["status"] == "no_block"


def test_missing_consensus_tab(tmp_path):
    import openpyxl
    p = mf.build(str(tmp_path / "x.xlsx"))
    wb = openpyxl.load_workbook(p)
    del wb["Consensus"]
    wb.save(p)
    assert va.inspect(p)["status"] == "missing"


def test_grid_cells_link_ours_and_type_only_printed_consensus(work):
    import json
    ctx = json.load(open(os.path.join(work, "context.json")))
    s = mf.series()
    cells, dropped = va.grid_cells(ctx, list(range(22, 31)))
    qcol = ctx["mod"]["cols"]["q"]
    assert cells["B22"][:2] == ("s", "Revenue") and cells["B28"][:2] == ("s", "Units")
    assert cells["F22"][:2] == ("f", f"MOD!${qcol}$3") and cells["F22"][2] == pytest.approx(s["Q4 26E"]["rev"])
    assert cells["C22"][:2] == ("n", 140.0) and cells["C22"][3] == "typed"
    assert cells["F23"][2] == pytest.approx(0.12)                        # internal revenue growth Q4
    assert cells["C23"][2] == pytest.approx(140.0 / s["Q4 25"]["rev"] - 1)
    assert "C24" not in cells and "C26" not in cells                     # no free consensus for margins or FCF
    assert cells["C27"][:2] == ("n", 0.62) and cells["H27"][0] == "f"    # EPS
    assert "B29" not in cells and dropped == []                          # unused key-driver rows left as they are


def test_fill_writes_only_the_consensus_part_and_records_it(model, work, tmp_path):
    import json
    ctx = json.load(open(os.path.join(work, "context.json")))
    info = va.inspect(model)
    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    res = va.fill(pkg, st, ctx, info, force=False)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    out = str(tmp_path / "out.xlsx")
    pkg.save(out)
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    changed = [n for n in a.namelist() if a.read(n) != b.read(n)]
    assert set(changed) <= {res["part"], "xl/styles.xml", "[Content_Types].xml", "xl/workbook.xml"}
    assert va.inspect(out, written=res["written"])["status"] == "ours"
    assert va.inspect(out)["status"] == "data"


def test_force_overwrites_the_users_cell(tmp_path, work):
    import json
    ctx = json.load(open(os.path.join(work, "context.json")))
    p = mf.build(str(tmp_path / "d.xlsx"), variance="data")
    info = va.inspect(p)
    pkg = Package(p)
    st = Styles(pkg.text("xl/styles.xml"))
    keep = va.fill(pkg, st, ctx, info, force=False)
    assert "F22" in keep["skipped"]
    pkg = Package(p)
    st = Styles(pkg.text("xl/styles.xml"))
    assert va.fill(pkg, st, ctx, info, force=True)["skipped"] == []


def test_first_fill_on_the_skeleton_skips_nothing(model, work):
    """Labels that already read what the grid would write are not the user's words in the way: reporting them as
    skipped would put a false warning in front of the user on every first fill."""
    import json
    ctx = json.load(open(os.path.join(work, "context.json")))
    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    assert va.fill(pkg, st, ctx, va.inspect(model), force=False)["skipped"] == []


def _shared_fixture(path):
    """The user filled C22:C24 down in Excel: Excel stores one shared formula (master C22, children C23 and C24).
    openpyxl never writes shared formulas, so patch the sheet XML of a built fixture."""
    import re
    import openpyxl
    p = mf.build(path)
    wb = openpyxl.load_workbook(p)
    for r in (22, 23, 24):
        wb["Consensus"][f"C{r}"] = f"=D{r}*2"
    wb.save(p)
    pkg = Package(p)
    part = {s[0]: s for s in pkg.sheets()}["Consensus"][3]
    xml = pkg.text(part)
    xml = xml.replace("<f>D22*2</f>", '<f t="shared" ref="C22:C24" si="0">D22*2</f>')
    for r in (23, 24):
        xml = re.sub(rf"<f>D{r}\*2</f>", '<f t="shared" si="0"/>', xml)
    assert xml.count('t="shared"') == 3
    pkg.put(part, xml)
    pkg.save(p)
    return p, part


def test_force_fill_unshares_the_users_filled_down_formula(tmp_path, work):
    """Overwriting a shared formula's master leaves its children pointing at nothing: Excel then asks to repair the
    file. Every group the fill touches is written out cell by cell first; the cells it does not write keep their
    formula."""
    import json
    import re
    ctx = json.load(open(os.path.join(work, "context.json")))
    p, part = _shared_fixture(str(tmp_path / "s.xlsx"))
    info = va.inspect(p)
    pkg = Package(p)
    st = Styles(pkg.text("xl/styles.xml"))
    va.fill(pkg, st, ctx, info, force=True)
    xml = pkg.text(part)
    masters = set(re.findall(r'<f t="shared"[^>]*?ref="[^"]+"[^>]*?si="(\d+)"', xml))
    children = set(re.findall(r'<f t="shared" si="(\d+)"\s*/>', xml))
    assert children <= masters
    c24 = re.search(r'<c r="C24"[^>]*>.*?</c>', xml, re.S).group(0)
    assert "<f>D24*2</f>" in c24                                  # not written by the fill: same formula, now plain
