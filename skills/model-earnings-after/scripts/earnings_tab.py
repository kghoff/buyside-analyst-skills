"""The Earnings tab model-earnings-before wrote: refs to the cells bands 9-15 read (by their column-A labels, so a
moved row still reads right), band 7's frozen forecast, and where band 9 starts. splice() replaces every row from
band 9 down with new rows and keeps every row above byte for byte (the tab may have been saved by Excel or openpyxl
since: shared strings, their row attributes and styles are all kept as they are).

Labels repeat across bands (Revenue, Units, EPS appear in bands 4 and 6), so each key is looked up only inside
the band LABELS names for it."""
import html
import re

import openpyxl

from xlsx import CT, NS_REL, colnum, esc, relpath_of, resolve

TAB = "Earnings"
FROZEN_RE = re.compile(r"^7\. FROZEN FORECAST: (.+?), frozen (\d{4}-\d{2}-\d{2})")   # model-earnings-before build.py
AFTER_RE = re.compile(r"^9\. ACTUAL VS FROZEN")
TITLE_RE = re.compile(r"^\S+ after the print: ")             # build.py's title row, just above band 9
BAND_RE = re.compile(r"^(\d+)\. [A-Z][A-Z0-9 ,/-]{3}")        # band headers: "1. PRINT SNAPSHOT AND THE CALL"
ROW_RE = re.compile(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', re.S)
LABELS = {  # key: (exact label or prefix, prefix?, band) -- model-earnings-before build.py INPUTS and band texts
    "price": ("Price", False, 1), "stance": ("Stance (", True, 1),
    "call_q": ("The quarter: beat / in line / miss", False, 1),
    "call_g": ("The guide: raise / hold / cut / initiate / none given", False, 1),
    "expected_move": ("Expected move on the day, either way", False, 1),
    "up": ("Move up", False, 2), "down": ("Move down", False, 2), "p_beat": ("Our P(upside case)", False, 2),
    "implied": ("Options-implied move", True, 5)}


def part(pkg):
    return {s[0]: s for s in pkg.sheets()}[TAB][3]


def _bands(a):
    """{band number: (header row, last row)} from the column-A band headers."""
    heads = sorted((r, int(m.group(1))) for r, v in a.items() if (m := BAND_RE.match(v)))
    last = max(a, default=0)
    return {n: (r, (heads[i + 1][0] - 1) if i + 1 < len(heads) else last) for i, (r, n) in enumerate(heads)}


def read(path):
    """None if there is no Earnings tab, else {refs: {key: "$B$n"}, frozen: {quarter, date, fy, rows: [{label, row,
    q, fy}]} or None, bands: {n: (header row, last row)}, after_start: band 9's row (its title row when build.py
    wrote one above it) or None, end: last row of bands
    1-8, start: where band 9 goes, labels: {row: column-A text}}."""
    wb = openpyxl.load_workbook(path, read_only=True)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    ws = wb[TAB]
    ws.reset_dimensions()       # read-only mode trusts <dimension>, which need not cover what the user typed
    full = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row
            if getattr(c, "value", None) is not None}
    wb.close()
    g = {k: v for k, v in full.items() if k[1] <= 3}
    a = {r: v for (r, c), v in g.items() if c == 1 and isinstance(v, str)}
    after = next((r for r, v in sorted(a.items()) if AFTER_RE.match(v)), None)
    if after and TITLE_RE.match(a.get(after - 1, "")):
        after -= 1                                            # the title belongs to bands 9-15: replaced with them
    bands = _bands(a)
    refs = {}
    for k, (lab, pre, band) in LABELS.items():
        if band not in bands:
            continue
        lo, hi = bands[band]
        r = next((r for r in range(lo + 1, hi + 1) if isinstance(a.get(r), str)
                  and (a[r].startswith(lab) if pre else a[r] == lab)), None)
        if r:
            refs[k] = f"$B${r}"
    top = next(((r, m) for r, v in sorted(a.items()) if (m := FROZEN_RE.match(v))), None)
    frozen = None
    if top:
        r0, m = top
        rows, r = [], r0 + 2
        while isinstance(a.get(r), str) and not BAND_RE.match(a[r]):
            rows.append({"label": a[r], "row": r, "q": g.get((r, 2)), "fy": g.get((r, 3))})
            r += 1
        frozen = {"quarter": m.group(1), "date": m.group(2), "fy": g.get((r0 + 1, 3)), "rows": rows}
    end = max((r for (r, c) in full if after is None or r < after), default=0)    # every column: a user's E30
    return {"refs": refs, "frozen": frozen, "bands": bands, "after_start": after, "end": end,
            "start": after if after else end + 2, "labels": a}


