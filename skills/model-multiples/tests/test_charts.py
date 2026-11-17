import xml.etree.ElementTree as ET

import charts

C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"


def test_line_chart_is_valid_xml_with_one_series_per_input_and_gaps_for_nm():
    x = charts.line("DXCM P/E (TTM)", ("'Multiples'!$A$10:$A$12", [45000, 45007, 45014]),
                    [{"name": "P/E", "ref": "'Multiples'!$P$10:$P$12", "vals": [30.0, None, 32.0], "color": "1F4E79"}],
                    '0.0"x"')
    root = ET.fromstring(x.split("\n", 1)[1])
    assert len(list(root.iter(f"{C}ser"))) == 1
    assert root.find(f".//{C}dispBlanksAs").get("val") == "gap"
    assert len(list(root.iter(f"{C}pt"))) == 3 + 2          # 3 dates + 2 numeric values (NM skipped)


def test_scatter_has_one_labelled_series_per_comp_and_subject_highlighted():
    pts = [{"name": "DXCM", "x": ("'Multiples'!$S$40", 0.14), "y": ("'Multiples'!$Q$40", 40.0), "subject": True},
           {"name": "PODD", "x": ("'Multiples'!$S$41", 0.20), "y": ("'Multiples'!$Q$41", 55.0), "subject": False}]
    root = ET.fromstring(charts.scatter("P/E vs revenue growth", pts).split("\n", 1)[1])
    sers = list(root.iter(f"{C}ser"))
    assert len(sers) == 2
    assert root.find(f".//{C}scatterChart") is not None
    assert all(s.find(f".//{C}showSerName").get("val") == "1" for s in sers)
