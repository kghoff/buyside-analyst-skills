"""SKILL.md is what Claude runs on print night; a stale name or flag in it breaks the run at the worst time."""
import os
import re

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
SKILL = open(os.path.join(ROOT, "SKILL.md")).read()
SKILLS = os.path.join(ROOT, "..")


def test_every_script_skill_md_calls_exists():
    """A renamed script breaks the run at print time, the worst time."""
    for var, d in (("SK", os.path.join(ROOT, "scripts")), ("FC", os.path.join(SKILLS, "model-forecast", "scripts")),
                   ("RF", os.path.join(SKILLS, "research-filings", "scripts"))):
        for s in set(re.findall(r'\$' + var + r'/([a-z_]+\.py)', SKILL)):
            assert os.path.exists(os.path.join(d, s)), f"${var}/{s}"


def test_every_flag_skill_md_passes_to_our_scripts_exists():
    """The scripts' flags changed after the real-model reviews (e.g. verify lost --q4 and --rows-moved); an old flag
    is an argparse error mid-run."""
    for line in SKILL.splitlines():
        for s in set(re.findall(r'\$SK/([a-z_]+\.py)', line)):
            src = open(os.path.join(ROOT, "scripts", s)).read()
            for flag in re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", line.split(f"$SK/{s}", 1)[1]):
                assert f'"{flag}"' in src or f"'{flag}'" in src or f'"{flag[2:]}"' in src, f"{s} {flag}"


def test_the_user_file_is_written_once_after_verify_and_a_checksum():
    """One write, after every check: a stopped run must leave the user's model exactly as it was."""
    writes = re.findall(r'cp [^\n]*"\$MODEL"', SKILL)
    assert writes == ['cp "$TMP/f.xlsx" "$MODEL"']
    i = SKILL.index('python3 "$SK/verify.py"')
    w = SKILL.index('cp "$TMP/f.xlsx" "$MODEL"')
    assert w > i and "SHA0" in SKILL[i:w]


def test_state_json_is_saved_only_with_the_model():
    """state.json tells the 10-Q rerun which cells wait; saved without the model it would describe cells that were
    never written."""
    assert '--state "$QW/state.json"' not in SKILL
    assert SKILL.index('cp "$TMP/state.json" "$QW/state.json"') > SKILL.index('cp "$TMP/f.xlsx" "$MODEL"')


def test_every_prompt_field_is_filled_in_skill_md():
    """An unfilled {FIELD} reaches the agent as literal text and it guesses."""
    for name in ("reader_prompt.md", "roll_prompt.md"):
        for f in set(re.findall(r"\{([A-Z_]+)\}", open(os.path.join(ROOT, "references", name)).read())):
            assert "{" + f + "}" in SKILL, f"{name}: {{{f}}}"


def test_the_placeholders_are_explained_to_the_user():
    """Orange cells hold the old forecast, not reported numbers; a user who isn't told reads them as actuals."""
    rep = SKILL[SKILL.index("## 8. Report"):]
    assert "placeholder" in rep and "orange" in rep.lower() and "not reported numbers" in rep