def _row_of(ref):
    return int(re.match(r"[A-Z]+(\d+)$", ref).group(1))


def _comment_texts(xml):
    """{ref: plain text} of a comments part, for messages only (kept notes are never regenerated). Excel splits a
    note into runs, may write an empty run as <t/>, and adds phonetic <rPh> text that is not part of the note."""
    out = {}
    for m in re.finditer(r'<comment ref="([A-Z]+\d+)"[^>]*>(.*?)</comment>', xml, re.S):
        body = re.sub(r"<rPh\b.*?</rPh>", "", m.group(2), flags=re.S)
        runs = re.findall(r"<t(?:\s[^>]*?)?(?:/>|>(.*?)</t>)", body, re.S)
        out[m.group(1)] = html.unescape("".join(runs))
    return out


def _refuse(msg):
    raise SystemExit(f"model-earnings-after stopped: {msg}")


# ---------------------------------------------------------------- VML note shapes
SHAPE_RE = re.compile(r"<(\w+):shape\b[^>]*?(?:/>|>.*?</\1:shape>)", re.S)     # not shapetype / shapelayout
IDMAP_RE = re.compile(r'(<\w+:idmap\b[^>]*?data=")([\d,\s]*)(")')
VML_NS = ('xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
          'xmlns:x="urn:schemas-microsoft-com:office:excel"')
NOTE_TYPE = ('<v:shapetype ' + VML_NS + ' id="_x0000_t202" coordsize="21600,21600" o:spt="202" '
             'path="m,l,21600r21600,l21600,xe"><v:stroke joinstyle="miter"/><v:path gradientshapeok="t" '
             'o:connecttype="rect"/></v:shapetype>')


def _note_row(shape):
    """0-based row of a note shape, or None for any other shape (buttons, checkboxes...), which is always kept."""
    if not re.search(r'ObjectType="Note"', shape):
        return None
    m = re.search(r"<(?:\w+:)?Row>(\d+)</(?:\w+:)?Row>", shape)
    return int(m.group(1)) if m else None


def _note_shape(ref, sid):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    c, r = colnum(m.group(1)) - 1, int(m.group(2)) - 1
    return (f'<v:shape {VML_NS} id="_x0000_s{sid}" type="#_x0000_t202" style="position:absolute;margin-left:59.25pt;'
            'margin-top:1.5pt;width:240pt;height:80pt;z-index:1;visibility:hidden" fillcolor="#ffffe1" '
            'o:insetmode="auto"><v:fill color2="#ffffe1"/><v:shadow on="t" color="black" obscured="t"/>'
            '<v:path o:connecttype="none"/><v:textbox style="mso-direction-alt:auto"><div style="text-align:left"/>'
            '</v:textbox><x:ClientData ObjectType="Note"><x:MoveWithCells/><x:SizeWithCells/>'
            f"<x:Anchor>{c + 1}, 15, {r}, 2, {c + 5}, 15, {r + 5}, 16</x:Anchor><x:AutoFill>False</x:AutoFill>"
            f"<x:Row>{r}</x:Row><x:Column>{c}</x:Column></x:ClientData></v:shape>")


def _blocks(data):
    return [int(x) for x in re.findall(rb"\d+", data)]


