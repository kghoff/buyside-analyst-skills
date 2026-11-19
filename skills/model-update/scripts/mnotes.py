# _add_notes, _vml_ns and _alloc_ids copied from skills/model-forecast/scripts/build.py (keep in sync).
"""Cell notes on MOD, written into its comments part (raw XML). A note starting with NOTE is the skill's own and is
rewritten on a rerun; on the user's own note the text is appended."""
import re

from xlsx import CT, RT, colnum, esc, relpath_of, resolve, unesc

NOTE = "Update: "


def add_notes(pkg, part, notes, prefix=NOTE):
    """Notes on MOD: append to its comments part (a note already on that cell is replaced), or create one. Only a
    note starting with `prefix` (the skill's own) is rewritten; on the user's note the text is appended."""
    if not notes:
        return
    rels = {t: resolve(part, g) for _, (t, g) in pkg.rels(relpath_of(part)).items()}
    if RT["comments"] in rels and RT["vml"] in rels:
        cpart, vpart = rels[RT["comments"]], rels[RT["vml"]]
        cx = pkg.text(cpart)
        notes = dict(notes)
        for ref in list(notes):
            old = re.search(rf'<comment ref="{ref}"[^>]*>.*?</comment>', cx, re.S)
            if not old:
                continue
            text = "".join(unesc(t) for t in re.findall(r"<t\b[^>]*>(.*?)</t>", old.group(0), re.S))
            if text.startswith(prefix):               # the skill's own note: rewrite it
                cx = cx[:old.start()] + cx[old.end():]
                continue
            # The user's note: keep it, (re)append the plan's source as its own run
            c = re.sub(r"<r>(?:(?!</r>).)*?<t\b[^>]*>\n\n" + re.escape(prefix) + r".*?</t></r>", "", old.group(0), flags=re.S)
            c = re.sub(r"<text>(<t\b[^>]*>.*?</t>)", r"<text><r>\1</r>", c, flags=re.S)
            c = c.replace("</text>", f'<r><t xml:space="preserve">{esc(chr(10) * 2 + notes.pop(ref))}</t></r></text>')
            cx = cx[:old.start()] + c + cx[old.end():]
        cx = cx.replace("<commentList/>", "<commentList></commentList>")
        add = "".join(f'<comment ref="{r}" authorId="0"><text><r><rPr><sz val="10"/><rFont val="Tahoma"/></rPr>'
                      f'<t xml:space="preserve">{esc(t)}</t></r></text></comment>' for r, t in notes.items())
        pkg.put(cpart, cx.replace("</commentList>", add + "</commentList>"))
        vml = pkg.text(vpart)
        rc = [(int(re.search(r"\d+", r).group(0)) - 1, colnum(re.match(r"[A-Z]+", r).group(0)) - 1) for r in notes]
        for row, col in rc:                         # drop the old shape of a replaced note
            vml = re.sub(rf"<v:shape\b(?:(?!</v:shape>).)*?<x:Row>{row}</x:Row>\s*<x:Column>{col}</x:Column>.*?</v:shape>",
                         "", vml, flags=re.S)
        others = {int(x) for p, data in pkg.parts.items() if p.endswith(".vml") and p != vpart
                  for d in re.findall(rb'<\w+:idmap\b[^>]*?\bdata="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)}
        vml = _vml_ns(vml)
        vml, new_ids = _alloc_ids(vml, len(rc), others)
        shapes = ""
        for k, (row, col) in enumerate(rc):
            shapes += (f'<v:shape id="_x0000_s{new_ids[k]}" type="#_x0000_t202" style="position:absolute;margin-left:59.25pt;'
                       'margin-top:1.5pt;width:240pt;height:80pt;z-index:1;visibility:hidden" fillcolor="#ffffe1" o:insetmode="auto">'
                       '<v:fill color2="#ffffe1"/><v:shadow on="t" color="black" obscured="t"/><v:path o:connecttype="none"/>'
                       '<v:textbox style="mso-direction-alt:auto"><div style="text-align:left"/></v:textbox>'
                       f'<x:ClientData ObjectType="Note"><x:MoveWithCells/><x:SizeWithCells/><x:Anchor>{col + 1}, 15, {row}, 2, '
                       f'{col + 5}, 15, {row + 5}, 16</x:Anchor><x:AutoFill>False</x:AutoFill><x:Row>{row}</x:Row>'
                       f'<x:Column>{col}</x:Column></x:ClientData></v:shape>')
        if 'id="_x0000_t202"' not in vml:
            shapes = ('<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe">'
                      '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>' + shapes)
        pkg.put(vpart, vml.replace("</xml>", shapes + "</xml>"))
        return
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
           for d in re.findall(rb'<\w+:idmap\b[^>]*?\bdata="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
    cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
    cx, vml = comments_parts(notes, max(ids + [0]) + 1)
    pkg.put(f"xl/comments{cn}.xml", cx)
    pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
    lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
    pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, _insert_before_first(pkg.text(part), AFTER_LEGACY, f'<legacyDrawing r:id="{lrid}"/>'))


VML_NS = {"v": "urn:schemas-microsoft-com:vml", "o": "urn:schemas-microsoft-com:office:office",
          "x": "urn:schemas-microsoft-com:office:excel"}


def _vml_ns(vml):
    """Declare v: o: x: on the root (openpyxl writes its VML with ns0: prefixes and a bare <xml>)."""
    root = re.search(r"<xml\b[^>]*>", vml).group(0)
    add = "".join(f' xmlns:{p}="{u}"' for p, u in VML_NS.items() if f"xmlns:{p}=" not in root)
    return vml.replace(root, root[:-1] + add + ">", 1) if add else vml


def _alloc_ids(vml, count, others):
    """`count` new shape ids for a VML drawing, each inside a block listed in its <o:idmap data> (block n holds ids
    1024*n+1 .. 1024*n+1023). Blocks are added to the list as needed, never one another .vml part uses (`others`).
    Returns (vml with the updated idmap, ids)."""
    m = re.search(r'(<\w+:idmap\b[^>]*?\bdata=")([\d,\s]*)(")', vml)
    blocks = [int(x) for x in re.findall(r"\d+", m.group(2))] if m else []
    have = [int(i) for i in re.findall(r'id="_x0000_s(\d+)"', vml)]
    cand = max(have) + 1 if have else (1024 * blocks[0] + 1 if blocks else None)
    if cand is None:
        b = next(n for n in range(1, 10 ** 6) if n not in others)
        blocks, cand = [b], 1024 * b + 1
    ids = []
    while len(ids) < count:
        b, off = divmod(cand, 1024)
        if off == 0:                                   # 1024*n is in no block
            cand += 1
            continue
        if b not in blocks:
            if b in others:                            # jump to the next block nobody uses
                b = next(n for n in range(b + 1, 10 ** 6) if n not in others and n not in blocks)
                cand = 1024 * b + 1
            blocks.append(b)
        ids.append(cand)
        cand += 1
    data = ",".join(str(b) for b in blocks)
    if m:
        vml = vml[:m.start()] + m.group(1) + data + m.group(3) + vml[m.end():]
    else:
        vml = re.sub(r"(<xml\b[^>]*>)", r'\1<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="' + data
                     + '"/></o:shapelayout>', vml, count=1)
    return vml, ids
