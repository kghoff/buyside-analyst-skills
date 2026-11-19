"""SKILL.md is what Claude follows: it must keep the house rules (shasum twice, the lock file, no backups, every
judgment call told), ask before stopping for a transcript, and name every script it runs that exists. NOTES.md says
why the scripts are the way they are, so a later change does not undo a choice by accident."""
import os
import re

D = os.path.join(os.path.dirname(__file__), "..")
S = open(os.path.join(D, "SKILL.md")).read()
N = open(os.path.join(D, "NOTES.md")).read()


def test_frontmatter():
    assert S.startswith("---\nname: model-earnings-after\n")


def test_house_rules():
    for s in ("shasum", "~$", "judgment call", "FactSet", "AskUserQuestion", "--rebuild", "T+7", "Earnings Reviews"):
        assert s in S, s


def test_shasum_before_and_before_copying():
    """The model is checksummed before the build and again before it is copied over (changed = stop)."""
    assert S.count("shasum") >= 2


def test_scripts_exist():
    names = set(re.findall(r'\$SK/([\w.]+\.(?:py|mjs))', S))
    assert names, "SKILL.md names no scripts"
    for f in names:
        assert os.path.isfile(os.path.join(D, "scripts", f)), f


def test_sibling_scripts_exist():
    """Scripts borrowed from sibling skills ($SKILLS/<skill>/scripts/...) must exist too."""
    for f in set(re.findall(r'\$SKILLS/([\w-]+/scripts/[\w.]+\.(?:py|mjs))', S)):
        assert os.path.isfile(os.path.join(D, "..", f)), f


def test_note_after_the_recalculated_copy_is_deleted_last():
    """note.py reads verify's recalculated copy: the step that deletes values_out must come after note.py runs."""
    assert S.index("note.py") < S.rindex("values_out")


def test_notes_sections():
    assert re.search(r"^## Origin", N, re.M) and re.search(r"^## Choices", N, re.M)
