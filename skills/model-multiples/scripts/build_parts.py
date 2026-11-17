"""Package plumbing for the Multiples tab: the sheet part, one drawing with an anchor per chart, the chart parts,
and comments + VML. Adapted from model-consensus/scripts/build.py (write_parts, anchor, next_vml_id); extended to many
charts."""
import re

from xlsx import CT, comments_parts

COL0, ROW0, NCOLS, NROWS = 21, 3, 10, 18           # charts start at column V, two across, 18 rows tall


def next_vml_id(pkg):
    ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
           for d in re.findall(rb'idmap\b[^>]*\bdata="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
    return max(ids + [0]) + 1


def anchor(col, row, nid, name, rid):
    return (f'<xdr:twoCellAnchor editAs="oneCell"><xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>0</xdr:colOff>'
            f'<xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>{col + NCOLS}</xdr:col>'
            f'<xdr:colOff>0</xdr:colOff><xdr:row>{row + NROWS}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
            '<xdr:graphicFrame macro="">'
            f'<xdr:nvGraphicFramePr><xdr:cNvPr id="{nid}" name="{name}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
            '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
            "</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>")


def write_parts(pkg, st, sh, chart_list, tab):
    pkg.put("xl/styles.xml", st.render())
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    nxt = next_vml_id(pkg)
    part = pkg.add_sheet(tab, "")
    drid = lrid = None
    if chart_list:
        dpart = f"xl/drawings/drawing{pkg.free('xl/drawings/drawing{}.xml')}.xml"
        anchors = []
        for i, xml in enumerate(chart_list):
            cpart = f"xl/charts/chart{pkg.free('xl/charts/chart{}.xml')}.xml"
            pkg.put(cpart, xml)
            pkg.content_override(cpart, CT["chart"])
            rid = pkg.attach(dpart, "chart", cpart)
            anchors.append(anchor(COL0 + (i % 2) * (NCOLS + 1), ROW0 + (i // 2) * (NROWS + 1), i + 2, f"Chart {i + 1}", rid))
        pkg.put(dpart, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                       '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">' + "".join(anchors) + "</xdr:wsDr>")
        pkg.content_override(dpart, CT["drawing"])
        drid = pkg.attach(part, "drawing", dpart)
    if sh.comments:
        cn = pkg.free("xl/comments{}.xml")
        vn = pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(sh.comments, nxt)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, sh.xml(drid, lrid))
    pkg.finish()
