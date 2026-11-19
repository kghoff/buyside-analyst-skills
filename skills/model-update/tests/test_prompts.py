"""The agent prompts: an unfilled or misnamed {FIELD} reaches the agent as literal text and it guesses."""
import os
import re

REF = os.path.join(os.path.dirname(__file__), "..", "references")


def _text(name):
    return open(os.path.join(REF, name)).read()


def _fields(name):
    return set(re.findall(r"\{([A-Z_]+)\}", _text(name)))


def test_reader_prompt_fields_are_the_ones_skill_md_fills():
    assert _fields("reader_prompt.md") == {"OPEN_LINES", "ROWMAP", "DOCS", "ROOT", "GUIDED", "ANSWERS", "GUIDANCE"}


def test_reader_prompt_teaches_the_summed_row_answer_match_py_accepts():
    """match.apply_answers refuses a second answer on a row unless every one says "sum": true; an agent that never
    heard of it can only map one of the lines and the row ties out wrong."""
    t = _text("reader_prompt.md")
    assert '"sum": true' in t and "map" in t


def test_roll_prompt_reads_the_thesis_before_the_plan():
    """The roll is thesis-aware: the agent must know what the thesis rests on before it touches an assumption."""
    t = _text("roll_prompt.md")
    assert t.index("{THESIS_READING_LIST}") < t.index("{PLAN}")
    assert _fields("roll_prompt.md") == {"QUARTER", "THESIS_READING_LIST", "PLAN", "WRITEUP", "DOCS", "ACTUAL_VS_FROZEN",
                                         "ROWMAP", "GUIDANCE", "PLAN_BEFORE", "CHANGES"}


def test_roll_prompt_forbids_the_structure_fields_plandiff_refuses():
    """plandiff.STRUCTURE is refused by code; a prompt that does not say so wastes rounds with the agent."""
    import plandiff
    t = _text("roll_prompt.md")
    assert all(f"`{k}`" in t for k in plandiff.STRUCTURE) and "seasonal" in t
