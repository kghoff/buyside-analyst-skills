"""Build the write-pitch PowerPoint template (navy banker style): python3 make_template.py --out assets/pitch_template.pptx

One master, 16 layouts named exactly as common.CORE_TYPES + common.SUPPORT_LAYOUTS. The builder finds a layout by
NAME and a placeholder by its idx, so the user can restyle the .pptx (colours, fonts, positions) and the builder
keeps working. Colours and font come from common.THEME.

Placeholder idx convention (same on every layout)
  0  title (navy bar, white bold)      10 takeaway (light band, italic)      11 source line (grey 7.5pt)
  12 and up: body areas and pictures, as listed below. "pic" = picture placeholder; "text" = bullets or a boxed
  paragraph; "area" = a frame for a table, chart or native object the builder draws at that position (it may also
  hold plain text). Unused placeholders should be deleted by the builder.
  The slide number is a plain field drawn on the layout (not a placeholder), so it shows without any code.

  title      12 pic (the cover picture)
  summary    12 area (cap table, left)  13 area (our-vs-Street grid, right)  14 text (bullets, bottom)
  setup      12 text (bullets, left)  13 pic (price chart, right)
  thesis     12, 13, 14 headbox: three columns, one per point
  risks      12 headbox (risk 1, left)  13 headbox (risk 2, right)  14 strip (tripwires, bottom, every paragraph bulleted)
  why_now    12 text (bullets, left)  13 box (the alpha bucket, right, plain)
  valuation  12 text (bullets, left)  13 pic (P/E history chart, right)
  different  12 area (ours vs Street table, top)  13 text (bullets, bottom)
  risk_reward 12 area (cases table, top left)  13 area (R/R ladder, below it)  14 pic (chart, top right)
             15 text (IRR line, three R's line, Watch lead; bottom left)  16 small (the 5 short-pitch lines; bottom right)
  catalysts  12 text (bullets, left)  13 bulbox (tripwires, right, bulleted)
  text_chart 12 text (bullets, left)  13 pic (right)
  table      12 area (one wide table)
  quote      12 text (the quotes, wide)  13 text (what they prove, bottom)
  two_column 12 colbox (left)  13 colbox (right)
  image      12 pic (wide)  13 caption (one plain line)
  checklist  12 area (one wide table of question / answer: 15 rows x 90 chars fit at 11pt with the question
             column at least 10in wide)

Paragraph levels (python-pptx paragraph.level, 0-based). The template styles them so the builder only sets the level:
  text, small, strip, bulbox   level 0 = bullet (every paragraph)
  headbox   level 0 = bold head (no bullet), level 1 = plain paragraph, level 2 = bullet   (thesis, risks)
  colbox    level 0 = bold head (no bullet), level 1 = bullet                                 (two_column)
  box, caption   level 0 = plain
A short idx 16 stays empty on a long call; delete it.
"""
import argparse
import datetime
import io
import os
import re
import sys
import zipfile

from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.packuri import PackURI
from pptx.parts.slide import SlideLayoutPart
from pptx.util import Emu
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CORE_TYPES
from common import SUPPORT_LAYOUTS
from common import THEME

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
W, H = 13.333, 7.5
LM, CW = 0.4, 12.533                      # left margin and content width, inches
TOP, BOT = 1.35, 6.9                      # body area from just under the takeaway band to just above the footer


def emu(v):
    return int(round(v * 914400))


def xfrm(x, y, w, h):
    return f'<a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'


