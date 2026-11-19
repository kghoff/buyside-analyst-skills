# skills/write-pitch/scripts/build_sheet.py
"""The two-page pitch sheet (.docx) the user rehearses with. Page 1: ticker / call / action / price, the 20-second
pitch, the 3-minute script, the napkin. Page 2: the hardest questions and what to know cold.
usage: python3 build_sheet.py --plan pitch_plan.json --out XYZ_pitch_sheet.docx"""
import argparse
import os
import sys

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.shared import Pt

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
from common import load  # noqa: E402
from fill import fill  # noqa: E402
from fill import label  # noqa: E402

FONT = "Arial"


def _style(doc):
    for name in ("Normal", "List Number", "List Bullet"):
        st = doc.styles[name]
        st.font.name = FONT
        st.font.size = Pt(9)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        st.paragraph_format.space_after = Pt(2)
        st.paragraph_format.space_before = Pt(0)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Inches(0.5)
    sec.top_margin = sec.bottom_margin = Inches(0.5)


def _head(doc, text, size=12):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(size)
    r.font.name = FONT
    return p


def build(plan, out):
    n = plan["numbers"]
    f = lambda t: fill(t, n)  # noqa: E731
    sheet = plan["pitch_sheet"]
    doc = Document()
    _style(doc)
    _head(doc, f"{plan['ticker']}  |  {plan['call']}  |  {plan['action']}  |  {n['price']['shown']}", 16)
    _head(doc, "20-second pitch")
    doc.add_paragraph(f(plan["pitch_20s"]))
    _head(doc, "3-minute script")
    for step in sheet["script_3min"]:
        doc.add_paragraph(f(step), style="List Number")
    _head(doc, "On a napkin")
    for item in sheet["napkin"]:
        doc.add_paragraph(f(item), style="List Bullet")
    doc.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)   # break inside the last napkin line: no empty paragraph
    _head(doc, "The hardest questions")
    for qa in sheet["hard_questions"]:
        doc.add_paragraph().add_run(f(qa["q"])).bold = True
        doc.add_paragraph(f(qa["a"]))
    _head(doc, "Know cold")
    for key in sheet["know_cold"]:
        p = doc.add_paragraph()
        p.add_run(f"{label(key)}: ").bold = True
        p.add_run(str(n[key]["shown"]))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    doc.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(build(load(a.plan), a.out))


if __name__ == "__main__":
    main()
