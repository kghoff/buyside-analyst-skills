import re
import xml.dom.minidom

import charts

CAT = ("'Industry P&L'!$C$4:$E$4", [2023, 2024, 2025])


def ser(name, color, **kw):
    return dict({"name": name, "name_ref": "'Industry P&L'!$B$10", "ref": "'Industry P&L'!$C$10:$E$10",
                 "vals": [1.0, None, 3.0], "color": color}, **kw)


def test_combo_chart_is_valid_xml_with_two_axes_and_gaps():
    x = charts.chart("Capital cycle", CAT,
                     [{"type": "bar", "axis": 1, "series": [ser("Capex / sales", "3F78D1")]},
                      {"type": "line", "axis": 1, "series": [ser("ROIC", "1F1F1F")]},
                      {"type": "line", "axis": 2, "series": [ser("Capex / D&A", "EDA100", dash=True)]}],
                     {"fmt": "0%", "title": "%"}, {"fmt": '0.0"x"', "title": "x"})
    xml.dom.minidom.parseString(x)
    assert x.count("<c:ser>") == 3
    assert re.findall(r'<c:idx val="(\d+)"/>', x) == ["0", "1", "2"]       # unique series indices
    assert '<c:dispBlanksAs val="gap"/>' in x
    assert x.count("<c:valAx>") == 2 and '<c:crosses val="max"/>' in x
    assert '<c:pt idx="1">' not in x.split("<c:val>")[1].split("</c:val>")[0]   # None is left out (a gap)


def test_stacked_area_and_single_axis():
    x = charts.chart("Market share", CAT,
                     [{"type": "area", "grouping": "percentStacked", "axis": 1,
                       "series": [ser("AAA", charts.SUBJECT), ser("BBB", charts.PEERS[0])]}],
                     {"fmt": "0%", "title": "share of revenue"})
    xml.dom.minidom.parseString(x)
    assert '<c:areaChart><c:grouping val="percentStacked"/>' in x
    assert x.count("<c:valAx>") == 1
    assert "E07040" in x


def test_first_peers_never_share_the_bar_blue():
    # Peer lines sit over the industry revenue bars; a peer drawn in the bar colour (3F78D1) disappears into them.
    assert charts.BAR not in charts.PEERS[:-1] and charts.PEERS[-1] == charts.BAR