def _vml(pkg, vpart, start, refs):
    """The tab's VML with note shapes on rows >= start dropped, every other shape byte for byte, and a new note
    shape per ref. New shape ids collide with no shape id in the workbook; the idmap gains blocks if needed."""
    vml = pkg.text(vpart) if vpart else (f'<xml {VML_NS}><o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data=""/>'
                                         "</o:shapelayout></xml>")
    vml = SHAPE_RE.sub(lambda m: "" if (r := _note_row(m.group(0))) is not None and r + 1 >= start
                       else m.group(0), vml)
    if not refs:
        return vml
    if not IDMAP_RE.search(vml):
        vml = re.sub(r"(<xml\b[^>]*>)", rf'\1<o:shapelayout {VML_NS} v:ext="edit"><o:idmap v:ext="edit" data=""/>'
                     "</o:shapelayout>", vml, count=1)
    others = [p for p in pkg.parts if p.endswith(".vml") and p != vpart]
    used = {int(x) for p in others for x in re.findall(rb"_x0000_s(\d+)", pkg.parts[p])}
    used |= {int(x) for x in re.findall(r"_x0000_s(\d+)", vml)}
    taken = {b for p in others for d in re.findall(rb'<\w+:idmap\b[^>]*?data="([\d,\s]*)"', pkg.parts[p])
             for b in _blocks(d)}
    own = [int(x) for x in re.findall(r"\d+", IDMAP_RE.search(vml).group(2))]
    blocks = [b for b in own if b not in taken]
    ids, fresh = [], max(taken | set(own) | {0}) + 1
    while len(ids) < len(refs):
        if not blocks:
            blocks.append(fresh)
            own.append(fresh)
            fresh += 1
        b = blocks[0]
        free = [i for i in range(1024 * b + 1, 1024 * (b + 1)) if i not in used]
        ids += free[:len(refs) - len(ids)]
        if len(ids) < len(refs):
            blocks.pop(0)
    vml = IDMAP_RE.sub(lambda m: m.group(1) + ",".join(str(b) for b in own) + m.group(3), vml, count=1)
    if 'id="_x0000_t202"' not in vml:
        vml = vml.replace("</xml>", NOTE_TYPE + "</xml>")
    return vml.replace("</xml>", "".join(_note_shape(ref, i) for ref, i in zip(refs, ids)) + "</xml>")


# ---------------------------------------------------------------- comments
EMPTY_COMMENTS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                  '<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><authors></authors>'
                  "<commentList></commentList></comments>")


def _comments(cx, start, notes, author="Claude"):
    """Comments with every <comment> on rows < start kept byte for byte (authors, rich text, xr:uid), those on
    rows >= start dropped, and `notes` appended under `author` (added to <authors> if missing)."""
    names = [html.unescape(a) for a in re.findall(r"<author>(.*?)</author>", cx, re.S)]
    if notes and author not in names:
        if re.search(r"<authors\s*/>", cx):
            cx = re.sub(r"<authors\s*/>", "<authors></authors>", cx, count=1)
        cx = cx.replace("</authors>", f"<author>{esc(author)}</author></authors>", 1)
        names.append(author)
    aid = names.index(author) if notes else 0
    m = re.search(r"<commentList>(.*?)</commentList>|<commentList\s*/>", cx, re.S)
    kept = [c.group(0) for c in re.finditer(r'<comment ref="([A-Z]+\d+)"[^>]*?(?:/>|>.*?</comment>)', m.group(1) or "",
                                            re.S) if _row_of(c.group(1)) < start]
    new = [f'<comment ref="{ref}" authorId="{aid}"><text><r><rPr><sz val="10"/><rFont val="Tahoma"/></rPr>'
           f'<t xml:space="preserve">{esc(t)}</t></r></text></comment>' for ref, t in notes.items()]
    return cx[:m.start()] + "<commentList>" + "".join(kept + new) + "</commentList>" + cx[m.end():]


def _threaded_rows(pkg, sheet_part, rels):
    out = []
    for typ, t in rels.values():
        if typ.endswith("/threadedComment"):
            out += [r for r in re.findall(r'<threadedComment\b[^>]*?\bref="([A-Z]+\d+)"',
                                          pkg.text(resolve(sheet_part, t)))]
    return out