def rpr(sz, color, bold=False, italic=False, tag="defRPr"):
    return (f'<a:{tag} lang="en-US" sz="{int(sz * 100)}" b="{int(bold)}" i="{int(italic)}">'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:latin typeface="{THEME["font"]}"/><a:cs typeface="{THEME["font"]}"/></a:{tag}>')


def sp(id_, name, ph, geom, fill=None, line=None, body="", anchor="t", ins=(0.08, 0.05), lst="", prompt="Text"):
    fill_x = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>'
    line_x = (f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else '<a:ln><a:noFill/></a:ln>')
    body_pr = (f'<a:bodyPr wrap="square" lIns="{emu(ins[0])}" tIns="{emu(ins[1])}" rIns="{emu(ins[0])}" '
               f'bIns="{emu(ins[1])}" anchor="{anchor}"><a:normAutofit/></a:bodyPr>')
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{id_}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f'<p:nvPr>{ph}</p:nvPr></p:nvSpPr><p:spPr>{xfrm(*geom)}{fill_x}{line_x}</p:spPr>'
            f'<p:txBody>{body_pr}<a:lstStyle>{lst}</a:lstStyle><a:p><a:r><a:rPr lang="en-US"/><a:t>{prompt}</a:t></a:r></a:p>'
            f'</p:txBody></p:sp>')


def lvl(n, sz, color, bullet=False, bold=False, italic=False):
    """List-level style n (1 = first paragraph, python-pptx paragraph.level 0)."""
    bu = (f'<a:buClr><a:srgbClr val="{THEME["navy"]}"/></a:buClr><a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>'
          if bullet else '<a:buNone/>')
    mar = 'marL="171450" indent="-171450"' if bullet else 'marL="0" indent="0"'
    return (f'<a:lvl{n}pPr {mar} algn="l"><a:spcBef><a:spcPts val="{300 if bullet else 200}"/></a:spcBef>{bu}'
            f'{rpr(sz, color, bold, italic)}</a:lvl{n}pPr>')


def lvl1(sz, color, bullet=False, bold=False, italic=False):
    return lvl(1, sz, color, bullet, bold, italic)


def chrome(first_id):
    """Footer slide-number field (a plain shape) on every layout."""
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{first_id}" name="Slide number"/><p:cNvSpPr txBox="1"/><p:nvPr userDrawn="1"/></p:nvSpPr>'
            f'<p:spPr>{xfrm(W - 1.0, 7.05, 0.6, 0.3)}<a:noFill/></p:spPr><p:txBody><a:bodyPr wrap="square" lIns="0" '
            f'tIns="0" rIns="0" bIns="0" anchor="ctr"/><a:lstStyle/><a:p><a:pPr algn="r"/><a:fld id="{{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}}" type="slidenum">'
            f'{rpr(7.5, THEME["grey"], tag="rPr")}<a:t>&#8249;#&#8250;</a:t></a:fld></a:p></p:txBody></p:sp>')


# (kind, geometry) per idx, per layout. kinds: text (bullets), box (boxed paragraph), strip (grey strip), area, pic
def full(h, y=TOP):
    return (LM, y, CW, h)


