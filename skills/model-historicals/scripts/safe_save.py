"""Save an openpyxl-edited workbook WITHOUT letting openpyxl rewrite the user's file.

openpyxl drops text boxes, shapes, pictures and equations and re-serialises charts when it saves. Skills that edit
with openpyxl call safe_save(wb, src, out) instead of wb.save(out):
1. openpyxl saves its result to a temp file (only to read it back);
2. The user's original file (src) is opened raw, and every row move the skill made (logged by log_move from its
   insert / delete / remap functions) is replayed on it: rows renumbered or dropped, every reference shifted on every
   tab, in charts, notes, shapes' anchors, merged cells, conditional formats and defined names;
3. every cell whose value, formula or style differs from openpyxl's result is written into the raw file (styles
   appended to styles.xml), row heights too; a tab whose notes changed gets its notes rebuilt from openpyxl's;
4. the result must equal openpyxl's result, tab by tab (values, formulas, styles, notes, merges, row heights, column
   widths, frozen panes), or nothing is written (SystemExit). Every other part of the file is copied byte for byte.
Canonical copy in model-historicals; model-ratios and model-kpis carry copies (keep in sync). Needs xlsx.py."""
import datetime as dt
import os
import re
import shutil
import tempfile

import openpyxl
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles.numbers import BUILTIN_FORMATS_REVERSE
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.utils.datetime import to_excel
from openpyxl.xml.functions import tostring

from xlsx import CT, RT, Package, colname, colnum, comments_parts, esc, relpath_of, resolve, unesc

CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
ROWONLY = re.compile(r"^(\$?)(\d+)$")


class RefIntoDeleted(ValueError):
    pass


# ---------------------------------------------------------------- logging row moves (called by the skills)
def log_move(ws, fn):
    """Record a row move on ws: fn(old row) -> new row, or None if the row was deleted. Call it from the skill's own
    insert / delete / remap function, in the order the moves happen."""
    wb = ws.parent
    if not hasattr(wb, "_safe_moves"):
        wb._safe_moves = []
    wb._safe_moves.append((ws.title, fn))


def insert_fn(at, n):
    return lambda r: r if r < at else r + n


def delete_fn(at, n):
    return lambda r: r if r < at else (None if r < at + n else r - n)


def move_fn(start, end, before):
    """Rows start..end (inclusive) moved to sit just above row `before` (Excel's cut + insert cut cells)."""
    n = end - start + 1
    if start <= before <= end + 1:
        return lambda r: r
    if before > end:                                   # moving down
        return lambda r: r - n if end < r < before else (before - n + (r - start) if start <= r <= end else r)
    return lambda r: r + n if before <= r < start else (before + (r - start) if start <= r <= end else r)


def remap_fn(new_of, max_row):
    olds = sorted(new_of)
    tail = new_of[olds[-1]] - olds[-1] if olds else 0
    return lambda r: new_of.get(r) if r <= max_row else r + tail


# ---------------------------------------------------------------- raw row remap
def _map_part(p, fn, soft=False):
    m = CELL.match(p) or ROWONLY.match(p)
    if not m:
        return p
    r = int(m.group(m.lastindex))
    new = fn(r)
    if new is None:
        if not soft:
            raise RefIntoDeleted(r)
        k = r
        while new is None and k > 1:                 # a range edge in deleted rows: the nearest surviving row above
            k -= 1
            new = fn(k)
        new = new or 1
    head = m.group(0)[:m.start(m.lastindex)]
    return f"{head}{new}"


def _sheet_of(prefix):
    s = prefix[:-1]
    return s[1:-1].replace("''", "'") if s.startswith("'") and s.endswith("'") else s


def _check_span(parts, fn):
    """A range must move as one piece (a move can't split it: Excel would point it at different cells)."""
    rows = []
    for p in parts:
        m = CELL.match(p) or ROWONLY.match(p)
        if m:
            rows.append(int(m.group(m.lastindex)))
    if len(rows) == 2 and rows[1] > rows[0]:
        if any(fn(r) is not None and fn(r + 1) is not None and fn(r + 1) != fn(r) + 1 for r in range(rows[0], rows[1])):
            raise RefIntoDeleted(f"range rows {rows[0]}-{rows[1]} would be split by the move")


