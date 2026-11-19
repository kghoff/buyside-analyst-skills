"""Every quote the note and the Call Notes tab show must be on the line it cites, and every number the agent typed
(the long-term target, any figure in its reasons) must be printed in a source: a misquote reaches the PM as the
company's words, and an invented figure as a fact."""
import copy
import json
import os
import subprocess
import sys

import pytest

import anchors
import context
import make_fixture as mf

HERE = os.path.dirname(__file__)
EX = json.load(open(os.path.join(HERE, "fixtures", "plan_example.json")))
CALL = "Earnings Calls/_md/2026 Q4 TEST call.md"


@pytest.fixture
def work(model, fixture_research, tmp_path):
    """The work folder context.py writes for the fixture: context.json and context.md, as the agent gets them."""
    w = str(tmp_path / "w")
    os.makedirs(w)
    json.dump(mf.YAHOO, open(os.path.join(w, "yahoo_after.json"), "w"))
    context.run(model, w, "TEST", values=model, research=fixture_research, today="2027-02-28")
    return w


@pytest.fixture
def md(work):
    return open(os.path.join(work, "context.md")).read()


def _check(p, root, md):
    return anchors.check(p, None, root, {}, md)


def test_example_quotes_hold(fixture_research, md):
    assert _check(EX, fixture_research, md) == []


def test_misquote_is_caught(fixture_research, md):
    p = copy.deepcopy(EX)
    p["sfot"]["tone"]["quote"] = "We are worried about everything."
    assert any(x.startswith("sfot.tone") for x in _check(p, fixture_research, md))


def test_every_quoted_section_is_checked(fixture_research, md):
    """Call notes, guidance and the long-term target are quoted on the tab too; each must be checked."""
    p = copy.deepcopy(EX)
    p["call_notes"]["Tone"][0]["anchor"] = f"{CALL}:3"
    p["guidance"][0]["quote"] = "We expect 2027 revenue of $700 million."
    probs = _check(p, fixture_research, md)
    assert any(x.startswith("call_notes.Tone[0]") for x in probs)
    assert any(x.startswith("guidance[0]") for x in probs)


def test_unprinted_number_is_caught(fixture_research, md):
    p = copy.deepcopy(EX)
    p["lt_target"]["anchor_value"] = 25
    assert any(x.startswith("lt_target") for x in _check(p, fixture_research, md))


def test_percent_target_reads_either_way(fixture_research, md):
    """The line prints '20%': 0.20 (the fraction the pace math uses) and 20 both match it here; plan.py then
    insists target == anchor_value and, for a ratio, a fraction."""
    for v in (0.20, 20):
        p = copy.deepcopy(EX)
        p["lt_target"]["anchor_value"] = v
        assert _check(p, fixture_research, md) == []


def test_target_year_must_be_on_the_line(fixture_research, md):
    """'20% by 2028' and '20% by 2030' are different promises: the year is checked like the number."""
    p = copy.deepcopy(EX)
    p["lt_target"]["year"] = 2030
    assert any(x.startswith("lt_target.year") for x in _check(p, fixture_research, md))


def test_short_quote_is_rejected(fixture_research, md):
    """A two-word fragment ('revenue grew') is found on many lines and can mean anything."""
    p = copy.deepcopy(EX)
    p["sfot"]["surprise"]["quote"] = "Revenue grew"
    assert any(x.startswith("sfot.surprise") and "4 words" in x for x in _check(p, fixture_research, md))


def test_negation_and_curly_quotes(tmp_path):
    """Dropping the 'not' reverses the company's words; a curly apostrophe in the transcript is not a misquote."""
    root = str(tmp_path)
    open(os.path.join(root, "t.md"), "w").write(
        "We do not expect revenue growth to slow next year.\nWe don’t see any change – at all.\n")
    q = anchors._quote
    assert "drops a negation" in q("x", "t.md:1", "expect revenue growth to slow", root)
    assert q("x", "t.md:1", "do not expect revenue growth", root) is None
    assert q("x", "t.md:2", "We don't see any change - at all.", root) is None
    assert "drops a negation" in q("x", "t.md:2", "see any change - at", root)


def test_unbacked_number_is_caught(fixture_research, md):
    """A figure in a reason must come from context.md or the item's own cited line, never from the agent."""
    p = copy.deepcopy(EX)
    p["react"]["reason"] = "An 8.0% move is too small for a 12.5% target change, so we add on the print today."
    probs = _check(p, fixture_research, md)
    assert any(x.startswith("react.reason") and "12.5" in x for x in probs)
    assert not any("8.0" in x for x in probs)
    p = copy.deepcopy(EX)                                 # 14% is on surprise's own cited line (line 3)
    p["sfot"]["surprise"]["reason"] = "Revenue grew 14% and beat our frozen forecast by 4.0% in the quarter."
    assert _check(p, fixture_research, md) == []


def test_malformed_plan_is_listed_not_crashed(fixture_research, md):
    """anchors.py runs after plan.py, but a bad shape must still come back as problems the agent can fix."""
    assert _check(["not", "a", "plan"], fixture_research, md)[0].startswith("plan:")
    p = copy.deepcopy(EX)
    p["sfot"] = "positive"
    p["call_notes"]["Tone"] = ["a string"]
    p["guidance"] = {"item": "x"}
    p["lt_target"] = "20%"
    p["react"] = None
    assert _check(p, fixture_research, md) == []


