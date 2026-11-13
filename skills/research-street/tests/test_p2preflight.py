import json, os

import p2preflight
from fixtures import SELLSIDE, make_src


def test_stop_without_phase1(tmp_path):
    src = make_src(str(tmp_path), phase1=False)
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "stop" and "research-filings" in r["missing"][0]["fix"]


def test_stop_when_sellside_markdown_missing(tmp_path):
    src = make_src(str(tmp_path))
    os.remove(os.path.join(src, "Sellside Research", "_md", list(SELLSIDE)[0] + ".md"))
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "stop" and "collect-documents" in r["missing"][0]["fix"]


def test_ok_writes_run_json_with_groups(tmp_path):
    src = make_src(str(tmp_path))
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "ok"
    run = json.load(open(os.path.join(src, "Street Research", "_work", "run.json")))
    assert run["phase1_as_of"] == "2026-10-29" and run["as_of"] == "2026-11-09"
    labels = [l for g in run["groups"] for l in g["labels"]]
    assert sorted(labels) == sorted(SELLSIDE)                 # every report in exactly one group
    assert [g["id"] for g in run["groups"]][0] == "s1"


def test_groups_split_on_words_and_file_count():
    items = [{"label": f"r{i}", "words": 6000} for i in range(5)]
    g = p2preflight.groups(items)
    assert [x["labels"] for x in g] == [["r0", "r1"], ["r2", "r3"], ["r4"]]   # 15,000-word cap
    small = [{"label": f"r{i}", "words": 100} for i in range(5)]
    assert [len(x["labels"]) for x in p2preflight.groups(small)] == [4, 1]       # 4-file cap


def test_warns_on_company_documents_newer_than_phase1(tmp_path):
    newer = {"call:2026Q4": {"category": "Earnings Calls", "label": "2026 Q4 DXCM call", "status": "found", "files": []}}
    src = make_src(str(tmp_path), extra_items=newer)
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "warn" and r["newer_docs"] == ["2026 Q4 DXCM call"]


def test_empty_sellside_folder_warns_web_only(tmp_path):
    src = make_src(str(tmp_path), sellside={})
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "warn" and r["sellside"] == 0


def test_stop_when_new_sellside_pdf_not_registered(tmp_path):
    src = make_src(str(tmp_path))
    open(os.path.join(src, "Sellside Research", "2026-11-05 GS note - New.pdf"), "wb").write(b"%PDF")
    open(os.path.join(src, "Sellside Research", list(SELLSIDE)[0] + ".pdf"), "wb").write(b"%PDF")   # registered: fine
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "stop"
    assert r["missing"][0]["fix"] == "Run /collect-documents DXCM to file and convert the new sell-side PDFs."
    assert "2026-11-05 GS note - New.pdf" in r["missing"][0]["what"]


def test_stop_when_unregistered_pdf_sits_in_a_tier_folder(tmp_path):
    # The user may drop a PDF straight into a tier folder; it still has to be filed and converted first.
    src = make_src(str(tmp_path))
    os.makedirs(os.path.join(src, "Sellside Research", "3 Independent Analysis"))
    open(os.path.join(src, "Sellside Research", "3 Independent Analysis", "sa.pdf"), "wb").write(b"%PDF")
    r = p2preflight.run("DXCM", src, "2026-11-09")
    assert r["status"] == "stop" and "sa.pdf" in r["missing"][0]["what"]
