# skills/model-short/tests/test_note.py
"""The note tells the user the verdict and every judgment call and flag (a call the user never hears about is the
worst outcome), with a table of contents after the cover."""
import json
import os

import build
import note


def test_note_has_cover_sections_and_every_call(model, work, tmp_path):
    build.build(model, work, "TEST", str(tmp_path / "o.xlsx"))
    md = open(note.write_md(work, "TEST", str(tmp_path), "2026-11-18")).read()
    assert '<div class="cover">' in md
    for h in ("## Verdict", "## FEV scorecard", "## Subpar-algorithm IRR wedge", "## Risk, sizing and borrow",
              "## Judgment calls and flags"):
        assert h in md, h
    assert "Filler short" in md and "Subpar algorithm" in md
    assert "check with PB" in md and "CFO change" in md          # unknown borrow and the smoke flag are told
    plan = json.load(open(os.path.join(work, "short_plan.json")))
    for k, x in plan["inputs"].items():
        assert x["reason"][:30] in md, k                          # every judgment's reason is in the note
    assert "| **Wedge** | **3.0%** |" in md                       # numbers read as the tab shows them
    assert "Reward price / reward | $44.00 / 13.7% |" in md
