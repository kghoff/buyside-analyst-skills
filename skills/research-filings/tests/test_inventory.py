import pytest

from common import doc_date
from fixtures import make_src
from inventory import build, summary


def test_outside_voices_never_enter_phase_1(tmp_path):
    # the filings research must form its own view before reading anyone else's: sell-side and letters are invisible to it
    src = make_src(str(tmp_path), [
        ("10-K:2024-12-31", "10-Ks", "TEST 2024 10-K", "Revenue grew.", "found"),
        ("sell:2026-01-01:x", "Sellside Research", "2026-01-01 Firm note", "Buy!", "found"),
        ("letter:2026-01-01:y", "Investor Letters", "2026-01-01 Fund letter", "We own it.", "found"),
    ])
    docs, skipped, _ = build(src)
    assert [d["label"] for d in docs] == ["TEST 2024 10-K"]
    assert skipped == []


def test_unknown_category_is_reported_not_silently_read_or_dropped(tmp_path):
    src = make_src(str(tmp_path), [("x:1", "Mystery Folder", "Something", "text", "found")])
    docs, skipped, _ = build(src)
    assert docs == []
    assert skipped[0][0] == "Something" and "unknown category" in skipped[0][1]
    assert "Mystery Folder" in summary(docs, skipped, [])


def test_missing_documents_are_not_listed(tmp_path):
    src = make_src(str(tmp_path), [("deck:2024Q1", "Investor Decks", "2024 Q1 TEST deck", None, "missing")])
    assert build(src)[0] == []


def test_duplicate_labels_are_refused_because_citations_name_files_by_label(tmp_path):
    src = make_src(str(tmp_path), [
        ("call:2024Q1", "Earnings Calls", "Same", "a", "found"),
        ("call:2024Q2", "Earnings Calls", "Same", "b", "found"),
    ])
    with pytest.raises(SystemExit, match="Same"):
        build(src)


def test_dates_order_documents_release_date_first_then_period_end():
    assert doc_date("10-K:2025-12-31", "DXCM 2025 10-K") == "2025-12-31"
    assert doc_date("ex:0001-26-1:x.htm", "2026 Q3 DXCM release 2026-10-29") == "2026-10-29"
    assert doc_date("deck:2026Q3", "2026 Q3 DXCM deck") == "2026-09-30"
    assert doc_date("proxy:2025-12-31", "DXCM 2025 proxy filed 2026-04-15") == "2026-04-15"


def test_registered_but_unsaved_documents_are_reported_as_gaps(tmp_path):
    src = make_src(str(tmp_path), [("call:2024Q1", "Earnings Calls", "2024 Q1 call", None, "deferred")])
    src_items = __import__("json").load(open(str(tmp_path / "_manifest.json")))
    src_items["items"]["call:2024Q1"]["reason"] = "transcript not yet published"
    __import__("json").dump(src_items, open(str(tmp_path / "_manifest.json"), "w"))
    docs, skipped, not_saved = build(src)
    assert docs == [] and not_saved == [("2024 Q1 call", "deferred", "transcript not yet published")]
    assert "2024 Q1 call: deferred - transcript not yet published" in summary(docs, skipped, not_saved)
