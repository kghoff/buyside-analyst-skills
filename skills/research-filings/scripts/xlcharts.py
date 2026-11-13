"""(Copied from model-industry, Nov 2026; adds invisible bars for waterfalls and floating ranges, marker-only
lines, text categories and a size per marker.) Annual charts in the house style of the Idio Chart tab (from model-price-history/assets/chart_fcf.xml):
14 pt bold title, grey 404040 axis text, light E0E0E0 gridlines, legend on top, thin D9D9D9 border.
Any number of series, in bar / line / area groups on a primary and an optional secondary axis.
chart(title, (cat_ref, cat_vals), groups, y1, y2=None); a group = {"type": "bar"|"line"|"area",
"grouping": "clustered"|"stacked"|"percentStacked"|"standard", "axis": 1|2, "series": [{"name", "name_ref", "ref",
"vals", "color", "dash", "thin", "marker", "labels"}]}; y = {"fmt", "title", "min", "max"}."""
from xlsx import esc

SUBJECT, INDUSTRY, BAR = "E07040", "1F1F1F", "3F78D1"
PEERS = ["1BAF7A", "EDA100", "6250D6", "7F7F7F", "9DC3E6", "A9D18E", "3F78D1"]   # BAR's blue last
NS = ('xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _txt(sz, b=0, color="404040", rot=None):
    body = f'<a:bodyPr rot="{rot}" vert="horz"/>' if rot else "<a:bodyPr/>"
    return (f'<c:txPr>{body}<a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="{b}"><a:solidFill><a:srgbClr val="{color}"/>'
            '</a:solidFill></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>')


def _rich(text, sz, b, rot=None):
    body = f'<a:bodyPr rot="{rot}" vert="horz"/>' if rot else "<a:bodyPr/>"
    return (f'<c:title><c:tx><c:rich>{body}<a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="{b}"/></a:pPr><a:r>'
            f'<a:rPr lang="en-US" sz="{sz}" b="{b}"/><a:t>{esc(text)}</a:t></a:r></a:p></c:rich></c:tx>'
            '<c:overlay val="0"/></c:title>')


def _cache(vals, fmt):
    pts = "".join(f'<c:pt idx="{j}"><c:v>{float(v)!r}</c:v></c:pt>' for j, v in enumerate(vals)
                  if isinstance(v, (int, float)) and not isinstance(v, bool))
    return f'<c:numCache><c:formatCode>{esc(fmt)}</c:formatCode><c:ptCount val="{len(vals)}"/>{pts}</c:numCache>'


def _ser(i, s, cat, kind, fmt):
    # literal series names: the rows' own labels repeat ("Share of industry revenue" in every block)
    tx = f'<c:tx><c:v>{esc(s["name"])}</c:v></c:tx>'
    fill = f'<a:solidFill><a:srgbClr val="{s["color"]}"/></a:solidFill>' if s.get("color") else "<a:noFill/>"
    if kind == "line" and s.get("noline"):          # markers only (a guide midpoint, an actual)
        sp = "<c:spPr><a:ln w=\"28575\"><a:noFill/></a:ln></c:spPr>"
        mk = (f'<c:marker><c:symbol val="{s.get("symbol", "circle")}"/><c:size val="{s.get("size", 7)}"/><c:spPr>{fill}'
              '<a:ln><a:noFill/></a:ln></c:spPr></c:marker>')
    elif kind == "line":
        dash = '<a:prstDash val="dash"/>' if s.get("dash") else ""
        sp = f'<c:spPr><a:ln w="{12700 if s.get("thin") else 28575}" cap="rnd">{fill}{dash}<a:round/></a:ln></c:spPr>'
        mk = (f'<c:marker><c:symbol val="circle"/><c:size val="5"/><c:spPr>{fill}<a:ln><a:noFill/></a:ln></c:spPr></c:marker>'
              if s.get("marker") else '<c:marker><c:symbol val="none"/></c:marker>')
    else:
        sp, mk = f"<c:spPr>{fill}{'' if s.get('color') else '<a:ln><a:noFill/></a:ln>'}</c:spPr>", ""
    inv = '<c:invertIfNegative val="0"/>' if kind == "bar" else ""
    lbl = ""
    if s.get("labels"):
        pos = '<c:dLblPos val="outEnd"/>' if kind == "bar" else '<c:dLblPos val="t"/>'
        lbl = (f'<c:dLbls><c:numFmt formatCode="{esc(s["labels"])}" sourceLinked="0"/><c:spPr><a:noFill/><a:ln><a:noFill/>'
               f'</a:ln></c:spPr>{_txt(800)}{pos}<c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/>'
               '<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>')
    cat_ref, cat_vals = cat[0], cat[1]
    if any(isinstance(v, str) for v in cat_vals):     # text categories (waterfall steps, cost lines)
        pts = "".join(f'<c:pt idx="{j}"><c:v>{esc(v)}</c:v></c:pt>' for j, v in enumerate(cat_vals))
        cx = f'<c:strRef><c:f>{esc(cat_ref)}</c:f><c:strCache><c:ptCount val="{len(cat_vals)}"/>{pts}</c:strCache></c:strRef>'
    else:
        cx = f'<c:numRef><c:f>{esc(cat_ref)}</c:f>{_cache(cat_vals, "0")}</c:numRef>'
    body = (f'<c:idx val="{i}"/><c:order val="{i}"/>{tx}{sp}{mk}{inv}{lbl}'
            f'<c:cat>{cx}</c:cat>'
            f'<c:val><c:numRef><c:f>{esc(s["ref"])}</c:f>{_cache(s["vals"], fmt)}</c:numRef></c:val>')
    smooth = '<c:smooth val="0"/>' if kind == "line" else ""
    return f"<c:ser>{body}{smooth}</c:ser>"


def _group(g, cat, i0, fmt):
    kind = g["type"]
    ax = '<c:axId val="301"/><c:axId val="302"/>' if g.get("axis", 1) == 1 else '<c:axId val="303"/><c:axId val="304"/>'
    sers = "".join(_ser(i0 + k, s, cat, kind, fmt) for k, s in enumerate(g["series"]))
    if kind == "bar":
        grp = g.get("grouping", "clustered")
        ov = '<c:overlap val="100"/>' if grp != "clustered" else ""
        return (f'<c:barChart><c:barDir val="col"/><c:grouping val="{grp}"/><c:varyColors val="0"/>{sers}'
                f'<c:gapWidth val="60"/>{ov}{ax}</c:barChart>')
    if kind == "area":
        return (f'<c:areaChart><c:grouping val="{g.get("grouping", "stacked")}"/><c:varyColors val="0"/>{sers}'
                f"{ax}</c:areaChart>")
    return f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{sers}<c:marker val="1"/>{ax}</c:lineChart>'


def _valax(axid, cross, y, right):
    sc = '<c:orientation val="minMax"/>' + (f'<c:max val="{y["max"]}"/>' if "max" in y else "") + \
         (f'<c:min val="{y["min"]}"/>' if "min" in y else "")
    grid = "" if right else ('<c:majorGridlines><c:spPr><a:ln w="6350"><a:solidFill><a:srgbClr val="E0E0E0"/>'
                             "</a:solidFill></a:ln></c:spPr></c:majorGridlines>")
    return (f'<c:valAx><c:axId val="{axid}"/><c:scaling>{sc}</c:scaling><c:delete val="0"/>'
            f'<c:axPos val="{"r" if right else "l"}"/>{grid}{_rich(y.get("title", ""), 900, 0, "-5400000")}'
            f'<c:numFmt formatCode="{esc(y["fmt"])}" sourceLinked="0"/><c:majorTickMark val="none"/>'
            '<c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr><a:ln><a:noFill/></a:ln></c:spPr>'
            f'{_txt(900)}<c:crossAx val="{cross}"/><c:crosses val="{"max" if right else "autoZero"}"/>'
            '<c:crossBetween val="between"/></c:valAx>')


def _catax(axid, cross, deleted):
    if deleted:
        return (f'<c:catAx><c:axId val="{axid}"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="1"/>'
                '<c:axPos val="b"/><c:numFmt formatCode="0" sourceLinked="1"/><c:majorTickMark val="none"/>'
                f'<c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:crossAx val="{cross}"/>'
                '<c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/>'
                '<c:noMultiLvlLbl val="0"/></c:catAx>')
    return (f'<c:catAx><c:axId val="{axid}"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
            '<c:axPos val="b"/><c:numFmt formatCode="0" sourceLinked="0"/><c:majorTickMark val="none"/>'
            '<c:minorTickMark val="none"/><c:tickLblPos val="low"/><c:spPr><a:ln w="9525"><a:solidFill>'
            f'<a:srgbClr val="BFBFBF"/></a:solidFill></a:ln></c:spPr>{_txt(1000)}<c:crossAx val="{cross}"/>'
            '<c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/>'
            '<c:noMultiLvlLbl val="0"/></c:catAx>')


def chart(title, cat, groups, y1, y2=None):
    body, i = "", 0
    hidden = [k for k, x in enumerate(x for g in groups for x in g["series"]) if not x.get("color") or x.get("nolegend")]
    for g in groups:
        fmt = (y2 if g.get("axis", 1) == 2 else y1)["fmt"]
        body += _group(g, cat, i, fmt)
        i += len(g["series"])
    axes = _catax(301, 302, False) + _valax(302, 301, y1, False)
    if y2:
        axes += _catax(303, 304, True) + _valax(304, 303, y2, True)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<c:chartSpace {NS}><c:date1904 val="0"/><c:lang val="en-US"/><c:roundedCorners val="0"/>'
            f'<c:style val="2"/><c:chart>{_rich(title, 1400, 1)}<c:autoTitleDeleted val="0"/><c:plotArea><c:layout/>'
            f'{body}{axes}<c:spPr><a:noFill/></c:spPr></c:plotArea><c:legend><c:legendPos val="t"/>'
            + "".join(f'<c:legendEntry><c:idx val="{k}"/><c:delete val="1"/></c:legendEntry>' for k in hidden)
            + f'<c:overlay val="0"/>{_txt(1000)}</c:legend><c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/>'
            '<c:showDLblsOverMax val="1"/></c:chart><c:spPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill>'
            '<a:ln w="9525"><a:solidFill><a:srgbClr val="D9D9D9"/></a:solidFill></a:ln></c:spPr>'
            '<c:printSettings><c:headerFooter/><c:pageMargins b="0.75" l="0.7" r="0.7" t="0.75" header="0.3" '
            'footer="0.3"/><c:pageSetup/></c:printSettings></c:chartSpace>')
