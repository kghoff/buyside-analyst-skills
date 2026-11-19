# skills/write-pitch/tests/test_docs.py
import re, pathlib
import common
R = pathlib.Path(__file__).resolve().parents[1] / "references"
KNOWN = {"TICKER","COMPANY","AS_OF","MODE","WORK","RESEARCH","USER_NOTES_OR_NONE","DIGEST","TAB_INDEX",
         "READING_LIST","OPTIONAL_MISSING","OLD_PLATE_OR_NONE","SKILL"}


def test_assignment_fills_known():
    for f in ("assignment.md", "pm_assignment.md"):
        assert set(re.findall(r"\{([A-Z_]+)\}", (R / f).read_text())) <= KNOWN


# why: the agents run from the user's model folder, so a bare "references/x.md" points nowhere
def test_assignments_name_briefs_by_skill_path():
    for f, briefs in (("assignment.md", ("pitch_brief", "plan_schema")), ("pm_assignment.md", ("pm_brief",))):
        text = (R / f).read_text()
        for b in briefs:
            assert f"{{SKILL}}/references/{b}.md" in text, (f, b)
        assert "references/" not in text.replace("{SKILL}/references/", ""), f


def test_briefs_exist_and_sized():
    assert 2500 < len((R / "pitch_brief.md").read_text().split()) < 6000
    assert 1200 < len((R / "pm_brief.md").read_text().split()) < 3500


def test_docs_agree_with_common():
    """The agent follows the briefs and code checks against common.py: if the two drift apart, the agent writes
    plans the checks reject (or the checks wave through plans the brief forbids). Every rule value is derived from
    common.py here, so changing a hurdle, a budget or a slide type there fails this test until the docs follow."""
    brief, schema = (R / "pitch_brief.md").read_text(), (R / "plan_schema.md").read_text()
    for t in common.CORE_TYPES:
        assert f"`{t}`" in brief and f"`{t}`" in schema, t
    # the schema states the core slide order exactly as common.CORE_TYPES has it
    assert ", ".join(f"`{t}`" for t in common.CORE_TYPES) in re.sub(r"\s+", " ", schema)
    for t in common.SUPPORT_LAYOUTS + common.CALLS:
        assert f"`{t}`" in schema, t
    for box in common.SUM_BOXES:
        assert f"`{box}`" in schema, box
    for name, limit in common.BUDGET.items():
        assert re.search(rf"\| {name} \| {limit:,}".replace(",", ",?"), schema), (name, limit)
    h = common.HURDLES
    for text in (brief, schema):
        assert f"{h['buy_rr']:g}:1" in text and f"{h['pound_rr']:g}:1" in text and f"{h['irr']:.0%}" in text
    # the buy price is the 3-year target discounted at the IRR hurdle, the no-brainer at the no-brainer IRR
    pm = (R / "pm_brief.md").read_text()
    for text in (brief, pm):
        assert f"{1 + h['irr']:g}^3" in text and f"{1 + h['nobrainer_irr']:g}^3" in text
        assert f"{h['nobrainer_irr']:.0%}" in text
    assert f"{h['buy_rr']:g}:1" in pm and f"{h['pound_rr']:g}:1" in pm and f"{h['irr']:.0%}" in pm
    # the budgets the brief restates are common.BUDGET's (the schema's table is checked above)
    for name, limit in common.BUDGET.items():
        assert re.search(rf"\b{name} {limit:,}\b".replace(",", ",?"), brief), (name, limit)
    # the brief's slide-order table runs in common.CORE_TYPES order
    rows = [brief.index(f"| {n} | `{t}` |") for n, t in enumerate(common.CORE_TYPES, 1)]
    assert rows == sorted(rows)


# why: the agent reads the verdicts and hurdles by their row labels in the digest; a label that drifts from the
# Valuation / Short Check tabs leaves the agent looking for a row that isn't there
def test_tab_labels_named():
    labels = ["Overall verdict (the agent's call: Buy / Hold / Sell)", "Verdict (agent's call)", "Verdict (the rule)",
              "IRR hurdle", "Buy at R/R", "Table-pound at R/R"]
    for f in ("pitch_brief.md", "plan_schema.md", "assignment.md"):
        text = re.sub(r"\s+", " ", (R / f).read_text())
        for lab in labels:
            assert f'"{lab}"' in text, (f, lab)