LAYOUTS = {
    "title": {12: ("pic", (LM, TOP, CW, BOT - TOP))},
    "summary": {12: ("area", (LM, TOP, 4.0, 3.7)), 13: ("area", (4.6, TOP, 8.33, 3.7)),
                14: ("text", (LM, 5.2, CW, BOT - 5.2))},   # 3 bullets x 170 chars at 13pt = 6 lines, fits
    "setup": {12: ("text", (LM, TOP, 4.9, BOT - TOP)), 13: ("pic", (5.5, TOP, 7.43, BOT - TOP))},
    "thesis": {12: ("headbox", (LM, TOP, 4.0, BOT - TOP)), 13: ("headbox", (4.67, TOP, 4.0, BOT - TOP)),
               14: ("headbox", (8.93, TOP, 4.0, BOT - TOP))},
    "risks": {12: ("headbox", (LM, TOP, 6.1, 3.5)), 13: ("headbox", (6.83, TOP, 6.1, 3.5)),
              14: ("strip", (LM, 4.95, CW, BOT - 4.95))},
    "why_now": {12: ("text", (LM, TOP, 7.4, BOT - TOP)), 13: ("box", (8.0, TOP, 4.93, 2.6))},
    "valuation": {12: ("text", (LM, TOP, 4.9, BOT - TOP)), 13: ("pic", (5.5, TOP, 7.43, BOT - TOP))},
    "different": {12: ("area", (LM, TOP, CW, 3.2)), 13: ("text", (LM, 4.7, CW, BOT - 4.7))},
    # left: cases, ladder, then the IRR / three R's / lead lines; right: chart, then the short-pitch lines
    # (5 fields x 170 chars at 10pt = 15 lines in a 6in column, fits). Lead (Watch) and short never appear together.
    "risk_reward": {12: ("area", (LM, TOP, 6.3, 1.75)), 13: ("area", (LM, 3.2, 6.3, 1.7)),
                    14: ("pic", (6.9, TOP, 6.03, 2.6)), 15: ("text", (LM, 5.0, 6.3, BOT - 5.0)),
                    16: ("small", (6.9, 4.05, 6.03, BOT - 4.05))},
    "catalysts": {12: ("text", (LM, TOP, 7.6, BOT - TOP)), 13: ("bulbox", (8.2, TOP, 4.73, 3.4))},
    "text_chart": {12: ("text", (LM, TOP, 4.9, BOT - TOP)), 13: ("pic", (5.5, TOP, 7.43, BOT - TOP))},
    "table": {12: ("area", (LM, TOP, CW, BOT - TOP))},
    "quote": {12: ("text", (LM, TOP, CW, 3.9)), 13: ("text", (LM, 5.4, CW, BOT - 5.4))},
    "two_column": {12: ("colbox", (LM, TOP, 6.1, BOT - TOP)), 13: ("colbox", (6.83, TOP, 6.1, BOT - TOP))},
    "image": {12: ("pic", (LM, TOP, CW, 5.0)), 13: ("caption", (LM, 6.45, CW, 0.45))},
    "checklist": {12: ("area", (LM, TOP, CW, BOT - TOP))},
}
NAMES = CORE_TYPES + SUPPORT_LAYOUTS
assert sorted(LAYOUTS) == sorted(NAMES), "LAYOUTS must cover exactly CORE_TYPES + SUPPORT_LAYOUTS"


def body_shape(i, idx, kind, geom):
    t = THEME
    name = f"Body {idx}"
    if kind == "pic":
        return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Picture {idx}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                f'<p:nvPr><p:ph type="pic" idx="{idx}"/></p:nvPr></p:nvSpPr><p:spPr>{xfrm(*geom)}<a:noFill/>'
                f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{t["line"]}"/></a:solidFill></a:ln></p:spPr>'
                f'<p:txBody><a:bodyPr anchor="ctr"/><a:lstStyle>{lvl1(10, t["grey"])}</a:lstStyle>'
                f'<a:p><a:r><a:rPr lang="en-US"/><a:t>Picture</a:t></a:r></a:p></p:txBody></p:sp>')
    ph = f'<p:ph type="body" sz="quarter" idx="{idx}"/>'
    tx, nv = t["text"], t["navy"]
    if kind == "text":
        return sp(i, name, ph, geom, lst=lvl(1, 13, tx, bullet=True), prompt="Bullets")
    if kind == "small":
        return sp(i, name, ph, geom, lst=lvl(1, 10, tx, bullet=True), prompt="Bullets")
    if kind == "box":
        return sp(i, name, ph, geom, line=t["line"], ins=(0.12, 0.1), lst=lvl(1, 12, tx), prompt="Box")
    if kind == "headbox":
        return sp(i, name, ph, geom, line=t["line"], ins=(0.12, 0.1), prompt="Head, then text",
                  lst=lvl(1, 13, nv, bold=True) + lvl(2, 12, tx) + lvl(3, 12, tx, bullet=True))
    if kind == "colbox":
        return sp(i, name, ph, geom, line=t["line"], ins=(0.12, 0.1), prompt="Head, then bullets",
                  lst=lvl(1, 13, nv, bold=True) + lvl(2, 12, tx, bullet=True))
    if kind == "bulbox":
        return sp(i, name, ph, geom, line=t["line"], ins=(0.12, 0.1), lst=lvl(1, 11, tx, bullet=True), prompt="Bullets")
    if kind == "strip":
        return sp(i, name, ph, geom, fill=t["strip"], anchor="ctr", ins=(0.12, 0.05),
                  lst=lvl(1, 11, tx, bullet=True), prompt="Bullets")
    if kind == "caption":
        return sp(i, name, ph, geom, fill=t["strip"], anchor="ctr", ins=(0.12, 0.05), lst=lvl(1, 11, tx), prompt="Caption")
    return sp(i, name, ph, geom, lst=lvl(1, 10, tx), prompt="Table, chart or text area")


