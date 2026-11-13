"""The rating-history chart, in the house style of the Idio Chart tab (14 pt bold title, grey 404040 axis text,
light E0E0E0 gridlines, legend on top, thin D9D9D9 border; see model-industry/scripts/charts.py). A line chart on a date
axis: lines for the close and the average target, marker-only series for upgrades and downgrades (#N/A elsewhere,
drawn as gaps). Excel has no downward triangle marker, so downgrades are red diamonds."""
import math

from xlsx import esc

CLOSE, AVG, UP, DOWN = "1F1F1F", "E07040", "1BAF7A", "C00000"
NS = ('xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _txt(sz):
    return (f'<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="0"><a:solidFill><a:srgbClr val="404040"/>'
            '</a:solidFill></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>')


def _title(text, sz=1400):
    return (f'<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="1"/></a:pPr><a:r>'
            f'<a:rPr lang="en-US" sz="{sz}" b="1"/><a:t>{esc(text)}</a:t></a:r></a:p></c:rich></c:tx>'
            '<c:overlay val="0"/></c:title>')


def _cache(vals, fmt):
    pts = "".join(f'<c:pt idx="{j}"><c:v>{float(v)!r}</c:v></c:pt>' for j, v in enumerate(vals)
                  if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
    return f'<c:numCache><c:formatCode>{esc(fmt)}</c:formatCode><c:ptCount val="{len(vals)}"/>{pts}</c:numCache>'


def _ser(i, s, cat):
    fill = f'<a:solidFill><a:srgbClr val="{s["color"]}"/></a:solidFill>'
    if s.get("marker"):
        sp = '<c:spPr><a:ln w="19050"><a:noFill/></a:ln></c:spPr>'
        mk = (f'<c:marker><c:symbol val="{s["marker"]}"/><c:size val="7"/><c:spPr>{fill}<a:ln><a:noFill/></a:ln>'
              '</c:spPr></c:marker>')
    else:
        dash = '<a:prstDash val="dash"/>' if s.get("dash") else ""
        sp = f'<c:spPr><a:ln w="{19050 if s.get("dash") else 22225}" cap="rnd">{fill}{dash}<a:round/></a:ln></c:spPr>'
        mk = '<c:marker><c:symbol val="none"/></c:marker>'
    return (f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/><c:tx><c:v>{esc(s["name"])}</c:v></c:tx>{sp}{mk}'
            f'<c:cat><c:numRef><c:f>{esc(cat[0])}</c:f>{_cache(cat[1], "yyyy-mm-dd")}</c:numRef></c:cat>'
            f'<c:val><c:numRef><c:f>{esc(s["ref"])}</c:f>{_cache(s["vals"], "#,##0.00")}</c:numRef></c:val>'
            '<c:smooth val="0"/></c:ser>')


def rating_chart(title, cat, series, yfmt="$#,##0"):
    sers = "".join(_ser(i, s, cat) for i, s in enumerate(series))
    axes = ('<c:dateAx><c:axId val="501"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
            '<c:axPos val="b"/><c:numFmt formatCode="mmm yy" sourceLinked="0"/><c:majorTickMark val="out"/>'
            '<c:minorTickMark val="none"/><c:tickLblPos val="low"/><c:spPr><a:ln w="9525"><a:solidFill>'
            f'<a:srgbClr val="BFBFBF"/></a:solidFill></a:ln></c:spPr>{_txt(900)}<c:crossAx val="502"/>'
            '<c:crosses val="autoZero"/><c:auto val="0"/><c:lblOffset val="100"/><c:baseTimeUnit val="days"/>'
            '<c:majorUnit val="6"/><c:majorTimeUnit val="months"/></c:dateAx>'
            '<c:valAx><c:axId val="502"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
            '<c:axPos val="l"/><c:majorGridlines><c:spPr><a:ln w="6350"><a:solidFill><a:srgbClr val="E0E0E0"/>'
            f'</a:solidFill></a:ln></c:spPr></c:majorGridlines><c:numFmt formatCode="{esc(yfmt)}" sourceLinked="0"/>'
            '<c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/>'
            f'<c:spPr><a:ln><a:noFill/></a:ln></c:spPr>{_txt(900)}<c:crossAx val="501"/><c:crosses val="autoZero"/>'
            '<c:crossBetween val="between"/></c:valAx>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<c:chartSpace {NS}><c:date1904 val="0"/><c:lang val="en-US"/><c:roundedCorners val="0"/><c:style val="2"/>'
            f'<c:chart>{_title(title)}<c:autoTitleDeleted val="0"/><c:plotArea><c:layout/>'
            f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{sers}<c:marker val="1"/>'
            f'<c:axId val="501"/><c:axId val="502"/></c:lineChart>{axes}<c:spPr><a:noFill/></c:spPr></c:plotArea>'
            f'<c:legend><c:legendPos val="t"/><c:overlay val="0"/>{_txt(1000)}</c:legend><c:plotVisOnly val="1"/>'
            '<c:dispBlanksAs val="gap"/></c:chart><c:spPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill>'
            '<a:ln w="9525"><a:solidFill><a:srgbClr val="D9D9D9"/></a:solidFill></a:ln></c:spPr>'
            '<c:printSettings><c:headerFooter/><c:pageMargins b="0.75" l="0.7" r="0.7" t="0.75" header="0.3" '
            'footer="0.3"/><c:pageSetup/></c:printSettings></c:chartSpace>')
