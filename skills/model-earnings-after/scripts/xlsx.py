"""(Copied from model-earnings-before, Nov 2026; keep in sync. Origin: model-multiples. Adds merged cells.) Raw-XML workbook editing: add / remove whole tabs (with their drawings, charts and comments) without loading the
workbook in openpyxl, which would drop the user's text boxes, shapes, images and equations and re-serialize their charts.

Every other part of the package is copied byte for byte. Only workbook.xml, its rels, [Content_Types].xml and
styles.xml (new styles appended at the end, existing indices untouched) change, plus the new tabs' own parts."""
import re
import zipfile

from xml.sax.saxutils import escape as _esc

NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = {
    "sheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
    "drawing": "application/vnd.openxmlformats-officedocument.drawing+xml",
    "chart": "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
    "comments": "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml",
}
RT = {k: f"{NS_REL}/{v}" for k, v in {"sheet": "worksheet", "drawing": "drawing", "chart": "chart",
                                       "comments": "comments", "vml": "vmlDrawing"}.items()}


def esc(t):
    return _esc(str(t), {'"': "&quot;"})


def colnum(L):
    n = 0
    for ch in L:
        n = n * 26 + ord(ch) - 64
    return n


def colname(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Package:
    def __init__(self, path):
        z = zipfile.ZipFile(path)
        self.infos = z.infolist()
        self.parts = {i.filename: z.read(i.filename) for i in self.infos}
        z.close()

    def text(self, name):
        return self.parts[name].decode("utf-8")

    def put(self, name, data):
        self.parts[name] = data.encode("utf-8") if isinstance(data, str) else data

    def save(self, path):
        names = [i.filename for i in self.infos if i.filename in self.parts]
        names += [n for n in self.parts if n not in names]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zo:
            info = {i.filename: i for i in self.infos}
            for n in names:
                if n in info:
                    zo.writestr(info[n], self.parts[n])
                else:
                    zo.writestr(n, self.parts[n])

    # ---- sheets ----
    def sheets(self):
        """[(name, sheetId, rId, part path)] in tab order."""
        wb = self.text("xl/workbook.xml")
        rels = self.rels("xl/_rels/workbook.xml.rels")
        out = []
        for m in re.finditer(r"<sheet\b[^>]*/>", wb):
            tag = m.group(0)
            name = re.search(r'name="([^"]*)"', tag).group(1)
            sid = re.search(r'sheetId="(\d+)"', tag).group(1)
            rid = re.search(r'r:id="([^"]+)"', tag).group(1)
            out.append((unesc(name), sid, rid, resolve("xl/workbook.xml", rels[rid][1])))
        return out

    def rels(self, relpath):
        """{Id: (Type, Target)}"""
        if relpath not in self.parts:
            return {}
        out = {}
        for m in re.finditer(r"<Relationship\b[^>]*/>", self.text(relpath)):
            t = m.group(0)
            out[re.search(r'Id="([^"]+)"', t).group(1)] = (re.search(r'Type="([^"]+)"', t).group(1),
                                                         re.search(r'Target="([^"]+)"', t).group(1))
        return out

    def write_rels(self, relpath, rels):
        body = "".join(f'<Relationship Id="{k}" Type="{t}" Target="{esc(g)}"/>' for k, (t, g) in rels.items())
        self.put(relpath, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                          f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>')

    def free(self, pattern):
        """next free number for a part pattern like 'xl/charts/chart{}.xml'"""
        k = 1
        while pattern.format(k) in self.parts:
            k += 1
        return k

    def content_override(self, part, ctype):
        ct = self.text("[Content_Types].xml")
        if f'PartName="/{part}"' not in ct:
            ct = ct.replace("</Types>", f'<Override PartName="/{part}" ContentType="{ctype}"/></Types>')
        self.put("[Content_Types].xml", ct)

    def content_default(self, ext, ctype):
        ct = self.text("[Content_Types].xml")
        if f'Extension="{ext}"' not in ct:
            ct = re.sub(r"(<Types[^>]*>)", rf'\1<Default Extension="{ext}" ContentType="{ctype}"/>', ct, count=1)
        self.put("[Content_Types].xml", ct)

    def drop_part(self, part):
        self.parts.pop(part, None)
        self.parts.pop(relpath_of(part), None)
        ct = self.text("[Content_Types].xml")
        self.put("[Content_Types].xml", re.sub(rf'<Override PartName="/{re.escape(part)}"[^>]*/>', "", ct))

    def remove_sheet(self, name):
        """Remove a tab and everything that hangs off it (drawing, charts, comments, vml)."""
        sh = {s[0]: s for s in self.sheets()}[name]
        _, sid, rid, part = sh
        idx = [s[0] for s in self.sheets()].index(name)
        for _, (typ, tgt) in self.rels(relpath_of(part)).items():
            if "TargetMode" in tgt:
                continue
            sub = resolve(part, tgt)
            if typ == RT["drawing"]:
                for _, (t2, g2) in self.rels(relpath_of(sub)).items():
                    if t2 == RT["chart"]:
                        ch = resolve(sub, g2)
                        for _, (t3, g3) in self.rels(relpath_of(ch)).items():
                            self.drop_part(resolve(ch, g3))
                        self.drop_part(ch)
            self.drop_part(sub)
        self.drop_part(part)
        wb = self.text("xl/workbook.xml")
        wb = re.sub(rf'<sheet\b[^>]*r:id="{rid}"[^>]*/>', "", wb)

        def fix_dn(m):
            k = int(m.group(2))
            if k == idx:
                return ""
            return m.group(0).replace(f'localSheetId="{k}"', f'localSheetId="{k - 1}"') if k > idx else m.group(0)
        wb = re.sub(r'(<definedName\b[^>]*localSheetId="(\d+)"[^>]*>.*?</definedName>)', fix_dn, wb, flags=re.S)
        wb = re.sub(r"<definedNames>\s*</definedNames>", "", wb)
        n = len(self.sheets()) - 1
        wb = re.sub(r'activeTab="(\d+)"', lambda m: f'activeTab="{min(int(m.group(1)), n - 1)}"', wb)
        self.put("xl/workbook.xml", wb)
        rels = self.rels("xl/_rels/workbook.xml.rels")
        rels.pop(rid, None)
        self.write_rels("xl/_rels/workbook.xml.rels", rels)

    def add_sheet(self, name, xml):
        """Append a tab at the end. Returns its part path."""
        k = self.free("xl/worksheets/sheet{}.xml")
        part = f"xl/worksheets/sheet{k}.xml"
        self.put(part, xml)
        self.content_override(part, CT["sheet"])
        rels = self.rels("xl/_rels/workbook.xml.rels")
        rid = new_rid(rels)
        rels[rid] = (RT["sheet"], f"worksheets/sheet{k}.xml")
        self.write_rels("xl/_rels/workbook.xml.rels", rels)
        wb = self.text("xl/workbook.xml")
        root = re.search(r"<workbook\b[^>]*>", wb).group(0)
        if "xmlns:r=" not in root:          # openpyxl declares r: on each <sheet>, Excel on the root; our r:id needs it
            wb = wb.replace(root, root[:-1] + f' xmlns:r="{NS_REL}">', 1)
        sid = max([int(s[1]) for s in self.sheets()] + [0]) + 1
        wb = wb.replace("</sheets>", f'<sheet name="{esc(name)}" sheetId="{sid}" r:id="{rid}"/></sheets>')
        self.put("xl/workbook.xml", wb)
        return part

    def attach(self, part, kind, target_part, ctype=None):
        """Relationship from `part` to `target_part`; returns the rId."""
        rp = relpath_of(part)
        rels = self.rels(rp)
        rid = new_rid(rels)
        rels[rid] = (RT[kind], relative(part, target_part))
        self.write_rels(rp, rels)
        if ctype:
            self.content_override(target_part, ctype)
        return rid

    def finish(self):
        """Force a full recalculation on open; drop calcChain (Excel rebuilds it)."""
        wb = self.text("xl/workbook.xml")
        if "<calcPr" in wb:
            wb = re.sub(r"<calcPr\b([^>]*?)/>", lambda m: "<calcPr" + re.sub(r'\s*fullCalcOnLoad="\w+"', "", m.group(1))
                        + ' fullCalcOnLoad="1"/>', wb, count=1)
        else:
            wb = re.sub(r"(</sheets>(?:\s*<functionGroups[^>]*/>)?(?:\s*<externalReferences>.*?</externalReferences>)?"
                        r"(?:\s*<definedNames>.*?</definedNames>)?)", r'\1<calcPr fullCalcOnLoad="1"/>', wb, count=1, flags=re.S)
        self.put("xl/workbook.xml", wb)
        if "xl/calcChain.xml" in self.parts:
            self.drop_part("xl/calcChain.xml")
            rels = {k: v for k, v in self.rels("xl/_rels/workbook.xml.rels").items() if not v[1].endswith("calcChain.xml")}
            self.write_rels("xl/_rels/workbook.xml.rels", rels)


def unesc(t):
    return t.replace("&quot;", '"').replace("&apos;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def new_rid(rels):
    k = 1
    while f"rId{k}" in rels:
        k += 1
    return f"rId{k}"


def relpath_of(part):
    d, f = part.rsplit("/", 1)
    return f"{d}/_rels/{f}.rels"


def resolve(base, target):
    if target.startswith("/"):
        return target[1:]
    parts = base.split("/")[:-1]
    for seg in target.split("/"):
        if seg == "..":
            parts.pop()
        elif seg != ".":
            parts.append(seg)
    return "/".join(parts)


def relative(base, target):
    b, t = base.split("/")[:-1], target.split("/")
    i = 0
    while i < min(len(b), len(t) - 1) and b[i] == t[i]:
        i += 1
    return "/".join([".."] * (len(b) - i) + t[i:])


# ---------------------------------------------------------------- styles
class Styles:
    """Appends fonts / fills / numFmts / cellXfs / dxfs to styles.xml and hands back their indices."""
    BUILTIN = {"General": 0, "0": 1, "0.00": 2, "#,##0": 3, "#,##0.00": 4, "0%": 9, "0.00%": 10}

    def __init__(self, xml):
        self.xml = xml
        self.fmt = {}
        for m in re.finditer(r'<numFmt numFmtId="(\d+)" formatCode="([^"]*)"/>', xml):
            self.fmt[unesc(m.group(2))] = int(m.group(1))
        self.next_fmt = max([163] + list(self.fmt.values())) + 1
        self.new = {"numFmts": [], "fonts": [], "fills": [], "cellXfs": [], "dxfs": []}
        self.count = {k: self._count(k) for k in self.new}
        self.cache = {}

    def _count(self, tag):
        m = re.search(rf"<{tag}\b[^>]*?(?:/>|>(.*?)</{tag}>)", self.xml, re.S)
        if not m or not m.group(1):
            return 0
        child = {"numFmts": "numFmt", "fonts": "font", "fills": "fill", "cellXfs": "xf", "dxfs": "dxf"}[tag]
        return len(re.findall(rf"<{child}\b", m.group(1)))

    def _add(self, tag, xml):
        key = (tag, xml)
        if key not in self.cache:
            self.cache[key] = self.count[tag] + len(self.new[tag])
            self.new[tag].append(xml)
        return self.cache[key]

    def numfmt(self, code):
        if code in self.BUILTIN:
            return self.BUILTIN[code]
        if code not in self.fmt:
            self.fmt[code] = self.next_fmt
            self.new["numFmts"].append(f'<numFmt numFmtId="{self.next_fmt}" formatCode="{esc(code)}"/>')
            self.next_fmt += 1
        return self.fmt[code]

    def font(self, color="FF000000", sz=12, b=False, i=False):
        return self._add("fonts", f'<font>{"<b/>" if b else ""}{"<i/>" if i else ""}<sz val="{sz}"/><color rgb="{color}"/>'
                                  '<name val="Aptos Narrow"/><family val="2"/></font>')

    def fill(self, rgb):
        return self._add("fills", f'<fill><patternFill patternType="solid"><fgColor rgb="{rgb}"/><bgColor indexed="64"/>'
                                  "</patternFill></fill>")

    def xf(self, color="FF000000", fmt="General", sz=12, b=False, i=False, fill=None, align=None):
        f = self.font(color, sz, b, i)
        fl = self.fill(fill) if fill else 0
        n = self.numfmt(fmt)
        al = f'<alignment horizontal="{align}" vertical="center" wrapText="1"/>' if align else ""
        return self._add("cellXfs", f'<xf numFmtId="{n}" fontId="{f}" fillId="{fl}" borderId="0" xfId="0" applyNumberFormat="1" '
                                    f'applyFont="1"{" applyFill=" + chr(34) + "1" + chr(34) if fill else ""}'
                                    f'{" applyAlignment=" + chr(34) + "1" + chr(34) + ">" + al + "</xf>" if al else "/>"}')

    def dxf_font(self, rgb):
        return self._add("dxfs", f'<dxf><font><color rgb="{rgb}"/></font></dxf>')

    def render(self):
        x = self.xml
        for tag in ("numFmts", "fonts", "fills", "cellXfs", "dxfs"):
            if not self.new[tag]:
                continue
            add = "".join(self.new[tag])
            total = self.count[tag] + len(self.new[tag])
            m = re.search(rf"<{tag}\b([^>]*?)(/>|>(.*?)</{tag}>)", x, re.S)
            if m:
                attrs = re.sub(r'\s*count="\d+"', "", m.group(1))
                inner = m.group(3) or ""
                x = x[:m.start()] + f'<{tag} count="{total}"{attrs}>{inner}{add}</{tag}>' + x[m.end():]
            else:
                # numFmts goes first inside styleSheet; dxfs after cellStyles
                anchor = {"numFmts": r"(<styleSheet\b[^>]*>)", "dxfs": r"(</cellStyles>|<cellStyles\b[^>]*/>)"}[tag]
                x = re.sub(anchor, lambda mm: (mm.group(1) + f'<{tag} count="{total}">{add}</{tag}>'), x, count=1)
        return x


# ---------------------------------------------------------------- sheet writer
class Sheet:
    """Collects cells and writes a worksheet part. Cells: ('f', formula) | ('fa', array formula) | ('n', number)
    | ('s', text) | ('d', excel serial date as number)."""

    def __init__(self):
        self.cells = {}
        self.widths = {}
        self.heights = {}
        self.cf = []          # (range, formula, dxf)
        self.merges = []   # "A1:I2"
        self.comments = {}    # ref -> text
        self.freeze = None
        self.zoom = None

    def set(self, ref, kind, value, style):
        m = re.match(r"([A-Z]+)(\d+)$", ref)
        self.cells[(int(m.group(2)), colnum(m.group(1)))] = (kind, value, style)

    def xml(self, drawing_rid=None, legacy_rid=None):
        rows = {}
        for (r, c), v in self.cells.items():
            rows.setdefault(r, []).append((c, v))
        maxr = max(rows) if rows else 1
        maxc = max(c for (_, c) in self.cells) if self.cells else 1
        out = []
        for r in sorted(rows):
            ht = f' ht="{self.heights[r]}" customHeight="1"' if r in self.heights else ""
            cells = []
            for c, (kind, val, st) in sorted(rows[r]):
                ref = f"{colname(c)}{r}"
                if kind == "f":
                    cells.append(f'<c r="{ref}" s="{st}"><f>{esc(val)}</f></c>')
                elif kind == "fa":
                    cells.append(f'<c r="{ref}" s="{st}"><f t="array" ref="{ref}">{esc(val)}</f></c>')
                elif kind == "s":
                    cells.append(f'<c r="{ref}" s="{st}" t="inlineStr"><is><t xml:space="preserve">{esc(val)}</t></is></c>')
                elif kind in ("n", "d"):
                    cells.append(f'<c r="{ref}" s="{st}"><v>{val!r}</v></c>')
                elif kind == "blank":
                    cells.append(f'<c r="{ref}" s="{st}"/>')
            out.append(f'<row r="{r}"{ht}>{"".join(cells)}</row>')
        pane = ""
        if self.freeze:
            m = re.match(r"([A-Z]+)(\d+)$", self.freeze)
            xs, ys = colnum(m.group(1)) - 1, int(m.group(2)) - 1
            pane_name = "bottomRight" if xs and ys else ("bottomLeft" if ys else "topRight")
            pane = (f'<pane{" xSplit=" + chr(34) + str(xs) + chr(34) if xs else ""}{" ySplit=" + chr(34) + str(ys) + chr(34) if ys else ""} '
                    f'topLeftCell="{self.freeze}" activePane="{pane_name}" state="frozen"/>'
                    f'<selection pane="{pane_name}" activeCell="{self.freeze}" sqref="{self.freeze}"/>')
        zoom = f' zoomScale="{self.zoom}" zoomScaleNormal="{self.zoom}"' if self.zoom else ""
        cols = "".join(f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>' for c, w in sorted(self.widths.items()))
        cf = "".join(f'<conditionalFormatting sqref="{rng}"><cfRule type="expression" dxfId="{dxf}" priority="{k + 1}">'
                     f"<formula>{esc(fm)}</formula></cfRule></conditionalFormatting>" for k, (rng, fm, dxf) in enumerate(self.cf))
        mg = (f'<mergeCells count="{len(self.merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in self.merges)
              + "</mergeCells>") if self.merges else ""
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                f'xmlns:r="{NS_REL}"><sheetPr><tabColor rgb="FF002060"/></sheetPr>'
                f'<dimension ref="A1:{colname(maxc)}{maxr}"/>'
                f'<sheetViews><sheetView showGridLines="0"{zoom} workbookViewId="0">{pane}</sheetView></sheetViews>'
                '<sheetFormatPr defaultRowHeight="16"/>'
                + (f"<cols>{cols}</cols>" if cols else "")
                + f'<sheetData>{"".join(out)}</sheetData>{mg}{cf}'
                '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
                + (f'<drawing r:id="{drawing_rid}"/>' if drawing_rid else "")
                + (f'<legacyDrawing r:id="{legacy_rid}"/>' if legacy_rid else "")
                + "</worksheet>")


def vml_blocks(count):
    """1024-id shape blocks a VML drawing with `count` notes needs (ids 1024 * n + 1 .. 1024 * n + count)."""
    return max(1, -(-(count + 1) // 1024))


def comments_parts(comments, n, author="Claude"):
    """(commentsN.xml, vmlDrawingN.vml) for {ref: text}. n = the first free shape-id block: each VML drawing needs
    its own blocks (o:idmap data = "n,n+1,...", shape ids from 1024 * n + 1), or Excel repairs the file."""
    items = "".join(f'<comment ref="{ref}" authorId="0"><text><r><rPr><sz val="10"/><rFont val="Tahoma"/></rPr>'
                    f'<t xml:space="preserve">{esc(t)}</t></r></text></comment>' for ref, t in comments.items())
    cx = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          f"<authors><author>{esc(author)}</author></authors><commentList>{items}</commentList></comments>")
    shapes = []
    for k, ref in enumerate(comments):
        m = re.match(r"([A-Z]+)(\d+)$", ref)
        c, r = colnum(m.group(1)) - 1, int(m.group(2)) - 1
        shapes.append(
            f'<v:shape id="_x0000_s{1024 * n + 1 + k}" type="#_x0000_t202" style="position:absolute;margin-left:59.25pt;'
            'margin-top:1.5pt;width:240pt;height:80pt;z-index:1;visibility:hidden" fillcolor="#ffffe1" o:insetmode="auto">'
            '<v:fill color2="#ffffe1"/><v:shadow on="t" color="black" obscured="t"/><v:path o:connecttype="none"/>'
            '<v:textbox style="mso-direction-alt:auto"><div style="text-align:left"/></v:textbox>'
            f'<x:ClientData ObjectType="Note"><x:MoveWithCells/><x:SizeWithCells/>'
            f"<x:Anchor>{c + 1}, 15, {r}, 2, {c + 5}, 15, {r + 5}, 16</x:Anchor><x:AutoFill>False</x:AutoFill>"
            f"<x:Row>{r}</x:Row><x:Column>{c}</x:Column></x:ClientData></v:shape>")
    vml = (f'<xml xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
           'xmlns:x="urn:schemas-microsoft-com:office:excel"><o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="'
           + ",".join(str(n + b) for b in range(vml_blocks(len(comments)))) + '"/></o:shapelayout>'
           '<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe">'
           '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>'
           + "".join(shapes) + "</xml>")
    return cx, vml