def layout_xml(name):
    t = THEME
    shapes = [
        sp(2, "Title", '<p:ph type="title"/>', (0, 0, W, 0.62), fill=t["navy"], anchor="ctr", ins=(LM, 0.04),
           lst=lvl(1, 20, "FFFFFF", bold=True), prompt="Title"),
        sp(3, "Takeaway", '<p:ph type="body" sz="quarter" idx="10"/>', (0, 0.62, W, 0.58), fill=t["band"], anchor="ctr",
           ins=(LM, 0.03), lst=lvl(1, 12, t["text"], italic=True), prompt="Takeaway: the one sentence to remember"),
        sp(4, "Source", '<p:ph type="body" sz="quarter" idx="11"/>', (LM, 7.05, W - 2.0 - LM + 0.6, 0.3), anchor="ctr",
           ins=(0, 0), lst=lvl(1, 7.5, t["grey"]), prompt="Source"),
    ]
    for n, (idx, (kind, geom)) in enumerate(sorted(LAYOUTS[name].items())):
        shapes.append(body_shape(5 + n, idx, kind, geom))
    shapes.append(chrome(5 + len(LAYOUTS[name])))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout {NS} preserve="1" userDrawn="1">'
            f'<p:cSld name="{name}"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            f'<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            f'{"".join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>').encode()


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(emu(W)), Emu(emu(H))
    master = prs.slide_master
    # the default master was drawn for 4:3; stretch its shapes to 16:9 so it is sane if the user edits it
    for shp in master.shapes:
        shp.left, shp.width = int(shp.left * W / 10), int(shp.width * W / 10)
    # Arial everywhere unless a run says otherwise
    theme = master.part.part_related_by(RT.THEME)
    theme._blob = re.sub(rb'typeface="(Calibri Light|Calibri)"', b'typeface="Arial"', theme.blob)
    # drop the default layouts, then add ours
    lst = master._element.find('{http://schemas.openxmlformats.org/presentationml/2006/main}sldLayoutIdLst')
    for el in list(lst):
        master.part.drop_rel(el.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'))
        lst.remove(el)
    for n, name in enumerate(NAMES, 1):
        part = SlideLayoutPart.load(PackURI(f"/ppt/slideLayouts/slideLayout{n}.xml"),
                                    "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
                                    prs.part.package, layout_xml(name))
        part.relate_to(master.part, RT.SLIDE_MASTER)
        rid = master.part.relate_to(part, RT.SLIDE_LAYOUT)
        e = etree.SubElement(lst, '{http://schemas.openxmlformats.org/presentationml/2006/main}sldLayoutId')
        e.set('id', str(2147483649 + n))
        e.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', rid)
    for part in prs.part.package.iter_parts():       # app.xml names the default template's 4:3 / Mac PowerPoint
        if str(part.partname) == "/docProps/app.xml":
            part._blob = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                          b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                          b'<Application>write-pitch</Application><PresentationFormat>Widescreen</PresentationFormat>'
                          b'</Properties>')
    cp = prs.core_properties
    cp.author = cp.last_modified_by = "write-pitch"
    cp.title, cp.subject, cp.keywords, cp.comments, cp.category = "write-pitch template", "", "", "", ""
    cp.created = cp.modified = datetime.datetime(2026, 1, 1)
    cp.revision = 1
    return prs


def write(out):
    buf = io.BytesIO()
    build().save(buf)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # fixed zip timestamps so a rerun gives the same bytes
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, zin.read(info.filename))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    write(args.out)
    print("wrote", args.out)
