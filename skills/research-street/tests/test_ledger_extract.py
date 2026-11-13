import json, os

import ledger_extract
from fixtures import GAPS_MD, MOVES_MD, make_src


def test_gaps_numbered_with_groups_and_stop_at_part_b():
    g = ledger_extract.gaps(GAPS_MD)
    assert [x["n"] for x in g] == [1, 2, 3]
    assert g[0]["group"] == "Driver 1: active customer base (volume)" and g[2]["group"] == "Driver 2: revenue per customer"
    assert g[0]["title"] == "Quarterly customer base" and "annual totals" in g[0]["text"]


def test_turning_points_first_table_only_bullets_for_no_event_and_no_callouts():
    t = ledger_extract.turning_points(MOVES_MD)
    assert [x["date"] for x in t] == [None, "2024-07-25", "2023-07-28", None]
    assert [x["major"] for x in t] == [False, True, False, False]
    assert [x["kind"] for x in t] == ["event", "event", "no-event", "no-event"]
    assert t[2]["event"] == "July to October 2023"
    assert t[1]["event"] == "Q2 2024 (2024-07-25)"


def test_main_writes_three_files(tmp_path):
    src = make_src(str(tmp_path))
    n = ledger_extract.extract(src)
    w = os.path.join(src, "Street Research", "_work")
    assert n == (3, 4)
    text = open(os.path.join(w, "phase1_extract.md")).read()
    assert "<!-- Filings research file: 15-gaps.md -->" in text and "16-appendix" not in text
    assert len(json.load(open(os.path.join(w, "gaps.json")))) == 3


def test_no_gaps_is_an_error(tmp_path):
    src = make_src(str(tmp_path))
    open(os.path.join(src, "Filings Research", "sections", "15-gaps.md"), "w").write("## 15 Gaps\n\nNone.\n")
    try:
        ledger_extract.extract(src)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "no numbered gaps" in str(e)


def test_the_eight_section_phase_1_layout_is_found_by_name(tmp_path):
    # The filings research moved to 8 sections (2026-11-09): gaps in 08-gaps.md, big moves in 07-stock.md
    src = make_src(str(tmp_path))
    d = os.path.join(src, "Filings Research", "sections")
    for old, new in (("15-gaps.md", "08-gaps.md"), ("12-stock-vs-drivers.md", "07-stock.md")):
        if os.path.exists(os.path.join(d, old)):
            os.rename(os.path.join(d, old), os.path.join(d, new))
    assert ledger_extract.extract(src) == (3, 4)
