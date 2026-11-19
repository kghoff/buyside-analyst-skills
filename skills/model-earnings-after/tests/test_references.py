"""The agent works only from these files, so they must carry the chapter's after-print rules and a plan example
that passes plan.py (an example that fails teaches the agent the wrong shape)."""
import json
import os

R = os.path.join(os.path.dirname(__file__), "..", "references")
AG = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents", "earnings-analyst.md")
EX = os.path.join(os.path.dirname(__file__), "fixtures", "plan_example.json")


def test_brief_carries_the_chapter():
    b = open(os.path.join(R, "after_brief.md")).read()
    for s in ("SFOT", "Surprise", "Fundamentals", "Outlook", "Tone", "checkpoint", "under-reaction",
              "conservative-guide", "weird reaction", "exit liquidity", "long-term value trajectory",
              "too cute", "Predict, then react"):
        assert s.lower() in b.lower(), s


def test_brief_cites_the_chapter_sections():
    """Every rule the agent follows must be traceable to the chapter, so the user can check the advice."""
    b = open(os.path.join(R, "after_brief.md")).read()
    assert "13.6" in b and "13.7" in b
    assert 600 <= len(b.split()) <= 1100


def test_agent_is_allowed_here():
    a = open(AG).read()
    assert "model-earnings-after" in a and "Use only from the model-earnings-before and model-earnings-after" in a
    assert "tools: Read, Write, Edit, Grep, Glob\n" in a         # no shell, no web: unchanged


def test_assignment_names_the_example_and_the_output():
    """The agent writes the file the skill reads, in the shape the example shows."""
    a = open(os.path.join(R, "after_assignment.md")).read()
    assert "after_plan.json" in a and "plan_example.json" in a and "PLAN WRITTEN" in a
    assert "played_out" in a and "drift_ready" in a


def test_example_is_valid_json_with_every_section():
    p = json.load(open(EX))
    for k in ("quarter", "sfot", "call_notes", "guidance", "lt_target", "checkpoint", "react", "catalysts",
              "controversies", "headline", "quarter_thoughts", "played_out", "judgment_calls"):
        assert k in p, k
