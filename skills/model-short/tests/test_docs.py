# skills/model-short/tests/test_docs.py
"""What Claude follows must name every step's script, and the agent's brief must carry every row, type and bucket
the code checks for, or the agent can't pass plan.py."""
import os

import shortmath as sm

SK = os.path.join(os.path.dirname(__file__), "..")
ROOT = os.path.join(SK, "..", "..")


def _read(*p):
    return open(os.path.join(*p)).read()


def test_skill_names_every_script_and_the_safety_steps():
    s = _read(SK, "SKILL.md")
    for x in ("fetch_short.mjs", "context.py", "plan.py", "anchors.py", "build.py", "verify.py", "note.py",
              "shasum", "~$", "short-analyst", "check with PB", "inputs_written.next.json"):
        assert x in s, x


def test_brief_and_assignment_carry_every_row_type_and_bucket():
    b = _read(SK, "references", "short_brief.md") + _read(SK, "references", "assignment.md")
    for rid, *_ in sm.ROWS:
        assert rid in b, rid
    for t in (*sm.TYPES, *sm.BUCKETS, *sm.VERDICTS):
        assert t in b, t


def test_agent_has_no_shell_or_web():
    a = _read(ROOT, "agents", "short-analyst.md")
    tools = [x for x in a.splitlines() if x.startswith("tools:")][0]
    assert "Bash" not in tools and "Web" not in tools


def test_skill_stops_without_a_model_and_every_stop_deletes_the_copies():
    """Keep no copies of the user's model: every way the run can stop after context.py (plan fails, verify fails, the
    model changed) and the normal end delete the recalculated copies and the built copy."""
    s = _read(SK, "SKILL.md")
    assert '"status": "build"' in s and "/model-historicals" in s
    rm = 'rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"'
    step3, step6, step7, step8 = (s.split(f"## Step {n}:")[1].split("## Step")[0] for n in (3, 6, 7, 8))
    assert rm in step3 and rm in step6 and rm in step7
    assert step8.count(rm) >= 2                                   # the shasum stop and the normal end
