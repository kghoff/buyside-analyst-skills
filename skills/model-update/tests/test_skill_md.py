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


def _commands(text):
    """Every shell line SKILL.md runs: lines inside code blocks and inline `python3 ...` / `cp ...` commands."""
    out, code = [], False
    for line in text.splitlines():
        if "```" in line:                             # fences, also "2. ```bash" in a numbered step
            code = not code
            continue
        if code:
            out.append(line)
        out += re.findall(r"`((?:python3|cp|mv) [^`]+)`", line)
    return out


def test_nothing_is_written_to_research_filings_data_before_the_model_copy():
    """Guidance is recorded on every print and the closed year rebuilt on a Q4, before verify and the checksum. Written
    straight into research-filings' folder, a run that stops later would leave guides and a bumped last_year for a
    print the model never got; so they go to a staged copy that is copied back only after the model copy."""
    copy = SKILL.index('cp "$TMP/f.xlsx" "$MODEL"')
    pre = _commands(SKILL[:copy])
    real = ('"$FRW', '"$SRC/Filings Research', 'handoff.py" --src "$SRC"')
    for line in pre:
        if not any(r in line for r in real) or line.startswith("FRW="):
            continue
        assert line.startswith("cp ") and line.rstrip().endswith('"$FW/"') or line.startswith('(cd "$FRW" &&'), line
        assert "$FW/" in line, line
    assert any('--work "$FW"' in x and "guidance.py\" record" in x for x in pre)
    assert any('handoff.py" --src "$TMP/fr"' in x for x in pre)
    back = SKILL.index('cp "$f" "$FRW/$f"')
    assert back > copy and SKILL.index('rm -rf "$TMP"', back) > back


def test_every_stop_once_tmp_exists_removes_it():
    """$TMP holds copies of the user's model; the house rule is to keep no backup copies, so no stop may leave it."""
    body = SKILL[SKILL.index("TMP=$(mktemp -d)"):]
    body = body[:body.index("## 8. Report")] + body[body.index("## 10-Q rerun"):]   # the report gives no stops
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"\bstop\b", line) and "Every stop" not in line:
            near = " ".join(lines[max(0, i - 1):i + 3])
            assert 'rm -rf "$TMP"' in near, line


def test_the_10q_rerun_keeps_print_nights_files():
    """The 10-Q pass must not overwrite print night's open lines, answers or match: they are the record of what was
    typed and why."""
    tenq = SKILL[SKILL.index("## 10-Q rerun"):]
    for name in ("open_lines", "reader_answers", "match"):
        assert f"$QW/{name}_10q.json" in tenq and f"$QW/{name}.json" not in tenq, name
    assert "$QW/reader_10q.assignment.md" in tenq and "$QW/reader.assignment.md" not in tenq


def test_kept_json_is_written_before_the_tieout_that_reads_it():
    """tieout reads kept.json; a missing file is a crash, a stale one skips the wrong cells."""
    tenq = SKILL[SKILL.index("## 10-Q rerun"):]
    assert tenq.index("`$QW/kept.json` (`[]`") < tenq.index('--awaiting "$QW/kept.json"')
