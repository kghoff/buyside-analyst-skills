# Copied from skills/model-forecast/scripts/xledit.py (keep in sync).
"""(Copied from research-filings, Nov 2026.) Edits inside tabs that already exist in the user's model, on the raw XML (xlsx.py says why not openpyxl).

- insert_rows: insert blank rows into one tab and shift every reference to the rows below, on every tab, in
  charts and in defined names, the way Excel's Insert Row does. Shared formulas that touch the tab are first
  written out cell by cell, because a shared formula's children are offsets from its first cell and an insert
  can change those offsets.
- set_cells: write cells into an existing tab; a cell that already holds something is never overwritten
  (the user's work), it is reported instead.
- add_cf / add_merges: conditional formatting and merged cells on an existing tab.
- drawing_part / put_anchors: shapes on a tab's drawing. Claude's shapes are named 'P1 ...' so a rerun removes
  and redraws exactly those and nothing of the user's."""
import re

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.formula.translate import Translator

from xlsx import CT, RT, colname, colnum, esc, relpath_of, resolve, unesc

CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
ROWONLY = re.compile(r"^(\$?)(\d+)$")
OWN = "P1 "            # name prefix of Claude's shapes


# ---------------------------------------------------------------- reference shifting
def _shift_part(p, at, n):
    m = CELL.match(p)
    if m:
        r = int(m.group(4))
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{r + n if r >= at else r}"
    m = ROWONLY.match(p)
    if m:
        r = int(m.group(2))
        return f"{m.group(1)}{r + n if r >= at else r}"
    return p                        # whole column, defined name, error...


def _sheet_of(prefix):
    s = prefix[:-1]                 # drop '!'
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1].replace("''", "'")
    return s


def shift_ref(text, local_sheet, target, at, n):
    """One range operand: 'MOD!H104', "'Px Data'!$A5:$B9", 'A:A', '5:7' ..."""
    if "!" in text:
        i = text.rindex("!")
        prefix, refs = text[:i + 1], text[i + 1:]
        if _sheet_of(prefix) != target:
            return text
    else:
        if local_sheet != target:
            return text
        prefix, refs = "", text
    return prefix + ":".join(_shift_part(p, at, n) for p in refs.split(":"))


def shift_formula(formula, local_sheet, target, at, n):
    """Shift rows >= at by n in every reference to `target` (formula text without or with a leading '=')."""
    eq = formula.startswith("=")
    tok = Tokenizer(formula if eq else "=" + formula)
    changed = False
    for t in tok.items:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            v = shift_ref(t.value, local_sheet, target, at, n)
            changed |= v != t.value
            t.value = v
    if not changed:
        return formula
    out = tok.render()
    return out if eq else out[1:]


def _refers_to(formula, local_sheet, target):
    tok = Tokenizer(formula if formula.startswith("=") else "=" + formula)
    for t in tok.items:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            if "!" in t.value:
                if _sheet_of(t.value[:t.value.rindex("!") + 1]) == target:
                    return True
            elif local_sheet == target:
                return True
    return False


# ---------------------------------------------------------------- shared formulas
C_ELEM = re.compile(r'<c r="([A-Z]+\d+)"[^>]*?(?:/>|>.*?</c>)', re.S)
F_SHARED = re.compile(r'<f t="shared"([^>]*?)(?:/>|>(.*?)</f>)', re.S)


def unshare(xml, local_sheet, target):
    """Write out shared formulas whose first cell refers to `target` (or all of them on `target` itself)."""
    masters = {}
    for m in C_ELEM.finditer(xml):
        f = F_SHARED.search(m.group(0))
        if f and f.group(2) is not None:
            si = re.search(r'si="(\d+)"', f.group(1)).group(1)
            masters[si] = (m.group(1), unesc(f.group(2)))
    todo = {si for si, (_, fx) in masters.items() if local_sheet == target or _refers_to(fx, local_sheet, target)}
    if not todo:
        return xml

    def cell(m):
        c = m.group(0)
        f = F_SHARED.search(c)
        if not f:
            return c
        si = re.search(r'si="(\d+)"', f.group(1)).group(1)
        if si not in todo:
            return c
        origin, fx = masters[si]
        text = fx if m.group(1) == origin else Translator("=" + fx, origin=origin).translate_formula(m.group(1))[1:]
        return c[:f.start()] + f"<f>{esc(text)}</f>" + c[f.end():]
    return C_ELEM.sub(cell, xml)


