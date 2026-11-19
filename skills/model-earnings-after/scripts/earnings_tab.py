"""The Earnings tab model-earnings-before wrote: refs to the cells bands 9-15 read (by their column-A labels, so a
moved row still reads right), band 7's frozen forecast, and where band 9 starts. splice() replaces every row from
band 9 down with new rows and keeps every row above byte for byte (the tab may have been saved by Excel or openpyxl
since: shared strings, their row attributes and styles are all kept as they are).

Labels repeat across bands (Revenue, Units, EPS appear in bands 4 and 6), so each key is looked up only inside
the band LABELS names for it."""
import re

import openpyxl

from xlsx import CT, comments_parts, relpath_of, resolve, unesc

TAB = "Earnings"
FROZEN_RE = re.compile(r"^7\. FROZEN FORECAST: (.+?), frozen (\d{4}-\d{2}-\d{2})")   # model-earnings-before build.py
AFTER_RE = re.compile(r"^9\. ACTUAL VS FROZEN")
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
    q, fy}]} or None, bands: {n: (header row, last row)}, after_start: band 9's row or None, end: last row of bands
    1-8, start: where band 9 goes, labels: {row: column-A text}}."""
    wb = openpyxl.load_workbook(path, read_only=True)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    g = {(c.row, c.column): c.value for row in wb[TAB].iter_rows(max_col=3) for c in row
         if getattr(c, "value", None) is not None}
    wb.close()
    a = {r: v for (r, c), v in g.items() if c == 1 and isinstance(v, str)}
    after = next((r for r, v in sorted(a.items()) if AFTER_RE.match(v)), None)
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
    end = max((r for (r, c) in g if after is None or r < after), default=0)
    return {"refs": refs, "frozen": frozen, "bands": bands, "after_start": after, "end": end,
            "start": after if after else end + 2, "labels": a}


def _row_of(ref):
    return int(re.match(r"[A-Z]+(\d+)$", ref).group(1))


def _comment_texts(xml):
    """{ref: plain text} of a comments part (Excel may split a note into runs; <text> itself is not a run)."""
    out = {}
    for m in re.finditer(r'<comment ref="([A-Z]+\d+)"[^>]*>(.*?)</comment>', xml, re.S):
        out[m.group(1)] = unesc("".join(re.findall(r"<t(?:\s[^>]*)?>(.*?)</t>", m.group(2), re.S)))
    return out


def splice(pkg, sheet_part, start, sh, notes):
    """Replace rows >= start with sh's rows (a Sheet, rows numbered from start), and the tab's notes with the
    kept ones (rows < start) plus `notes`. Merges and conditional formats from start down are dropped; sh must
    not carry its own (they would be lost here, so it fails loud instead)."""
    if sh.merges or sh.cf or sh.comments:
        raise ValueError("splice() writes only sh's rows: pass notes separately; merges and formats unsupported")
    xml = pkg.text(sheet_part)
    m = re.search(r"<sheetData>(.*?)</sheetData>|<sheetData/>", xml, re.S)
    body = m.group(1) or ""
    kept = [x.group(0) for x in ROW_RE.finditer(body) if int(x.group(1)) < start]
    if any(r < start for (r, _) in sh.cells):
        raise ValueError(f"new rows must start at row {start} or below")
    new = re.search(r"<sheetData>(.*?)</sheetData>", sh.xml(), re.S).group(1)
    xml = xml[:m.start()] + "<sheetData>" + "".join(kept) + new + "</sheetData>" + xml[m.end():]
    xml = re.sub(r'<mergeCell ref="[A-Z]+(\d+):[^"]*"/>',
                 lambda x: "" if int(x.group(1)) >= start else x.group(0), xml)
    n = len(re.findall(r"<mergeCell ", xml))
    xml = re.sub(r'<mergeCells count="\d+">', f'<mergeCells count="{n}">', xml)
    xml = re.sub(r'<mergeCells count="0">\s*</mergeCells>', "", xml)
    xml = re.sub(r'<conditionalFormatting sqref="[A-Z]+(\d+)[^"]*">.*?</conditionalFormatting>',
                 lambda x: "" if int(x.group(1)) >= start else x.group(0), xml, flags=re.S)
    maxr = max([int(r) for r in re.findall(r'<row r="(\d+)"', xml)] + [1])
    xml = re.sub(r'<dimension ref="([A-Z]+)\d+:([A-Z]+)\d+"/>', rf'<dimension ref="\g<1>1:\g<2>{maxr}"/>', xml)
    rels = pkg.rels(relpath_of(sheet_part))
    cpart = next((resolve(sheet_part, t) for _, (typ, t) in rels.items() if typ.endswith("/comments")), None)
    vpart = next((resolve(sheet_part, t) for _, (typ, t) in rels.items() if typ.endswith("/vmlDrawing")), None)
    old = {k: v for k, v in (_comment_texts(pkg.text(cpart)) if cpart else {}).items() if _row_of(k) < start}
    allnotes = {**old, **notes}
    if allnotes or cpart:     # an existing comments part is rewritten even when no note is left
        # each VML drawing needs its own shape-id blocks; the idmap prefix is o: from Excel, ns0: from openpyxl
        ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml") and p != vpart
               for d in re.findall(rb'<\w+:idmap [^>]*?data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
        cx, vml = comments_parts(allnotes, max(ids + [0]) + 1)
        if not cpart:
            pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
            cpart = f"xl/comments{pkg.free('xl/comments{}.xml')}.xml"
            vpart = f"xl/drawings/vmlDrawing{pkg.free('xl/drawings/vmlDrawing{}.vml')}.vml"
            pkg.put(vpart, vml)
            lrid = pkg.attach(sheet_part, "vml", vpart)
            pkg.put(cpart, cx)
            pkg.attach(sheet_part, "comments", cpart, CT["comments"])
            xml = re.sub(r"(<legacyDrawingHF|<picture|<oleObjects|<controls|<webPublishItems|<tableParts|<extLst"
                         r"|</worksheet>)",
                         f'<legacyDrawing xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                         f'relationships" r:id="{lrid}"/>\\1', xml, count=1)
        else:
            pkg.put(cpart, cx)
            pkg.put(vpart, vml)
    pkg.put(sheet_part, xml)
