# skills/model-earnings-before/tests/test_note.py
"""The note tells the user the call, the rule, every set-up side, risk score and judgment call (a call the user never
hears about is the worst outcome), with numbers as the tab shows them and a cover the PDF puts a contents page after."""
import json
import os

import build
import note


def test_note_sections_and_calls(model, work, tmp_path):
    build.build(model, work, "TEST", str(tmp_path / "o.xlsx"), variance="consensus")
    md = open(note.write_md(work, "TEST", str(tmp_path), "2026-11-18")).read()
    assert '<div class="cover">' in md
    for h in ("## 1. Net", "## 2. Set-up", "## 3. Last quarter", "## 4. Since the last print", "## 5. Expectations",
              "## 6. Model checks", "## 7. Variance", "## 8. Risk / reward", "## 9. What this print will tell us",
              "## 10. Judgment calls and flags"):
        assert h in md, h
    assert "**hold** (the rule says **hold**)" in md
    assert "Hockey stick" in md and "Revenue" in md                       # the flag that fired, in plain English
    assert "estimated" in md                                              # the report date is an estimate
    plan = json.load(open(os.path.join(work, "earnings_plan.json")))
    for k, x in plan["inputs"].items():
        assert x["reason"][:30] in md, k
    for c in plan["judgment_calls"]:
        assert c in md
    assert "demand remains solid" in md and "Investor Events/_md/TEST 2026-11-10 conference.md:2" in md
    assert "On the Consensus tab" in md


def test_note_says_when_the_user_overrode_the_stance(model, work, tmp_path):
    build.build(model, work, "TEST", str(tmp_path / "o.xlsx"), variance="earnings")
    p = os.path.join(work, "layout.json")
    lay = json.load(open(p))
    lay["users"] = [build.LABEL["stance"]]
    lay["used"][build.LABEL["stance"]] = "add"
    json.dump(lay, open(p, "w"))
    md = open(note.write_md(work, "TEST", str(tmp_path), "2026-11-18")).read()
    assert "**add** (the rule says **hold**). **You changed this.**" in md