# ---------------------------------------------------------------- insert rows
def _shift_formulas_in(xml, local_sheet, target, at, n):
    def f(m):
        attrs, body = m.group(1), m.group(2)
        new = esc(shift_formula(unesc(body), local_sheet, target, at, n))
        if local_sheet == target and "ref=" in attrs:      # array / shared range on the target itself
            attrs = re.sub(r'ref="([^"]+)"', lambda r: f'ref="{shift_ref(r.group(1), target, target, at, n)}"', attrs)
        return f"<f{attrs}>{new}</f>"
    return re.sub(r"<f\b([^>]*?)(?<!/)>(.*?)</f>", f, xml, flags=re.S)     # never a self-closing <f .../>


def _sheet_vml_and_comments(pkg, part):
    out = []
    for _, (typ, tgt) in pkg.rels(relpath_of(part)).items():
        if typ in (RT["comments"], RT["vml"]):
            out.append((typ, resolve(part, tgt)))
    return out


def insert_rows(pkg, target, at, n):
    """Insert n blank rows above row `at` on tab `target`; shift every reference (all tabs, charts, names)."""
    sheets = pkg.sheets()
    for name, _, _, part in sheets:
        xml = unshare(pkg.text(part), name, target)
        xml = _shift_formulas_in(xml, name, target, at, n)
        if name == target:
            xml = re.sub(r'(<row r=")(\d+)"', lambda m: f'{m.group(1)}{int(m.group(2)) + n if int(m.group(2)) >= at else m.group(2)}"', xml)
            xml = re.sub(r'(<c r=")([A-Z]+\d+)"', lambda m: f'{m.group(1)}{shift_ref(m.group(2), target, target, at, n)}"', xml)
            xml = re.sub(r'(<dimension ref=")([^"]+)"', lambda m: f'{m.group(1)}{shift_ref(m.group(2), target, target, at, n)}"', xml)
            xml = re.sub(r'(sqref=")([^"]+)"', lambda m: m.group(1) + " ".join(shift_ref(s, target, target, at, n)
                                                                          for s in m.group(2).split()) + '"', xml)
            xml = re.sub(r'(<mergeCell ref=")([^"]+)"', lambda m: f'{m.group(1)}{shift_ref(m.group(2), target, target, at, n)}"', xml)
            for typ, sub in _sheet_vml_and_comments(pkg, part):
                t = pkg.text(sub)
                if typ == RT["comments"]:
                    t = re.sub(r'(<comment ref=")([^"]+)"', lambda m: f'{m.group(1)}{shift_ref(m.group(2), target, target, at, n)}"', t)
                else:       # VML rows are 0-based
                    t = re.sub(r"<x:Row>(\d+)</x:Row>", lambda m: f"<x:Row>{int(m.group(1)) + n if int(m.group(1)) >= at - 1 else m.group(1)}</x:Row>", t)

                    def anc(m):
                        v = [x.strip() for x in m.group(1).split(",")]
                        for k in (2, 6):
                            if int(v[k]) >= at - 1:
                                v[k] = str(int(v[k]) + n)
                        return "<x:Anchor>" + ", ".join(v) + "</x:Anchor>"
                    t = re.sub(r"<x:Anchor>([^<]+)</x:Anchor>", anc, t)
                pkg.put(sub, t)
        pkg.put(part, xml)
    for p in [p for p in pkg.parts if p.startswith("xl/charts/chart") and p.endswith(".xml")]:
        t = pkg.text(p)
        t2 = re.sub(r"<(c:)?f>(.*?)</(?:c:)?f>",       # Excel writes c:f; openpyxl a default namespace
                    lambda m: f"<{m.group(1) or ''}f>{esc(shift_formula(unesc(m.group(2)), None, target, at, n))}</{m.group(1) or ''}f>", t)
        if t2 != t:
            pkg.put(p, t2)
    wb = pkg.text("xl/workbook.xml")
    wb = re.sub(r"(<definedName\b[^>]*>)(.*?)(</definedName>)",
                lambda m: m.group(1) + esc(shift_formula(unesc(m.group(2)), None, target, at, n)) + m.group(3), wb, flags=re.S)
    pkg.put("xl/workbook.xml", wb)


