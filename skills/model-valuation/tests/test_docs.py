import os
import re

from conftest import HERE

ROOT = os.path.join(HERE, "..", "..", "..")


def test_agent_has_no_shell_or_web():
    t = open(os.path.join(ROOT, "agents", "valuation-analyst.md")).read()
    tools = re.search(r"^tools: (.+)$", t, re.M).group(1)
    assert tools == "Read, Write, Edit, Grep, Glob"


def test_assignment_carries_the_schema_and_loop():
    a = open(os.path.join(HERE, "..", "references", "assignment.md")).read()
    for s in ("scenarios_try_", "TRY 1 WRITTEN", "PLAN WRITTEN", '"anchor_value"', "25%", "judgment"):
        assert s in a


def test_skill_md_names_every_script_and_the_loop():
    s = open(os.path.join(HERE, "..", "SKILL.md")).read()
    for x in ("context.py", "scenario_eval.py", "plan.py", "anchors.py", "build.py", "verify.py", "note.py",
              "TRY <n> WRITTEN", "inputs_written.next.json", "shasum"):
        assert x in s


def test_tables_list_the_skill():
    for f in ("README.md", "CLAUDE.md"):
        assert "model-valuation" in open(os.path.join(ROOT, f)).read(), f
