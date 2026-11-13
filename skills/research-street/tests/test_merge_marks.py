import json, os

import merge_marks
from p2common import LEDGER_COLS, MARK_COLS, read_csv, write_csv

LEDGER = [{"id": "D2-01", "topic": "driver2", "claim": "c", "phase1_cite": "", "phase1_section": "10.2"},
          {"id": "D1-01", "topic": "driver1", "claim": "c", "phase1_cite": "", "phase1_section": "10.1"},
          {"id": "G1", "topic": "gap", "claim": "q1", "phase1_cite": "", "phase1_section": "15"},
          {"id": "G2", "topic": "gap", "claim": "q2", "phase1_cite": "", "phase1_section": "15"},
          {"id": "G3", "topic": "gap", "claim": "q3", "phase1_cite": "", "phase1_section": "15"}]


def m(cid, stance, ht="sell-side", tier="", src="S, p1"):
    return {"claim_id": cid, "stance": stance, "view": "v", "reasoning": "r", "holder": "h", "holder_type": ht,
            "tier": tier, "date": "2026-10-01", "source": src}


def test_merge(tmp_path):
    w = tmp_path / "Street Research" / "_work"
    write_csv(str(w / "ledger.csv"), LEDGER_COLS, LEDGER)
    json.dump([{"n": 1, "group": "Driver 1", "title": "Base"}, {"n": 2, "group": "Driver 1", "title": "Churn"},
               {"n": 3, "group": "Driver 2", "title": "Price"}], open(w / "gaps.json", "w"))
    write_csv(str(w / "readers" / "s1" / "marks.csv"), MARK_COLS,
              [m("D2-01", "agrees"), m("D2-01", "differs"), m("NEW", "adds")])
    write_csv(str(w / "research" / "r1" / "marks.csv"), MARK_COLS,
              [m("G1", "gap-closed", "official", "primary", "CMS, 2026-01-01, https://cms.gov/x"),
               m("G2", "gap-closed", "sell-side", "opinion")])
    merge_marks.merge(str(tmp_path))
    _, led = read_csv(str(w / "ledger_marked.csv"))
    by = {r["id"]: r for r in led}
    assert by["D2-01"]["marks_summary"] == "differs" and by["D2-01"]["agrees"] == "1"
    assert by["D1-01"]["marks_summary"] == "no outside view"
    _, gaps = read_csv(str(w / "gap_status.csv"))
    assert [(g["n"], g["status"], g["best_tier"]) for g in gaps] == [
        ("1", "closed-fact", "primary"), ("2", "estimate-only", "opinion"), ("3", "open", "")]
    _, allm = read_csv(str(w / "marks_all.csv"))
    assert {r["by"] for r in allm} == {"s1", "r1"} and len(allm) == 5
    _, mat = read_csv(str(w / "stance_matrix.csv"))
    assert {"topic": "driver2", "holder_type": "sell-side", "stance": "differs", "count": "1"} in mat
    assert "NEW" in open(w / "new_views.md").read() or "adds" in open(w / "new_views.md").read()