# ---------------------------------------------------------------- cells on an existing tab
def _has_content(c):
    return bool(re.search(r"<(v|f|is)\b", c))


def _cell_xml(ref, kind, val, st):
    if kind == "f":
        return f'<c r="{ref}" s="{st}"><f>{esc(val)}</f></c>'
    if kind == "s":
        return f'<c r="{ref}" s="{st}" t="inlineStr"><is><t xml:space="preserve">{esc(val)}</t></is></c>'
    if kind == "n":
        return f'<c r="{ref}" s="{st}"><v>{val!r}</v></c>'
    return f'<c r="{ref}" s="{st}"/>'


def set_cells(xml, cells, heights=None, replace=False):
    """cells: {'AB9': (kind, value, style)}. Returns (xml, refs skipped because the cell already holds something)."""
    skipped = []
    by_row = {}
    for ref, v in cells.items():
        m = re.match(r"([A-Z]+)(\d+)$", ref)
        by_row.setdefault(int(m.group(2)), []).append((colnum(m.group(1)), ref, v))
    heights = heights or {}
    sd = re.search(r"<sheetData\s*/>|<sheetData>(.*?)</sheetData>", xml, re.S)
    rows = {int(m.group(1)): m.group(0) for m in re.finditer(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', sd.group(1) or "", re.S)}
    for r, items in by_row.items():
        row = rows.get(r, f'<row r="{r}"></row>')
        if row.endswith("/>"):
            row = row[:-2] + "></row>"
        head = row[:row.index(">") + 1]
        if r in heights:
            head = re.sub(r'\s*(ht|customHeight)="[^"]*"', "", head)[:-1] + f' ht="{heights[r]}" customHeight="1">'
        cs = {colnum(re.match(r'<c r="([A-Z]+)', c.group(0)).group(1)): c.group(0)
              for c in re.finditer(r'<c r="[A-Z]+\d+"[^>]*?(?:/>|>.*?</c>)', row, re.S)}
        for col, ref, (kind, val, st) in items:
            if col in cs and _has_content(cs[col]) and not replace:
                skipped.append(ref)
                continue
            cs[col] = _cell_xml(ref, kind, val, st)
        head = re.sub(r'\s*spans="[^"]*"', "", head)
        rows[r] = head + "".join(cs[c] for c in sorted(cs)) + "</row>"
    body = "".join(rows[r] for r in sorted(rows))
    xml = xml[:sd.start()] + f"<sheetData>{body}</sheetData>" + xml[sd.end():]
    last = max(rows) if rows else 1
    xml = re.sub(r'<dimension ref="([A-Z]+)\d+:([A-Z]+)(\d+)"/>',
                 lambda m: f'<dimension ref="{m.group(1)}1:{m.group(2)}{max(int(m.group(3)), last)}"/>'
                 if m.group(1) else m.group(0), xml)
    return xml, skipped


AFTER_CF = ("dataValidations", "hyperlinks", "printOptions", "pageMargins", "pageSetup", "headerFooter", "rowBreaks",
            "colBreaks", "customProperties", "cellWatches", "ignoredErrors", "smartTags", "drawing", "legacyDrawing",
            "legacyDrawingHF", "picture", "oleObjects", "controls", "webPublishItems", "tableParts", "extLst")


def _insert_before_first(xml, tags, block):
    pos = [m.start() for t in tags for m in [re.search(rf"<{t}\b", xml)] if m]
    i = min(pos) if pos else xml.rindex("</worksheet>")
    return xml[:i] + block + xml[i:]


def add_cf(xml, rules):
    """rules: [(sqref, formula, dxf_id)] as expression rules, after any existing ones."""
    prio = max([int(p) for p in re.findall(r'<cfRule\b[^>]*priority="(\d+)"', xml)] + [0])
    block = "".join(f'<conditionalFormatting sqref="{rng}"><cfRule type="expression" dxfId="{dxf}" priority="{prio + k + 1}">'
                    f"<formula>{esc(fm)}</formula></cfRule></conditionalFormatting>" for k, (rng, fm, dxf) in enumerate(rules))
    return _insert_before_first(xml, AFTER_CF, block)


def add_merges(xml, refs):
    if not refs:
        return xml
    if "<mergeCells" in xml:
        have = re.findall(r'<mergeCell ref="([^"]+)"', xml)
        allm = have + [r for r in refs if r not in have]
        return re.sub(r"<mergeCells\b.*?</mergeCells>", f'<mergeCells count="{len(allm)}">'
                      + "".join(f'<mergeCell ref="{r}"/>' for r in allm) + "</mergeCells>", xml, flags=re.S)
    return xml.replace("</sheetData>", f'</sheetData><mergeCells count="{len(refs)}">'
                       + "".join(f'<mergeCell ref="{r}"/>' for r in refs) + "</mergeCells>", 1)


def merged(xml):
    return re.findall(r'<mergeCell ref="([^"]+)"', xml)


# ---------------------------------------------------------------- drawings
def drawing_part(pkg, sheet_part):
    for _, (typ, tgt) in pkg.rels(relpath_of(sheet_part)).items():
        if typ == RT["drawing"]:
            return resolve(sheet_part, tgt)
    return None


ANCHOR = re.compile(r"<(xdr:)?(twoCellAnchor|oneCellAnchor|absoluteAnchor)\b.*?</(?:xdr:)?\2>", re.S)
NS_XDR = 'xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"'
NS_A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


def put_anchors(pkg, dpart, anchors):
    """Remove Claude's previous shapes ('P1 ...') from a drawing and append `anchors` (xml strings)."""
    x = pkg.text(dpart)
    x = ANCHOR.sub(lambda m: "" if re.search(rf'<(?:xdr:)?cNvPr\b[^>]*name="{OWN}', m.group(0)) else m.group(0), x)
    root = re.search(r"<(?:xdr:)?wsDr\b[^>]*>", x).group(0)
    for ns in (NS_XDR, NS_A):          # openpyxl writes the drawing in a default namespace; our anchors use xdr: / a:
        if ns.split("=")[0] not in root:
            x = x.replace(root, root[:-1] + " " + ns + ">", 1)
            root = root[:-1] + " " + ns + ">"
    ids = [int(i) for i in re.findall(r'<(?:xdr:)?cNvPr\b[^>]*\bid="(\d+)"', x)]
    nxt = max(ids + [1]) + 1
    out = []
    for a in anchors:
        out.append(a.replace("{ID}", str(nxt)))
        nxt += 1
    end = x.rindex("</")
    pkg.put(dpart, x[:end] + "".join(out) + x[end:])


def ensure_drawing(pkg, sheet_part):
    d = drawing_part(pkg, sheet_part)
    if d:
        return d
    dn = pkg.free("xl/drawings/drawing{}.xml")
    d = f"xl/drawings/drawing{dn}.xml"
    pkg.put(d, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
               'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"></xdr:wsDr>')
    pkg.content_override(d, CT["drawing"])
    rid = pkg.attach(sheet_part, "drawing", d)
    xml = pkg.text(sheet_part)
    xml = _insert_before_first(xml, AFTER_CF[AFTER_CF.index("drawing"):], f'<drawing r:id="{rid}"/>')
    pkg.put(sheet_part, xml)
    return d


def _pos(col, colOff, row, rowOff):
    return (f"<xdr:col>{col}</xdr:col><xdr:colOff>{colOff}</xdr:colOff>"
            f"<xdr:row>{row}</xdr:row><xdr:rowOff>{rowOff}</xdr:rowOff>")


def textbox(name, frm, to, text, sz=1100, bold=False, color="000000"):
    """frm / to = (col, colOff EMU, row, rowOff EMU). Styled like the user's own notes on the Idio Chart: white fill,
    thin grey outline, centered 11 pt text."""
    paras = "".join(f'<a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="en-US" sz="{sz}" b="{1 if bold else 0}"><a:solidFill>'
                    f'<a:srgbClr val="{color}"/></a:solidFill></a:rPr><a:t>{esc(line)}</a:t></a:r></a:p>' for line in text.split("\n"))
    return (f'<xdr:twoCellAnchor>{"<xdr:from>" + _pos(*frm) + "</xdr:from>"}{"<xdr:to>" + _pos(*to) + "</xdr:to>"}'
            f'<xdr:sp macro="" textlink=""><xdr:nvSpPr><xdr:cNvPr id="{{ID}}" name="{OWN}{esc(name)}"/>'
            '<xdr:cNvSpPr txBox="1"/></xdr:nvSpPr><xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:schemeClr val="lt1"/></a:solidFill>'
            '<a:ln w="9525" cmpd="sng"><a:solidFill><a:schemeClr val="lt1"><a:shade val="50000"/></a:schemeClr></a:solidFill>'
            '</a:ln></xdr:spPr>'
            '<xdr:txBody><a:bodyPr vertOverflow="clip" horzOverflow="clip" wrap="square" lIns="36000" tIns="18000" '
            f'rIns="36000" bIns="18000" rtlCol="0" anchor="t"/><a:lstStyle/>{paras}</xdr:txBody></xdr:sp>'
            "<xdr:clientData/></xdr:twoCellAnchor>")


def arrow(name, frm, to, color="000000"):
    """Straight arrow from `frm` to `to` (the head at `to`). Flips are set when the line runs up or left."""
    flip = ""
    (c1, o1, r1, q1), (c2, o2, r2, q2) = frm, to
    a, b = (c1, o1, r1, q1), (c2, o2, r2, q2)
    fh, fv = (c2, o2) < (c1, o1), (r2, q2) < (r1, q1)
    lo = (min((c1, o1), (c2, o2)), min((r1, q1), (r2, q2)))
    hi = (max((c1, o1), (c2, o2)), max((r1, q1), (r2, q2)))
    if fh:
        flip += ' flipH="1"'
    if fv:
        flip += ' flipV="1"'
    return (f'<xdr:twoCellAnchor><xdr:from>{_pos(lo[0][0], lo[0][1], lo[1][0], lo[1][1])}</xdr:from>'
            f'<xdr:to>{_pos(hi[0][0], hi[0][1], hi[1][0], hi[1][1])}</xdr:to>'
            f'<xdr:cxnSp macro=""><xdr:nvCxnSpPr><xdr:cNvPr id="{{ID}}" name="{OWN}{esc(name)}"/><xdr:cNvCxnSpPr/>'
            f'</xdr:nvCxnSpPr><xdr:spPr><a:xfrm{flip}><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></a:xfrm>'
            '<a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom><a:ln w="9525">'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:tailEnd type="triangle"/></a:ln></xdr:spPr>'
            "</xdr:cxnSp><xdr:clientData/></xdr:twoCellAnchor>")