def map_ref(text, local, target, fn, soft=False, strict=False):
    if "!" in text:
        i = text.rindex("!")
        prefix, refs = text[:i + 1], text[i + 1:]
        if _sheet_of(prefix) != target:
            return text
    else:
        if local != target:
            return text
        prefix, refs = "", text
    if strict:
        _check_span(refs.split(":"), fn)
    return prefix + ":".join(_map_part(p, fn, soft) for p in refs.split(":"))


def map_formula(formula, local, target, fn, strict=False):
    eq = formula.startswith("=")
    tok = Tokenizer(formula if eq else "=" + formula)
    changed = False
    for t in tok.items:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            v = map_ref(t.value, local, target, fn, strict=strict)
            changed |= v != t.value
            t.value = v
    if not changed:
        return formula
    out = tok.render()
    return out if eq else out[1:]


C_ELEM = re.compile(r'<c r="([A-Z]+)(\d+)"[^>]*?(?:/>|>.*?</c>)', re.S)
F_SHARED = re.compile(r'<f t="shared"([^>]*?)(?:/>|>(.*?)</f>)', re.S)
ROW_ELEM = re.compile(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', re.S)


def unshare_all(xml):
    """Write every shared formula out cell by cell (a row move or a rewrite can break their offsets)."""
    masters = {}
    for m in C_ELEM.finditer(xml):
        f = F_SHARED.search(m.group(0))
        if f and f.group(2) is not None:
            masters[re.search(r'si="(\d+)"', f.group(1)).group(1)] = (m.group(1) + m.group(2), unesc(f.group(2)))
    if not masters:
        return xml

    def cell(m):
        c = m.group(0)
        f = F_SHARED.search(c)
        if not f:
            return c
        origin, fx = masters[re.search(r'si="(\d+)"', f.group(1)).group(1)]
        ref = m.group(1) + m.group(2)
        text = fx if ref == origin else Translator("=" + fx, origin=origin).translate_formula(ref)[1:]
        return c[:f.start()] + f"<f>{esc(text)}</f>" + c[f.end():]
    return C_ELEM.sub(cell, xml)


def _sheet_subparts(pkg, part, types):
    return [(typ, resolve(part, tgt)) for _, (typ, tgt) in pkg.rels(relpath_of(part)).items() if typ in types]


def remap_rows(pkg, target, fn, strict=False):
    """Apply a row move (fn: old row -> new row or None) to tab `target` of a raw package, the way Excel would.
    strict=True (a block move): a range that the move would split raises RefIntoDeleted; rows are re-sorted."""
    for name, _, _, part in pkg.sheets():
        xml = unshare_all(pkg.text(part))
        if name == target:
            xml = ROW_ELEM.sub(lambda m: "" if fn(int(m.group(1))) is None else m.group(0), xml)
        xml = re.sub(r"<f\b([^>]*?)(?<!/)>(.*?)</f>",
                     lambda m: f"<f{m.group(1)}>{esc(map_formula(unesc(m.group(2)), name, target, fn, strict))}</f>", xml, flags=re.S)
        if name == target:
            xml = re.sub(r'(<row r=")(\d+)"', lambda m: f'{m.group(1)}{fn(int(m.group(2)))}"', xml)
            xml = re.sub(r'(<c r=")([A-Z]+)(\d+)"', lambda m: f'{m.group(1)}{m.group(2)}{fn(int(m.group(3)))}"', xml)
            if strict:                                   # a block move: put the rows back in order
                sd = re.search(r"<sheetData>(.*?)</sheetData>", xml, re.S)
                if sd:
                    rows = sorted(ROW_ELEM.finditer(sd.group(1)), key=lambda m: int(m.group(1)))
                    xml = xml[:sd.start(1)] + "".join(m.group(0) for m in rows) + xml[sd.end(1):]
            soft = lambda t: map_ref(t, target, target, fn, soft=True)
            xml = re.sub(r'(<dimension ref=")([^"]+)"', lambda m: f'{m.group(1)}{soft(m.group(2))}"', xml)
            xml = re.sub(r'(sqref=")([^"]+)"', lambda m: m.group(1) + " ".join(soft(s) for s in m.group(2).split()) + '"', xml)
            xml = re.sub(r'(topLeftCell=")([^"]+)"', lambda m: f'{m.group(1)}{soft(m.group(2))}"', xml)
            xml = re.sub(r'(activeCell=")([^"]+)"', lambda m: f'{m.group(1)}{soft(m.group(2))}"', xml)

            def merge(m):
                try:
                    return f'<mergeCell ref="{map_ref(m.group(1), target, target, fn)}"/>'
                except RefIntoDeleted:
                    return ""
            xml = re.sub(r'<mergeCell ref="([^"]+)"\s*/>', merge, xml)
            xml = re.sub(r'<mergeCells count="\d+"', lambda m: f'<mergeCells count="{xml.count("<mergeCell ref=")}"', xml)
            for typ, sub in _sheet_subparts(pkg, part, (RT["comments"], RT["vml"], RT["drawing"])):
                t = pkg.text(sub)
                if typ == RT["comments"]:
                    t = re.sub(r"<comment ref=\"([^\"]+)\".*?</comment>",
                               lambda m: "" if fn(int(re.search(r"\d+", m.group(1)).group(0))) is None else
                               m.group(0).replace(f'ref="{m.group(1)}"', f'ref="{map_ref(m.group(1), target, target, fn)}"', 1),
                               t, flags=re.S)
                elif typ == RT["vml"]:                   # 0-based rows
                    z = lambda r0: _map_part(str(r0 + 1), fn, soft=True)
                    t = re.sub(r"<x:Row>(\d+)</x:Row>", lambda m: f"<x:Row>{int(z(int(m.group(1)))) - 1}</x:Row>", t)

                    def anc(m):
                        v = [x.strip() for x in m.group(1).split(",")]
                        for k in (2, 6):
                            v[k] = str(int(z(int(v[k]))) - 1)
                        return "<x:Anchor>" + ", ".join(v) + "</x:Anchor>"
                    t = re.sub(r"<x:Anchor>([^<]+)</x:Anchor>", anc, t)
                else:                                    # shapes' anchors: <xdr:row> is 0-based
                    t = re.sub(r"<(xdr:)?row>(\d+)</(?:xdr:)?row>",
                               lambda m: f"<{m.group(1) or ''}row>{int(_map_part(str(int(m.group(2)) + 1), fn, soft=True)) - 1}</{m.group(1) or ''}row>", t)
                pkg.put(sub, t)
        pkg.put(part, xml)
    for p in [p for p in pkg.parts if p.startswith("xl/charts/chart") and p.endswith(".xml")]:
        t = pkg.text(p)
        t2 = re.sub(r"<(c:)?f>(.*?)</(?:c:)?f>",
                    lambda m: f"<{m.group(1) or ''}f>{esc(map_formula(unesc(m.group(2)), None, target, fn, strict))}</{m.group(1) or ''}f>", t)
        if t2 != t:
            pkg.put(p, t2)
    wb = pkg.text("xl/workbook.xml")
    wb = re.sub(r"(<definedName\b[^>]*>)(.*?)(</definedName>)",
                lambda m: m.group(1) + esc(map_formula(unesc(m.group(2)), None, target, fn, strict)) + m.group(3), wb, flags=re.S)
    pkg.put("xl/workbook.xml", wb)


# ---------------------------------------------------------------- styles
def style_key(c):
    return tuple(tostring(x.to_tree()) for x in (c.font, c.fill, c.border, c.alignment, c.protection)) + (c.number_format,)


class RawStyles:
    """Appends fonts / fills / borders / numFmts / cellXfs to styles.xml from openpyxl style objects."""
    TAGS = {"numFmts": "numFmt", "fonts": "font", "fills": "fill", "borders": "border", "cellXfs": "xf"}

    def __init__(self, xml):
        self.xml = xml
        self.items, self.new = {}, {t: [] for t in self.TAGS}
        for tag, child in self.TAGS.items():
            m = re.search(rf"<{tag}\b[^>]*?(?:/>|>(.*?)</{tag}>)", xml, re.S)
            self.items[tag] = re.findall(rf"<{child}\b[^>]*?(?:/>|>.*?</{child}>)", m.group(1) or "", re.S) if m else []
        self.fmt = {unesc(m.group(2)): int(m.group(1)) for m in re.finditer(r'<numFmt numFmtId="(\d+)" formatCode="([^"]*)"/>', xml)}
        self.cache = {}

    def _add(self, tag, x):
        allx = self.items[tag] + self.new[tag]
        if x in allx:
            return allx.index(x)
        self.new[tag].append(x)
        return len(allx)

    def numfmt(self, code):
        if code in BUILTIN_FORMATS_REVERSE:
            return BUILTIN_FORMATS_REVERSE[code]
        if code not in self.fmt:
            self.fmt[code] = max([163] + list(self.fmt.values())) + 1
            self.new["numFmts"].append(f'<numFmt numFmtId="{self.fmt[code]}" formatCode="{esc(code)}"/>')
        return self.fmt[code]

    def xf_for(self, c):
        k = style_key(c)
        if k not in self.cache:
            f = self._add("fonts", _s(c.font.to_tree()))
            fl = self._add("fills", _s(c.fill.to_tree()))
            b = self._add("borders", _s(c.border.to_tree()))
            n = self.numfmt(c.number_format)
            al, pr = _s(c.alignment.to_tree()), _s(c.protection.to_tree())
            body = (al if al != "<alignment />" and al != "<alignment/>" else "") + (pr if pr not in ("<protection />", "<protection/>") else "")
            x = (f'<xf numFmtId="{n}" fontId="{f}" fillId="{fl}" borderId="{b}" xfId="0" applyNumberFormat="1" '
                 f'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyProtection="1"'
                 + (f">{body}</xf>" if body else "/>"))
            self.cache[k] = self._add("cellXfs", x)
        return self.cache[k]

    def render(self):
        x = self.xml
        for tag in ("numFmts", "fonts", "fills", "borders", "cellXfs"):
            if not self.new[tag]:
                continue
            total = len(self.items[tag]) + len(self.new[tag])
            m = re.search(rf"<{tag}\b([^>]*?)(/>|>(.*?)</{tag}>)", x, re.S)
            add = "".join(self.new[tag])
            if m:
                attrs = re.sub(r'\s*count="\d+"', "", m.group(1))
                x = x[:m.start()] + f'<{tag} count="{total}"{attrs}>{m.group(3) or ""}{add}</{tag}>' + x[m.end():]
            else:
                x = re.sub(r"(<styleSheet\b[^>]*>)", lambda mm: mm.group(1) + f'<{tag} count="{total}">{add}</{tag}>', x, count=1)
        return x


def _s(el):
    t = tostring(el)
    return t.decode() if isinstance(t, bytes) else t


# ---------------------------------------------------------------- cells
def _val(v):
    """A comparable value: openpyxl's ArrayFormula objects never compare equal across workbooks."""
    if isinstance(v, ArrayFormula):
        return ("array", v.ref, v.text)
    return v


def cell_xml(ref, v, s):
    if isinstance(v, ArrayFormula):
        return f'<c r="{ref}" s="{s}"><f t="array" ref="{v.ref}">{esc((v.text or "").lstrip("="))}</f></c>'
    if v is None:
        return f'<c r="{ref}" s="{s}"/>'
    if isinstance(v, str) and v.startswith("=") and len(v) > 1:
        return f'<c r="{ref}" s="{s}"><f>{esc(v[1:])}</f></c>'
    if isinstance(v, bool):
        return f'<c r="{ref}" s="{s}" t="b"><v>{int(v)}</v></c>'
    if isinstance(v, (int, float)):
        return f'<c r="{ref}" s="{s}"><v>{v!r}</v></c>'
    if isinstance(v, (dt.datetime, dt.date)):
        return f'<c r="{ref}" s="{s}"><v>{to_excel(v)!r}</v></c>'
    if isinstance(v, str):
        if v.startswith("#") and v.rstrip("!?/0").upper() in ("#N/A", "#REF", "#VALUE", "#DIV", "#NAME", "#NUM", "#NULL"):
            return f'<c r="{ref}" s="{s}" t="e"><v>{esc(v)}</v></c>'
        return f'<c r="{ref}" s="{s}" t="inlineStr"><is><t xml:space="preserve">{esc(v)}</t></is></c>'
    raise SystemExit(f"safe_save: can't write {type(v).__name__} in {ref}")


def put_cells(xml, cells, row_attrs):
    """cells {(row, col): xml or None (remove)}; row_attrs {row: {attr: value or None}}."""
    by_row = {}
    for (r, c), x in cells.items():
        by_row.setdefault(r, {})[c] = x
    rows_touched = set(by_row) | set(row_attrs)
    sd = re.search(r"<sheetData\s*/>|<sheetData>(.*?)</sheetData>", xml, re.S)
    body = sd.group(1) or ""
    rows = {int(m.group(1)): m.group(0) for m in ROW_ELEM.finditer(body)}
    for r in rows_touched:
        row = rows.get(r, f'<row r="{r}"></row>')
        if row.endswith("/>"):
            row = row[:-2] + "></row>"
        head = row[:row.index(">") + 1]
        head = re.sub(r'\s*spans="[^"]*"', "", head)
        for a, v in row_attrs.get(r, {}).items():
            head = re.sub(rf'\s*{a}="[^"]*"', "", head)
            if v is not None:
                head = head[:-1] + f' {a}="{v}">'
        cs = {colnum(m.group(1)): m.group(0) for m in C_ELEM.finditer(row)}
        for c, x in by_row.get(r, {}).items():
            if x is None:
                cs.pop(c, None)
            else:
                cs[c] = x
        rows[r] = head + "".join(cs[c] for c in sorted(cs)) + "</row>"
    new_body = "".join(rows[r] for r in sorted(rows))
    return xml[:sd.start()] + f"<sheetData>{new_body}</sheetData>" + xml[sd.end():]


def _notes(ws):
    return {c.coordinate: c.comment.text for row in ws.iter_rows() for c in row if c.comment}


def _row_dims(ws):
    return {r: (d.ht if d.customHeight else None, bool(d.hidden), d.outlineLevel or 0)
            for r, d in ws.row_dimensions.items() if (d.customHeight and d.ht) or d.hidden or d.outlineLevel}


def _rewrite_notes(pkg, part, notes):
    """Replace (or create) the tab's notes with `notes` {ref: text}."""
    subs = dict((t, p) for t, p in _sheet_subparts(pkg, part, (RT["comments"], RT["vml"])))
    ids = [int(x) for p, d in pkg.parts.items() if p.endswith(".vml")
           for blk in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', d) for x in re.findall(rb"\d+", blk)]
    if RT["vml"] in subs:
        mine = re.search(r'<o:idmap v:ext="edit" data="([\d,\s]+)"', pkg.text(subs[RT["vml"]]))
        n = int(re.findall(r"\d+", mine.group(1))[0]) if mine else max(ids + [0]) + 1
    else:
        n = max(ids + [0]) + 1
    cx, vml = comments_parts(notes, n)
    if RT["comments"] in subs and RT["vml"] in subs:
        pkg.put(subs[RT["comments"]], cx)
        pkg.put(subs[RT["vml"]], vml)
        return
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
    pkg.put(f"xl/comments{cn}.xml", cx)
    pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
    rid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
    pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    xml = pkg.text(part)
    el = f'<legacyDrawing r:id="{rid}"/>'
    m = re.search(r"<(legacyDrawingHF|picture|oleObjects|controls|webPublishItems|tableParts|extLst)\b", xml)
    xml = xml[:m.start()] + el + xml[m.start():] if m else xml.replace("</worksheet>", el + "</worksheet>")
    if 'xmlns:r="' not in xml[:xml.index(">")]:
        xml = xml.replace("<worksheet ", '<worksheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    pkg.put(part, xml)


# ---------------------------------------------------------------- the save
def _snapshot(path):
    wb = openpyxl.load_workbook(path)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = {
            "cells": {(c.row, c.column): (_val(c.value), style_key(c)) for row in ws.iter_rows() for c in row
                      if c.value is not None or c.has_style},
            "notes": _notes(ws), "merges": sorted(str(m) for m in ws.merged_cells.ranges), "rows": _row_dims(ws),
            "freeze": ws.freeze_panes,
            "cols": {k: (d.width if d.customWidth else None, bool(d.hidden)) for k, d in ws.column_dimensions.items()},
        }
    return out, wb.calculation.fullCalcOnLoad


def _default_key():
    wb = openpyxl.Workbook()
    return style_key(wb.active["A1"])


def safe_save(wb, src, out):
    """Save openpyxl workbook `wb` (loaded from `src`) to `out` without openpyxl rewriting the file (see module doc)."""
    tmp = tempfile.mkdtemp(prefix="safe_save_")
    try:
        po = os.path.join(tmp, "openpyxl.xlsx")
        wb.save(po)
        want, full_calc = _snapshot(po)
        pkg = Package(src)
        for title, fn in getattr(wb, "_safe_moves", []):
            remap_rows(pkg, title, fn)
        pr = os.path.join(tmp, "moved.xlsx")
        pkg.save(pr)
        pkg = Package(pr)
        have, _ = _snapshot(pr)
        if set(have) != set(want):
            raise SystemExit(f"safe_save: the tabs differ ({sorted(set(have) ^ set(want))}); adding or removing tabs is "
                             "not supported. Nothing was written.")
        src_wb = openpyxl.load_workbook(po)
        st = RawStyles(pkg.text("xl/styles.xml"))
        dflt = _default_key()
        parts = {name: part for name, _, _, part in pkg.sheets()}
        for name, w in want.items():
            h = have[name]
            ws = src_wb[name]
            cells = {}
            for rc in set(w["cells"]) | set(h["cells"]):
                a, b = w["cells"].get(rc), h["cells"].get(rc)
                if a == b:
                    continue
                if a is None or (a[0] is None and a[1] == dflt):
                    cells[rc] = None
                else:
                    c = ws.cell(*rc)
                    cells[rc] = cell_xml(f"{colname(rc[1])}{rc[0]}", c.value, st.xf_for(c))
            row_attrs = {}
            for r in set(w["rows"]) | set(h["rows"]):
                if w["rows"].get(r) != h["rows"].get(r):
                    ht, hidden, lvl = w["rows"].get(r, (None, False, 0))
                    row_attrs[r] = {"ht": ht, "customHeight": "1" if ht else None, "hidden": "1" if hidden else None,
                                    "outlineLevel": lvl or None}
            if cells or row_attrs:
                pkg.put(parts[name], put_cells(unshare_all(pkg.text(parts[name])), cells, row_attrs))
            if w["notes"] != h["notes"]:
                _rewrite_notes(pkg, parts[name], w["notes"])
        pkg.put("xl/styles.xml", st.render())
        if full_calc:
            x = pkg.text("xl/workbook.xml")
            x = re.sub(r"<calcPr\b([^>]*?)\s*/>", lambda m: "<calcPr" + re.sub(r'\s*fullCalcOnLoad="\w+"', "", m.group(1))
                       + ' fullCalcOnLoad="1"/>', x) if "<calcPr" in x else x.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')
            pkg.put("xl/workbook.xml", x)
        pkg.finish()
        final = os.path.join(tmp, "final.xlsx")
        pkg.save(final)
        got, _ = _snapshot(final)
        diffs = [f"{name}: {what}" for name in want for what in ("cells", "notes", "merges", "rows", "freeze", "cols")
                 if got[name][what] != want[name][what]]
        if diffs:
            first = []
            for name in want:
                gw, gg = want[name]["cells"], got[name]["cells"]
                first += [f"{name}!{colname(c)}{r}" for (r, c) in sorted(set(gw) | set(gg)) if gw.get((r, c)) != gg.get((r, c))][:5]
            raise SystemExit("safe_save: the safe copy does not match openpyxl's result (" + "; ".join(diffs) + "; first "
                             f"cells: {', '.join(first[:10])}). Nothing was written.")
        shutil.copyfile(final, out + ".safe_save.tmp")
        os.replace(out + ".safe_save.tmp", out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