# why: every problem line plan.py prints carries a rule id, and the agent fixes it by reading that rule in section 12;
# a rule the schema doesn't list (or lists but the code never checks) misleads the agent
def test_schema_rule_ids_match_plan_py():
    src = (pathlib.Path(common.__file__).parent / "plan.py").read_text()
    code = {m for pair in re.findall(r'\[R(\d+)\]|"R(\d+)"', src) for m in pair if m}
    schema = (R / "plan_schema.md").read_text()
    s12 = schema[schema.index("## 12. Every rule the code enforces"):]
    listed = re.findall(r"\*\*\[R(\d+)\]\*\*", s12)
    assert len(listed) == len(set(listed)), "an id is listed twice"
    assert set(listed) == code


# why: SKILL.md is what Claude follows; a script it never names is a step the run silently skips (and a house rule it
# never states, such as the checksum before the copy-over, is one Claude never follows)
def test_skill_md_runs_every_script_and_house_rules():
    skill = R.parent / "SKILL.md"
    text = skill.read_text()
    flat = re.sub(r"\s+", " ", text)
    library = {"__init__", "common", "fill", "xlsx", "model_reads", "make_template", "lo"}   # imported by others, or a one-off tool
    for p in sorted((R.parent / "scripts").glob("*.py")):
        if p.stem not in library:
            assert f'"$SK/{p.stem}.py"' in text, p.name
    assert "build_deck.py" in text and "import lo" in text and "lo.recalc" in text
    assert text.startswith("---\nname: write-pitch\n")
    for must in ("shasum -a 256", "~$", "model opus", "never overwrite", "`{SKILL}`", "AskUserQuestion",
                 "UNVERIFIED", "sum_written.next.json", "verify OK", "plain English", "judgment call",
                 "speaker notes", "mv -n", "--research <dir>", "python3 -m pip install"):
        assert must in text, must
    # the model copies are deleted on every stop after Step 4 (house rule: keep no copies), not just on success
    assert text.count('rm -rf "$W/values" "$W/out.xlsx" "$W/build"') >= 5
    # UNVERIFIED items go in the speaker notes and the report, never in red on the slide face
    assert "in red" not in text
    # every assignment fill is named, so none reaches the agent as a raw {KEY}
    for key in KNOWN:
        assert f"`{{{key}}}`" in text, key
    for lab in ("Overall verdict (the agent's call: Buy / Hold / Sell)", "Verdict (agent's call)",
                "Verdict (the rule)", "IRR hurdle", "Buy at R/R", "Table-pound at R/R"):
        assert f'"{lab}"' in flat, lab


# why: labels.py reads the verdicts and hurdles by these exact labels; if it drifts from the brief's wording, the call
# the analyst makes and the call plan.py checks come from different rows
def test_labels_py_matches_brief():
    import labels
    brief = re.sub(r"\s+", " ", (R / "pitch_brief.md").read_text())
    for lab in (labels.VAL_VERDICT, labels.SHORT_AGENT, labels.SHORT_RULE, *labels.HURDLE_LABELS.values()):
        assert f'"{lab}"' in brief, lab


# why: each line below is a rule a run gets wrong without it: the deck shows last run's SUM prices (--sum-record), a
# build lands in Pitch/ before the look step (bare names), a box in the user's model holds an unchecked number nobody
# named, the look step loops with the analyst forever, or the PM's rerun Write is refused (unread file)
def test_rerun_and_report_rules_are_written_down():
    skill = re.sub(r"\s+", " ", (R.parent / "SKILL.md").read_text())
    assert '--sum-record "$MD/_model_work/write-pitch/sum_written.json"' in skill
    assert "as bare file names (no folder)" in skill
    assert "Every SUM box that now holds an UNVERIFIED number" in skill and "`unverified.json`" in skill
    assert "at most one more check round: Step 7's two-round limit does not restart" in skill
    pm = re.sub(r"\s+", " ", (R / "pm_assignment.md").read_text())
    assert "already exists (a rerun), Read it first" in pm
    notes = re.sub(r"\s+", " ", (R.parent / "NOTES.md").read_text())
    assert "Table of contents: an exception to the house rule" in notes and "slide 2's summary" in notes


# why: model-update's forecast roll reads the newest Pitch/*.md, and CLAUDE.md names the prefixes; neither may call
# write-pitch a future skill now that it writes that file
def test_other_docs_know_write_pitch_exists():
    root = R.parents[2]
    claude = re.sub(r"\s+", " ", (root / "CLAUDE.md").read_text())
    assert "`write-` (future)" not in claude and "`write-` produces a deliverable" in claude
    upd = (root / "skills" / "model-update" / "SKILL.md").read_text()
    assert "newest `$SRC/Pitch/*.md`" in upd and "future /write-pitch" not in upd
