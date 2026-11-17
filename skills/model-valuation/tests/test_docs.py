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
