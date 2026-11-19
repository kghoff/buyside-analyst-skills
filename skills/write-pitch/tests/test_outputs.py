# skills/write-pitch/tests/test_outputs.py
import copy
import json
import re

import pytest
from docx import Document
from pptx import Presentation

import build_md
import build_sheet
import export_pdf
from fill import fill

from conftest import FIX

ROOT = FIX.parent.parent
PLAN = json.loads((FIX / "plan_example.json").read_text())


def _full_budget_plan():
    """Script of 12 steps x 420 chars, five hard questions at budget, a long know-cold list."""
    p = copy.deepcopy(PLAN)
    p["pitch_sheet"]["script_3min"] = [("Step %d: " % i + "word " * 100)[:420] for i in range(1, 13)]
    p["pitch_sheet"]["hard_questions"] = [{"q": "Q%d " % i + "x" * 160, "a": "a " * 200} for i in range(5)]
    return p


def test_fill_uses_shown_and_fails_loud():
    assert fill("at {price}", PLAN["numbers"]) == "at " + PLAN["numbers"]["price"]["shown"]
    with pytest.raises(KeyError):   # a raw placeholder must never reach the user
        fill("{nope}", PLAN["numbers"])


def test_sheet_headings_page_break_no_placeholders(tmp_path):
    out = build_sheet.build(PLAN, str(tmp_path / "s.docx"))
    doc = Document(out)
    text = "\n".join(p.text for p in doc.paragraphs)
    for h in ("20-second pitch", "3-minute script", "On a napkin", "The hardest questions", "Know cold"):
        assert h in text
    assert 'w:br w:type="page"' in doc.element.xml
    assert "{" not in text and "}" not in text
    assert PLAN["numbers"]["price"]["shown"] in text.splitlines()[0]   # the heading line carries the price


def test_md_leads_with_call_and_has_everything(tmp_path):
    pm = tmp_path / "pm.md"
    pm.write_text("# PM review\n\n## Verdict: Approve with fixes\n\nbody\n")
    out = build_md.build(PLAN, str(pm), str(tmp_path / "p.md"))
    text = open(out).read()
    assert text.startswith(f"**Call: {PLAN['call']}. Action: {PLAN['action']}.**")
    assert "## Contents" in text and text.index("## Contents") < text.index("## 20-second pitch")
    for s in PLAN["slides"]:
        assert fill(s["title"], PLAN["numbers"]) in text
    assert not re.search(r"\{\w+\}", text)
    assert "Speaker notes" in text
    assert "Verdict: Approve with fixes" in text
    assert "our estimate" in text                       # risk probabilities are labelled as judgment
    q = PLAN["quotes"][0]
    assert f"{q['file']}:{q['line']}" in text           # a quote always carries its citation
    assert "Judgment calls" in text


def test_md_override_and_missing_review(tmp_path):
    p = copy.deepcopy(PLAN)
    p["override"] = "Overrode the Hold because of the catalyst."
    text = open(build_md.build(p, str(tmp_path / "none.md"), str(tmp_path / "p.md"))).read()
    assert "PM review: none" in text
    assert text.index("Overrode the Hold") < text.index(f"# {PLAN['ticker']} pitch")


@pytest.fixture(scope="session")
def exports(tmp_path_factory):
    """One LibreOffice run per file: a two-slide deck and the full-budget sheet."""
    import fitz
    d = tmp_path_factory.mktemp("pdf_fx")
    prs = Presentation(str(ROOT / "assets" / "pitch_template.pptx"))
    for name in ("title", "summary"):
        prs.slides.add_slide(next(l for l in prs.slide_layouts if l.name == name))
    deck = str(d / "deck.pptx")
    prs.save(deck)
    sheet = build_sheet.build(_full_budget_plan(), str(d / "sheet.docx"))
    out = {}
    for k, src in (("deck", deck), ("sheet", sheet)):
        pdf = export_pdf.to_pdf(src, str(d / "pdf"))
        out[k] = (pdf, len(fitz.open(pdf)))
    out["pngs"] = export_pdf.pngs(out["sheet"][0], str(d / "png"))
    return out


@pytest.mark.slow
def test_deck_exports_two_pages(exports):
    assert exports["deck"][1] == 2


@pytest.mark.slow
def test_full_budget_sheet_is_two_pages(exports):
    assert exports["sheet"][1] == 2      # the whole point of a rehearsal sheet: it fits two pages
    assert len(exports["pngs"]) == 2
