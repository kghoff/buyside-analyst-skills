# skills/model-earnings-before/tests/test_docs.py
"""What Claude follows must name every step's script and the safety steps, ask the user before overwriting their
variance table, and the agent's brief must carry every id plan.py checks, or the agent can't pass it."""
import os

import earnmath as em

SK = os.path.join(os.path.dirname(__file__), "..")
ROOT = os.path.join(SK, "..", "..")


def _read(*p):
    return open(os.path.join(*p)).read()


def test_skill_names_every_script_and_the_safety_steps():
    s = _read(SK, "SKILL.md")
    for x in ("fetch_earnings.mjs", "context.py", "web_assignment.md", "street-researcher", "earnings-analyst",
              "plan.py", "anchors.py", 'variance.py" inspect', "build.py", "verify.py", "note.py", "shasum", "~$",
              "--force-variance", "--variance earnings", "inputs_written.next.json", "variance_written.next.json"):
        assert x in s, x


def test_skill_asks_before_overwriting_the_users_variance_table():
    s = _read(SK, "SKILL.md")
    step = s.split("## Step 7:")[1].split("## Step")[0]
    assert '"data"' in step and "Ask the user" in step and "skeleton" in step and "ours" in step


def test_brief_and_assignment_carry_every_id():
    b = _read(SK, "references", "earnings_brief.md") + _read(SK, "references", "assignment.md")
    ids = [rid for rid, *_ in em.SETUP] + [rid for rid, _ in em.RISKS] + list(em.STANCES) + list(em.CALL_Q) + \
        list(em.CALL_G) + list(em.AGENT_INPUTS)
    for x in ids:
        assert x in b, x


def test_agent_has_no_shell_or_web():
    a = _read(ROOT, "agents", "earnings-analyst.md")
    tools = [x for x in a.splitlines() if x.startswith("tools:")][0]
    assert "Bash" not in tools and "Web" not in tools


def test_every_stop_deletes_the_copies():
    """Keep no copies of the user's model: every way the run can stop after context.py and the normal end delete the
    recalculated copies and the built copy."""
    s = _read(SK, "SKILL.md")
    assert '"status": "build"' in s and "/model-historicals" in s
    rm = 'rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"'
    step3, step6, step8, step9 = (s.split(f"## Step {n}:")[1].split("## Step")[0] for n in (3, 6, 8, 9))
    assert rm in step3 and rm in step6 and rm in step8
    assert step9.count(rm) >= 2
