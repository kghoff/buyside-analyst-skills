"""SKILL.md must match the scripts: every command uses flags its script really takes (a wrong flag would stop
the user's run halfway), and the removed v1 pieces (agent, plan, approval page) are gone."""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
SKILL = open(os.path.join(ROOT, "SKILL.md")).read()


def _flags(script):
    src = open(os.path.join(ROOT, "scripts", script)).read()
    flags = set(re.findall(r'add_argument\(\s*["\']--([\w-]+)', src))
    for tup in re.findall(r"for \w+ in \(([^)]*)\):\s*\n\s*ap\.add_argument", src):
        flags |= set(re.findall(r'"([\w-]+)"', tup))
    return flags


def test_every_skill_command_uses_flags_its_script_takes():
    cmds = re.findall(r"python3 \$R/scripts/(\w+\.py)([^\n]*(?:\\\n[^\n]*)*)", SKILL)
    assert {c for c, _ in cmds} == {"context.py", "solve.py", "build.py", "check.py"}
    for script, args in cmds:
        used = set(re.findall(r"--([\w-]+)", args))
        if script == "context.py":
            assert not used, "context.py takes positional arguments: <model> <out context.json>"
            continue
        assert used <= _flags(script), f"{script}: unknown flags {used - _flags(script)}"
        assert _flags(script) <= used, f"{script}: missing required flags {_flags(script) - used}"


def test_no_agent_plan_or_approval_left():
    for gone in ("dcf_plan", "plan_prompt", "page.py", "subagent_type", "AskUserQuestion", "Bear", "Bull"):
        assert gone not in SKILL, gone
    assert not os.path.exists(os.path.join(ROOT, "references", "plan_prompt.md"))
    assert not os.path.exists(os.path.join(ROOT, "scripts", "page.py"))
