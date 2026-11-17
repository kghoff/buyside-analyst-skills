"""Charts for the Multiples tab in the house style of the Idio Chart and Consensus tabs (14 pt bold title, grey 404040
axis text, light E0E0E0 gridlines, legend on top, thin D9D9D9 border). Adapted from model-consensus/scripts/charts.py.
NM points are missing from the cache and drawn as gaps."""
import math

from xlsx import esc

NS = ('xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
SUBJECT, OTHER = "C00000", "1F4E79"


def _txt(sz):
    return (f'<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="0"><a:solidFill><a:srgbClr val="404040"/>'
            '</a:solidFill></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>')


def _title(text):
    return ('<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="1400" b="1"/></a:pPr><a:r>'
            f'<a:rPr lang="en-US" sz="1400" b="1"/><a:t>{esc(text)}</a:t></a:r></a:p></c:rich></c:tx>'
            '<c:overlay val="0"/></c:title>')


def _cache(vals, fmt):
    pts = "".join(f'<c:pt idx="{j}"><c:v>{float(v)!r}</c:v></c:pt>' for j, v in enumerate(vals)
                  if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
    return f'<c:numCache><c:formatCode>{esc(fmt)}</c:formatCode><c:ptCount val="{len(vals)}"/>{pts}</c:numCache>'


def _valax(ax, cross, pos, fmt, grid=True, delete=False):
    g = ('<c:majorGridlines><c:spPr><a:ln w="6350"><a:solidFill><a:srgbClr val="E0E0E0"/></a:solidFill></a:ln>'
         '</c:spPr></c:majorGridlines>') if grid else ""
    return (f'<c:valAx><c:axId val="{ax}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="{1 if delete else 0}"/><c:axPos val="{pos}"/>{g}'
            f'<c:numFmt formatCode="{esc(fmt)}" sourceLinked="0"/><c:majorTickMark val="none"/>'
            f'<c:minorTickMark val="none"/><c:tickLblPos val="low"/><c:spPr><a:ln><a:noFill/></a:ln></c:spPr>{_txt(900)}'
            f'<c:crossAx val="{cross}"/><c:crosses val="autoZero"/><c:crossBetween val="midCat"/></c:valAx>')


def _wrap(title, plot, legend=True):
    leg = f'<c:legend><c:legendPos val="t"/><c:overlay val="0"/>{_txt(1000)}</c:legend>' if legend else ""
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<c:chartSpace {NS}><c:date1904 val="0"/><c:lang val="en-US"/><c:roundedCorners val="0"/>'
            f'<c:chart>{_title(title)}<c:autoTitleDeleted val="0"/><c:plotArea><c:layout/>{plot}'
            f'<c:spPr><a:noFill/></c:spPr></c:plotArea>{leg}<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>'
            '<c:spPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill><a:ln w="9525"><a:solidFill>'
            '<a:srgbClr val="D9D9D9"/></a:solidFill></a:ln></c:spPr></c:chartSpace>')


def line(title, cat, series, yfmt):
    """cat = (ref, excel serial dates); series = [{name, ref, vals, color, dash?}]."""
    sers = ""
    for i, s in enumerate(series):
        dash = '<a:prstDash val="dash"/>' if s.get("dash") else ""
        sers += (f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/><c:tx><c:v>{esc(s["name"])}</c:v></c:tx>'
                 f'<c:spPr><a:ln w="19050" cap="rnd"><a:solidFill><a:srgbClr val="{s["color"]}"/></a:solidFill>{dash}'
                 '<a:round/></a:ln></c:spPr><c:marker><c:symbol val="none"/></c:marker>'
                 f'<c:cat><c:numRef><c:f>{esc(cat[0])}</c:f>{_cache(cat[1], "yyyy-mm-dd")}</c:numRef></c:cat>'
                 f'<c:val><c:numRef><c:f>{esc(s["ref"])}</c:f>{_cache(s["vals"], yfmt)}</c:numRef></c:val>'
                 '<c:smooth val="0"/></c:ser>')
    axes = ('<c:dateAx><c:axId val="601"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
            '<c:axPos val="b"/><c:numFmt formatCode="mmm yy" sourceLinked="0"/><c:majorTickMark val="out"/>'
            '<c:minorTickMark val="none"/><c:tickLblPos val="low"/><c:spPr><a:ln w="9525"><a:solidFill>'
            f'<a:srgbClr val="BFBFBF"/></a:solidFill></a:ln></c:spPr>{_txt(900)}<c:crossAx val="602"/>'
            '<c:crosses val="autoZero"/><c:auto val="0"/><c:lblOffset val="100"/><c:baseTimeUnit val="days"/>'
            '<c:majorUnit val="12"/><c:majorTimeUnit val="months"/></c:dateAx>' + _valax(602, 601, "l", yfmt))
    plot = (f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{sers}<c:marker val="1"/>'
            f'<c:axId val="601"/><c:axId val="602"/></c:lineChart>{axes}')
    return _wrap(title, plot, legend=len(series) > 1)


def scatter(title, points, xfmt="0%", yfmt='0"x"'):
    """points = [{name, x: (ref, value), y: (ref, value), subject}]: one series per company, labelled with its name."""
    sers = ""
    for i, p in enumerate(points):
        col = SUBJECT if p["subject"] else OTHER
        sers += (f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/><c:tx><c:v>{esc(p["name"])}</c:v></c:tx>'
                 '<c:spPr><a:ln w="19050"><a:noFill/></a:ln></c:spPr>'
                 f'<c:marker><c:symbol val="circle"/><c:size val="{9 if p["subject"] else 7}"/><c:spPr><a:solidFill>'
                 f'<a:srgbClr val="{col}"/></a:solidFill><a:ln><a:noFill/></a:ln></c:spPr></c:marker>'
                 '<c:dLbls><c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>' + _txt(800) +
                 '<c:dLblPos val="r"/><c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="0"/>'
                 '<c:showSerName val="1"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>'
                 f'<c:xVal><c:numRef><c:f>{esc(p["x"][0])}</c:f>{_cache([p["x"][1]], xfmt)}</c:numRef></c:xVal>'
                 f'<c:yVal><c:numRef><c:f>{esc(p["y"][0])}</c:f>{_cache([p["y"][1]], yfmt)}</c:numRef></c:yVal>'
                 '<c:smooth val="0"/></c:ser>')
    plot = (f'<c:scatterChart><c:scatterStyle val="lineMarker"/><c:varyColors val="0"/>{sers}'
            '<c:axId val="701"/><c:axId val="702"/></c:scatterChart>'
            + _valax(701, 702, "b", xfmt, grid=False) + _valax(702, 701, "l", yfmt))
    return _wrap(title, plot, legend=False)