def splice(pkg, sheet_part, start, sh, notes, after_start):
    """Replace rows >= start with sh's rows (a Sheet, rows numbered from start) and add `notes` ({ref: text}, on
    rows >= start). Rows, notes and VML shapes above start stay byte for byte. after_start is read()'s: with no
    band 9 yet, anything in the rows that would be dropped is the user's, so it stops instead. Merges and
    conditional formats from start down are dropped; sh must not carry its own (they would be lost here)."""
    if sh.merges or sh.cf or sh.comments:
        raise ValueError("splice() writes only sh's rows: pass notes separately; merges and formats unsupported")
    if any(r < start for (r, _) in sh.cells) or any(_row_of(k) < start for k in notes):
        raise ValueError(f"new rows and notes must start at row {start} or below")
    xml = pkg.text(sheet_part)
    rels = pkg.rels(relpath_of(sheet_part))
    cpart = next((resolve(sheet_part, t) for typ, t in rels.values() if typ.endswith("/comments")), None)
    vpart = next((resolve(sheet_part, t) for typ, t in rels.values() if typ.endswith("/vmlDrawing")), None)
    m = re.search(r"<sheetData>(.*?)</sheetData>|<sheetData/>", xml, re.S)
    rows = [(int(x.group(1)), x.group(0)) for x in ROW_RE.finditer(m.group(1) or "")]
    old_notes = _comment_texts(pkg.text(cpart)) if cpart else {}
    if after_start is None:
        cells = [c for r, x in rows if r >= start
                 for c in re.findall(r'<c r="([A-Z]+\d+)"[^>]*?(?<!/)>(?:(?!</c>).)*?<(?:v|f|is)\b', x, re.S)]
        cells += [k for k in old_notes if _row_of(k) >= start and k not in cells]
        if cells:
            _refuse(f"the Earnings tab has content below band 8 ({', '.join(cells[:10])}"
                    f"{'...' if len(cells) > 10 else ''}) and no band 9 yet, so it is yours. Move it above band 8 "
                    "or onto another tab, then rerun.")
    lost = [k for k in _threaded_rows(pkg, sheet_part, rels) if _row_of(k) >= start]
    if lost:
        _refuse(f"threaded comments on {', '.join(lost)} sit in the rows bands 9-15 replace. Move or delete them "
                "in Excel, then rerun.")
    new = re.search(r"<sheetData>(.*?)</sheetData>", sh.xml(), re.S).group(1)
    xml = xml[:m.start()] + "<sheetData>" + "".join(x for r, x in rows if r < start) + new + "</sheetData>" \
        + xml[m.end():]
    xml = re.sub(r'<mergeCell ref="[A-Z]+(\d+):[^"]*"/>',
                 lambda x: "" if int(x.group(1)) >= start else x.group(0), xml)
    n = len(re.findall(r"<mergeCell ", xml))
    xml = re.sub(r'<mergeCells count="\d+">', f'<mergeCells count="{n}">', xml)
    xml = re.sub(r'<mergeCells count="0">\s*</mergeCells>', "", xml)
    xml = re.sub(r'<conditionalFormatting sqref="[A-Z]+(\d+)[^"]*">.*?</conditionalFormatting>',
                 lambda x: "" if int(x.group(1)) >= start else x.group(0), xml, flags=re.S)
    maxr = max([int(r) for r in re.findall(r'<row r="(\d+)"', xml)] + [1])
    xml = re.sub(r'<dimension ref="([A-Z]+)\d+:([A-Z]+)\d+"/>', rf'<dimension ref="\g<1>1:\g<2>{maxr}"/>', xml)
    if notes or cpart:
        if not cpart:
            cpart = f"xl/comments{pkg.free('xl/comments{}.xml')}.xml"
            pkg.attach(sheet_part, "comments", cpart, CT["comments"])
            cx = EMPTY_COMMENTS
        else:
            cx = pkg.text(cpart)
        pkg.put(cpart, _comments(cx, start, notes))
        vml = _vml(pkg, vpart, start, list(notes))
        if not vpart:   # a tab that already has VML (form controls) keeps its one legacyDrawing; add one only here
            pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
            vpart = f"xl/drawings/vmlDrawing{pkg.free('xl/drawings/vmlDrawing{}.vml')}.vml"
            lrid = pkg.attach(sheet_part, "vml", vpart)
            if "<legacyDrawing " in xml:
                _refuse("the Earnings tab has a legacyDrawing with no VML part behind it; open and save it in Excel.")
            xml = re.sub(r"(<legacyDrawingHF|<drawingHF|<picture|<oleObjects|<controls|<webPublishItems|<tableParts"
                         r"|<extLst|</worksheet>)", f'<legacyDrawing xmlns:r="{NS_REL}" r:id="{lrid}"/>\\1', xml,
                         count=1)
        pkg.put(vpart, vml)
    pkg.put(sheet_part, xml)
