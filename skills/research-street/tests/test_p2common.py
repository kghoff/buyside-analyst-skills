import os

import p2common
from fixtures import SEMI, make_src


def test_phase1_scripts_importable_without_shadowing():
    import common, numcheck   # research-filings modules, found through p2common's sys.path entry
    assert common.__file__.startswith(p2common.P1_SCRIPTS)
    assert numcheck.__file__.startswith(p2common.P1_SCRIPTS)


def test_paths(tmp_path):
    s = str(tmp_path)
    assert p2common.work_dir(s) == os.path.join(s, "Street Research", "_work")
    assert p2common.p1_work(s) == os.path.join(s, "Filings Research", "_work")


def test_sellside_items_sorted_with_md_and_pdf(tmp_path):
    src = make_src(str(tmp_path))
    items = p2common.sellside_items(src)
    assert [i["date"] for i in items] == sorted(i["date"] for i in items)
    semi = next(i for i in items if i["label"] == SEMI)
    assert semi["md"].endswith(".md") and semi["pdf"].endswith(".pdf")
    assert all(i["label"] != "DXCM 2025 10-K" for i in items)   # company documents are not sell-side


def test_csv_roundtrip_handles_bom(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes("﻿a,b\n1,2\n".encode("utf-8"))
    header, rows = p2common.read_csv(str(p))
    assert header == ["a", "b"] and rows == [{"a": "1", "b": "2"}]
    p2common.write_csv(str(tmp_path / "y" / "z.csv"), ["a"], [{"a": "q", "b": "ignored"}])
    assert p2common.read_csv(str(tmp_path / "y" / "z.csv"))[1] == [{"a": "q"}]
