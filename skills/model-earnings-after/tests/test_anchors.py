"""Every quote the note and the Call Notes tab show must be on the line it cites, and every number the agent typed
(the long-term target) must be printed there: a misquote reaches the PM as the company's words."""
import copy
import json
import os
import subprocess
import sys

import anchors

HERE = os.path.dirname(__file__)
EX = json.load(open(os.path.join(HERE, "fixtures", "plan_example.json")))


def test_example_quotes_hold(fixture_research):
    assert anchors.check(EX, None, fixture_research, {}) == []


def test_misquote_is_caught(fixture_research):
    p = copy.deepcopy(EX)
    p["sfot"]["tone"]["quote"] = "We are worried about everything."
    assert any(x.startswith("sfot.tone") for x in anchors.check(p, None, fixture_research, {}))


def test_every_quoted_section_is_checked(fixture_research):
    """Call notes, guidance and the long-term target are quoted on the tab too; each must be checked."""
    p = copy.deepcopy(EX)
    p["call_notes"]["Tone"][0]["anchor"] = "Earnings Calls/_md/2026 Q4 TEST call.md:3"
    p["guidance"][0]["quote"] = "We expect 2027 revenue of $700 million."
    probs = anchors.check(p, None, fixture_research, {})
    assert any(x.startswith("call_notes.Tone[0]") for x in probs)
    assert any(x.startswith("guidance[0]") for x in probs)


def test_unprinted_number_is_caught(fixture_research):
    p = copy.deepcopy(EX)
    p["lt_target"]["anchor_value"] = 25
    assert any(x.startswith("lt_target") for x in anchors.check(p, None, fixture_research, {}))


def test_percent_target_reads_either_way(fixture_research):
    """The line prints '20%': 0.20 (the fraction the pace math uses) and 20 both match it."""
    for v in (0.20, 20):
        p = copy.deepcopy(EX)
        p["lt_target"]["anchor_value"] = v
        assert anchors.check(p, None, fixture_research, {}) == []


def test_cli_reads_the_research_root_from_context(fixture_research, tmp_path):
    """SKILL.md runs anchors.py with the context only: the research root must come from context.json."""
    pp, cp = str(tmp_path / "p.json"), str(tmp_path / "c.json")
    json.dump(EX, open(pp, "w"))
    json.dump({"ticker": "TEST", "research": fixture_research}, open(cp, "w"))
    s = os.path.join(HERE, "..", "scripts", "anchors.py")
    r = subprocess.run([sys.executable, "-I", s, "--plan", pp, "--context", cp], capture_output=True, text=True)
    assert r.returncode == 0 and "anchors OK" in r.stdout, r.stdout + r.stderr