def test_cli_reads_research_root_and_context_md(work, tmp_path):
    """SKILL.md runs anchors.py with the context only: the research root comes from context.json and the free-text
    figures are checked against the context.md beside it."""
    pp = str(tmp_path / "p.json")
    json.dump(EX, open(pp, "w"))
    s = os.path.join(HERE, "..", "scripts", "anchors.py")
    cmd = [sys.executable, "-I", s, "--plan", pp, "--context", os.path.join(work, "context.json")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0 and "anchors OK" in r.stdout, r.stdout + r.stderr
    bad = copy.deepcopy(EX)
    bad["headline"] = "Revenue beat by 9.9% and a first 2027 guide; margin missed."
    json.dump(bad, open(pp, "w"))
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 1 and "the number 9.9" in r.stdout


def test_guidance_and_call_note_figures_need_a_source(fixture_research, md):
    """Guidance before / now and the call-note text are typed into the model (band 14, the Call Notes tab) as the
    company's numbers: a figure no source prints would reach the PM as guidance the company never gave."""
    p = copy.deepcopy(EX)
    p["guidance"][0]["before"] = "$999 million"
    p["guidance"][0]["now"] = "$777-788 million"
    p["call_notes"]["Capital allocation"][0]["text"] = "Bought back $555 million, up 31%."
    probs = _check(p, fixture_research, md)
    assert any(x.startswith("guidance[0].before:") and "999" in x for x in probs)
    assert any(x.startswith("guidance[0].now:") and "777" in x for x in probs)
    assert any(x.startswith("guidance[0].now:") and "788" in x for x in probs)
    cn = [x for x in probs if x.startswith("call_notes.Capital allocation[0].text:")]
    assert any("555" in x for x in cn) and any("31" in x for x in cn)


def test_sourced_guidance_and_call_note_figures_pass(fixture_research, md, tmp_path):
    """The same fields pass when the figure is printed: 'now' and the note on the call's own line; 'before' on the
    line its before_anchor cites (any file under the research root, quote checked), or in the previous Call Notes
    columns when there is no before_anchor."""
    import shutil
    root = str(tmp_path / "TEST")
    shutil.copytree(fixture_research, root)
    open(os.path.join(root, "Earnings Calls", "_md", "2026 Q3 TEST call.md"), "w").write(
        "# Q3 call\n\nJane Doe, CEO: We now see 2026 revenue of $540 million to $550 million.\n")
    p = copy.deepcopy(EX)
    p["guidance"][0].update(before="$540-550 million", now="$640-650 million",
                            before_anchor="Earnings Calls/_md/2026 Q3 TEST call.md:3",
                            before_quote="We now see 2026 revenue of $540 million")
    p["call_notes"]["Capital allocation"][0]["text"] = "Bought back $50 million of stock."
    assert _check(p, root, md) == []
    bad = copy.deepcopy(p)
    bad["guidance"][0]["before_quote"] = "We now see 2026 revenue of $999 million"
    assert any(x.startswith("guidance[0].before:") for x in _check(bad, root, md))
    p["guidance"][0].pop("before_anchor")
    p["guidance"][0].pop("before_quote")
    assert any(x.startswith("guidance[0].before:") and "540" in x for x in _check(p, root, md))
    hist = {"history": [{"quarter": "Q3 26", "cells": {"Guidance (near-term)": "2026 revenue $540-550 million"}}]}
    assert anchors.check(p, None, root, hist, md) == []


def test_failing_names_keep_a_topic_with_a_colon(fixture_research, md):
    """unverified.json holds names the build matches to cells; 'Driver: units' holds a colon, so the name is the
    longest one check() can print that the problem starts with, not the text before the first colon."""
    p = copy.deepcopy(EX)
    p["call_notes"]["Driver: units"] = [{"text": "Units up 99%.", "anchor": f"{CALL}:9",
                                        "quote": "Units should grow faster than revenue"}]
    probs = _check(p, fixture_research, md)
    assert anchors.failing(p, probs) == ["call_notes.Driver: units[0].text"]


def test_cli_writes_and_clears_unverified(work, tmp_path):
    """SKILL.md passes --unverified on every anchors.py run: failing names land in the file the build reads, and
    a plan that now holds leaves no stale file behind to mark cells red."""
    pp, up = str(tmp_path / "p.json"), str(tmp_path / "unverified.json")
    s = os.path.join(HERE, "..", "scripts", "anchors.py")
    cmd = [sys.executable, "-I", s, "--plan", pp, "--context", os.path.join(work, "context.json"), "--unverified", up]
    bad = copy.deepcopy(EX)
    bad["react"]["watch"] = "the drift to the seventh day and 42 other things"
    json.dump(bad, open(pp, "w"))
    assert subprocess.run(cmd, capture_output=True).returncode == 1
    assert json.load(open(up)) == ["react.watch"]
    json.dump(EX, open(pp, "w"))
    assert subprocess.run(cmd, capture_output=True).returncode == 0 and not os.path.exists(up)
