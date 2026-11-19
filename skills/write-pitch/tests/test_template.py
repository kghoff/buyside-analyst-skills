"""The navy template: layouts by name, placeholders by idx (the builder relies on both)."""
import hashlib
import os
import sys

from pptx import Presentation
from pptx.util import Inches

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import make_template
from common import CORE_TYPES
from common import SUPPORT_LAYOUTS
from common import THEME

TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "assets", "pitch_template.pptx")
NAMES = CORE_TYPES + SUPPORT_LAYOUTS


def idx_map(prs):
    return {l.name: sorted(p.placeholder_format.idx for p in l.placeholders) for l in prs.slide_layouts}


def test_opens_and_is_16_9():
    # a 4:3 deck would crop the mockup's wide tables
    prs = Presentation(TEMPLATE)
    assert abs(prs.slide_width / prs.slide_height - 16 / 9) < 0.01


def test_every_layout_name_exists_exactly_once():
    # the builder looks layouts up by name; a missing or duplicate name would silently pick the wrong slide design
    names = [l.name for l in Presentation(TEMPLATE).slide_layouts]
    for n in NAMES:
        assert names.count(n) == 1, n
    assert sorted(names) == sorted(NAMES)


def test_title_takeaway_source_idx_on_every_layout():
    # every slide carries a title, a takeaway and a source line (the plan requires them)
    for name, idxs in idx_map(Presentation(TEMPLATE)).items():
        assert {0, 10, 11} <= set(idxs), name
        assert len(idxs) == len(set(idxs)), name


def test_one_slide_per_layout_every_placeholder_fills():
    # catches a placeholder python-pptx cannot instantiate or that has no text frame
    prs = Presentation(TEMPLATE)
    for layout in prs.slide_layouts:
        slide = prs.slides.add_slide(layout)
        assert {p.placeholder_format.idx for p in slide.placeholders} == {p.placeholder_format.idx for p in layout.placeholders}
        for ph in slide.placeholders:
            if ph.placeholder_format.type is not None and "PICTURE" in str(ph.placeholder_format.type):
                continue                      # pictures take an image, not text
            ph.text_frame.text = "Sample"
            assert ph.text_frame.text == "Sample"
    assert len(prs.slides) == len(NAMES)


def test_placeholders_stay_on_the_slide():
    # text off the edge is the first thing a restyled template breaks
    prs = Presentation(TEMPLATE)
    for layout in prs.slide_layouts:
        for ph in layout.placeholders:
            assert ph.left >= 0 and ph.top >= 0, layout.name
            assert ph.left + ph.width <= prs.slide_width and ph.top + ph.height <= prs.slide_height, layout.name


def test_template_has_no_personal_metadata():
    cp = Presentation(TEMPLATE).core_properties
    assert cp.author == "write-pitch" and cp.last_modified_by == "write-pitch"


def test_regenerating_does_not_drift(tmp_path):
    # the committed .pptx must match what the script makes, or the docstring's idx map is a lie
    out = tmp_path / "t.pptx"
    make_template.write(str(out))
    assert idx_map(Presentation(str(out))) == idx_map(Presentation(TEMPLATE))
    out2 = tmp_path / "t2.pptx"
    make_template.write(str(out2))
    assert hashlib.sha1(out.read_bytes()).hexdigest() == hashlib.sha1(out2.read_bytes()).hexdigest()


def _style(ph):
    """(fill hex, font size pt, bold, italic, colour hex) from the layout placeholder's own XML."""
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    el = ph._element
    fill = el.xpath("./p:spPr/a:solidFill/a:srgbClr/@val")
    d = el.xpath(".//a:lvl1pPr/a:defRPr")[0]
    return (fill[0] if fill else None, int(d.get("sz")) / 100, d.get("b") == "1", d.get("i") == "1",
            d.xpath("./a:solidFill/a:srgbClr/@val")[0])


def test_chrome_matches_theme():
    # a look change in THEME (or a hand edit of the template) must fail here so the docs and builder stay in step
    for layout in Presentation(TEMPLATE).slide_layouts:
        ph = {p.placeholder_format.idx: p for p in layout.placeholders}
        assert _style(ph[0]) == (THEME["navy"], 20, True, False, "FFFFFF"), layout.name
        assert _style(ph[10]) == (THEME["band"], 12, False, True, THEME["text"]), layout.name
        assert _style(ph[11]) == (None, 7.5, False, False, THEME["grey"]), layout.name
        fields = layout._element.xpath('.//a:fld[@type="slidenum"]')
        assert len(fields) == 1, layout.name          # slide number shows with no code


def test_app_xml_is_not_the_default_templates():
    import zipfile
    app = zipfile.ZipFile(TEMPLATE).read("docProps/app.xml").decode()
    assert "Macintosh" not in app and "On-screen Show (4:3)" not in app


def test_capacity_geometry():
    # full-budget text must fit: 15 checklist rows of 11pt need ~0.3in each; the question column is the full width
    prs = Presentation(TEMPLATE)
    lay = {l.name: {p.placeholder_format.idx: p for p in l.placeholders} for l in prs.slide_layouts}
    assert lay["checklist"][12].height >= Inches(15 * 0.3 + 0.4)
    assert lay["risk_reward"][16].height >= Inches(2.8)       # five short-pitch lines at 10pt
    assert lay["risks"][14].height >= Inches(1.8)             # four 170-char tripwires
    assert lay["summary"][14].height >= Inches(1.5)           # three 170-char bullets
