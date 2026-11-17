"""SKILL.md must match the scripts: every command names a script that exists and passes flags it takes, and the
judgment calls and pauses the user must hear about are written down (a missing one would be a silent decision)."""
import os
import re

SK = os.path.join(os.path.dirname(__file__), "..")
TEXT = open(os.path.join(SK, "SKILL.md")).read()


def _flags(script):
    src = open(os.path.join(SK, "scripts", script)).read()
    return set(re.findall(r'add_argument\(\s*["\']--([\w-]+)', src))


def test_skill_runs_only_scripts_that_exist():
    scripts = set(re.findall(r'\$SK/([\w.]+)', TEXT))
    assert scripts
    for s in scripts:
        assert os.path.exists(os.path.join(SK, "scripts", s)), s


def test_every_command_uses_flags_its_script_takes():
    for script, args in re.findall(r'python3 "\$SK/(\w+\.py)"([^\n`]*)', TEXT):
        used = set(re.findall(r"--([\w-]+)", args))
        assert used <= _flags(script), f"{script}: unknown flags {used - _flags(script)}"


def test_skill_covers_the_pauses_and_the_judgment_calls():
    for must in ("AskUserQuestion", "comps.json", "stooq", "mapping.json", "45 days", "TTM", "shasum", "~$",
                 "_model_work/model-multiples", '"ok": true', "Price Data"):
        assert must in TEXT, must


def test_description_says_when_to_use_it():
    desc = re.search(r"^description: (.*)$", TEXT, re.M).group(1)
    assert "Use when" in desc and "/model-multiples" in desc


def test_no_backup_copies_and_no_live_write_before_the_copy_over():
    assert "no backup" in TEXT.lower()
    assert TEXT.count('cp "$W/out.xlsx" "$M"') == 1


def test_every_path_skill_deletes_is_one_the_scripts_create():
    scripts = "".join(open(os.path.join(SK, "scripts", f)).read() for f in os.listdir(os.path.join(SK, "scripts"))
                      if f.endswith(".py"))
    step7 = TEXT.split("## Step 7")[1].split("## Step 8")[0]
    for name, marker in (("$W/out.xlsx", "out.xlsx"), ("$W/values/", '"values"'), ("$W/verify/", '"verify"')):
        assert name in step7 and marker in (scripts + TEXT), name
    assert "_recalc" not in TEXT
