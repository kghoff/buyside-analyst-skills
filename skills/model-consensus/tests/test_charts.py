# tests/test_charts.py
import xml.dom.minidom

import charts


def test_chart_has_date_axis_lines_and_marker_only_series():
    x = charts.rating_chart("DXCM price, average target and rating changes",
                            ("'Consensus'!$R$5:$R$7", [46000, 46001, 46002]),
                            [{"name": "Close", "ref": "'Consensus'!$S$5:$S$7", "vals": [80, 81, 82], "color": charts.CLOSE},
                             {"name": "Average target", "ref": "'Consensus'!$T$5:$T$7", "vals": [95, None, 96],
                              "color": charts.AVG, "dash": True},
                             {"name": "Upgrade", "ref": "'Consensus'!$U$5:$U$7", "vals": [None, 81, None],
                              "color": charts.UP, "marker": "triangle"}])
    xml.dom.minidom.parseString(x)                          # well-formed
    assert "<c:dateAx>" in x and 'formatCode="mmm yy"' in x
    assert x.count("<c:ser>") == 3
    assert '<c:symbol val="triangle"/>' in x and '<a:prstDash val="dash"/>' in x
    assert '<c:dispBlanksAs val="gap"/>' in x
    avg_vals = x.split("Average target")[1].split("<c:val>")[1].split("</c:val>")[0]
    assert '<c:pt idx="1">' not in avg_vals and '<c:pt idx="2">' in avg_vals             # None left out of the cache


def test_cache_skips_non_finite_numbers():
    c = charts._cache([1.0, float("nan"), float("inf"), 2.0], "0")
    assert "nan" not in c and "inf" not in c
    assert '<c:pt idx="0">' in c and '<c:pt idx="3">' in c and '<c:pt idx="1">' not in c
