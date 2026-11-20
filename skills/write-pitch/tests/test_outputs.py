# skills/write-pitch/tests/test_outputs.py
import copy
import json
import os
import re
import shutil

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
    """Every sheet field at its budget: 420-char pitch, 12 x 420 script, 5 x 170 napkin, 5 Q&As, 10 know-cold keys,
    a long action in the heading."""
    p = copy.deepcopy(PLAN)
    p["action"] = "Buy aggressively on weakness"
    p["pitch_20s"] = ("pitch " * 100)[:420]
    sh = p["pitch_sheet"]
    sh["script_3min"] = [("Step %d: " % i + "word " * 100)[:420] for i in range(1, 13)]
    sh["napkin"] = [("napkin " * 40)[:170] for _ in range(5)]
    sh["hard_questions"] = [{"q": ("Q%d " % i + "why " * 60)[:170], "a": ("a " * 300)[:420]} for i in range(5)]
    for k in ("k1", "k2", "k3"):
        p["numbers"][k] = {"value": 1, "shown": "$1,204m", "anchor": "SUM!A1"}
    sh["know_cold"] = sh["know_cold"] + ["k1", "k2", "k3"]
    assert len(sh["know_cold"]) == 10
    return p


def test_fill_uses_shown_and_fails_loud():
    assert fill("at {price}", PLAN["numbers"]) == "at " + PLAN["numbers"]["price"]["shown"]
    with pytest.raises(KeyError, match="no number named nope in plan numbers"):   # no raw placeholder reaches the user
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


def test_md_override_object_and_dropped_fields(tmp_path):
    p = copy.deepcopy(PLAN)
    p["override"] = {"reason": "Catalyst beats the Hold.", "evidence": "Valuation!C5"}
    p["slides"][5]["bucket"] = "Estimate momentum"            # why_now
    p["slides"][2]["events"] = [{"date": "2026-02-03", "label": "Q4 print"}]   # setup
    p["slides"].append({"type": "image", "section": "support", "supports": "thesis.1", "title": "Pic",
                        "takeaway": "t", "image": {"pdf": "Decks/a.pdf", "page": 4, "crop": [0.1, 0.2, 0.9, 0.8]},
                        "caption": "The caption", "notes": "n", "source": "s"})
    text = open(build_md.build(p, "", str(tmp_path / "p.md"))).read()
    assert "Override: Catalyst beats the Hold. Evidence: Valuation!C5" in text
    assert "Estimate momentum" in text and "Q4 print" in text
    assert "Decks/a.pdf page 4" in text and "The caption" in text
    assert "Supports: thesis point 1" in text
    assert "R/R ladder: read from the Valuation tab" in text and "3-year IRR" in text   # not hidden behind cases
    for s in p["slides"]:                                      # every slide is listed in the contents
        assert fill(s["title"], p["numbers"]) in text.split("## 20-second pitch")[0]


# why: a waived hurdle is a judgment call; the Markdown copy must show it at the top like an override, or the reader
# sees a Long that cleared nothing with no reason given
def test_md_shows_hurdle_override(tmp_path):
    p = copy.deepcopy(PLAN)
    p["hurdle_override"] = {"reason": "Print in two weeks at {price}.", "evidence": "Valuation!C5"}
    text = open(build_md.build(p, "", str(tmp_path / "p.md"))).read()
    assert "Hurdle override: Print in two weeks at $72.40. Evidence: Valuation!C5" in text.split("# XYZ pitch")[0]


def test_md_two_column_and_text_chart_render(tmp_path):
    text = open(build_md.build(PLAN, "", str(tmp_path / "p.md"))).read()
    assert "**Bull view**" in text and "Growth holds on new products." in text
    assert "Mix adds most of the gain." in text


def test_verdict_line_forms(tmp_path):
    f = tmp_path / "pm.md"
    f.write_text("intro\n### verdict: Reject\n")
    assert build_md._verdict(str(f)) == "verdict: Reject"
    f.write_bytes(b"\xff\xfe\x00bad")
    assert build_md._verdict(str(f)) is None


def test_export_failure_messages(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="does not exist"):
        export_pdf.to_pdf(str(tmp_path / "nope.docx"), str(tmp_path))
    src = tmp_path / "a.docx"
    src.write_text("not a docx")
    monkeypatch.setattr(export_pdf.lo, "SOFFICE", None)
    with pytest.raises(SystemExit, match="LibreOffice not found"):
        export_pdf.to_pdf(str(src), str(tmp_path))
    monkeypatch.setattr(export_pdf.lo, "SOFFICE", shutil.which("false"))
    with pytest.raises(SystemExit, match="could not convert"):
        export_pdf.to_pdf(str(src), str(tmp_path))
    monkeypatch.setattr(export_pdf.lo, "SOFFICE", str(tmp_path / "missing_soffice"))
    with pytest.raises(SystemExit, match="could not be started"):
        export_pdf.to_pdf(str(src), str(tmp_path))


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


@pytest.mark.slow
def test_two_conversions_at_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    srcs = []
    for i in range(2):
        srcs.append(build_sheet.build(PLAN, str(tmp_path / f"s{i}.docx")))
    with ThreadPoolExecutor(2) as ex:
        pdfs = list(ex.map(lambda p: export_pdf.to_pdf(p, str(tmp_path / "out")), srcs))
    assert all(os.path.exists(p) for p in pdfs)


def test_know_cold_capped_at_ten():
    import plan as planmod   # why: more than 10 keys cannot fit the two-page sheet
    p = _full_budget_plan()
    assert not any("at most 10" in x for x in planmod.check(p, "Buy"))
    p["numbers"]["k4"] = p["numbers"]["k1"]
    p["pitch_sheet"]["know_cold"].append("k4")
    assert any("know_cold: at most 10" in x for x in planmod.check(p, "Buy"))


# why: plan.py allows "Wait for {buy_price}" in action and says the builder fills it; a raw {key} on the sheet's
# title line or the Markdown's first line is the first thing the reader sees
def test_action_placeholder_filled_on_sheet_and_md(tmp_path):
    p = copy.deepcopy(PLAN)
    p["action"] = "Wait for {price}"
    want = "Wait for " + p["numbers"]["price"]["shown"]
    sheet = Document(build_sheet.build(p, str(tmp_path / "s.docx")))
    assert want in sheet.paragraphs[0].text
    pm = tmp_path / "pm.md"
    pm.write_text("# PM review\n")
    text = open(build_md.build(p, str(pm), str(tmp_path / "p.md"))).read()
    assert text.startswith(f"**Call: {p['call']}. Action: {want}.**")
