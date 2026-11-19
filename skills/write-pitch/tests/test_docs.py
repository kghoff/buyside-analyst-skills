# skills/write-pitch/tests/test_docs.py
import re, pathlib
import common
R = pathlib.Path(__file__).resolve().parents[1] / "references"
KNOWN = {"TICKER","COMPANY","AS_OF","MODE","WORK","RESEARCH","USER_NOTES_OR_NONE","DIGEST","TAB_INDEX",
         "READING_LIST","OPTIONAL_MISSING","OLD_PLATE_OR_NONE"}


def test_assignment_fills_known():
    for f in ("assignment.md", "pm_assignment.md"):
        assert set(re.findall(r"\{([A-Z_]+)\}", (R / f).read_text())) <= KNOWN


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
    # the buy price is the 3-year target discounted at the IRR hurdle
    assert f"{1 + h['irr']:g}^3" in brief
