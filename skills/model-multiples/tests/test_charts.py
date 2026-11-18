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


def _line(vals, title="T", name="P/E"):
    x = charts.line(title, ("'M'!$A$1:$A$%d" % len(vals), list(range(len(vals)))),
                    [{"name": name, "ref": "'M'!$B$1", "vals": vals, "color": "1F4E79"}], "0.0")
    return ET.fromstring(x.split("\n", 1)[1])


def test_special_characters_in_title_and_name_survive():
    root = _line([1.0, 2.0], title="A & B <x>", name="P&L <ttm>")
    assert "".join(t.text for t in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")) == "A & B <x>"
    assert root.find(f".//{C}ser/{C}tx/{C}v").text == "P&L <ttm>"


def test_nan_is_omitted_from_cache():
    root = _line([1.0, float("nan"), 3.0])
    assert len(root.findall(f".//{C}val//{C}pt")) == 2


def test_single_point_series_works():
    assert len(_line([5.0]).findall(f".//{C}val//{C}pt")) == 1


def test_empty_inputs_raise():
    import pytest
    with pytest.raises(ValueError):
        charts.line("T", ("r", []), [], "0")
    with pytest.raises(ValueError):
        charts.scatter("T", [])


def test_cross_between_line_between_scatter_midcat():
    assert _line([1.0, 2.0]).find(f".//{C}valAx/{C}crossBetween").get("val") == "between"
    pts = [{"name": "A", "x": ("r", 1.0), "y": ("r", 2.0), "subject": False}]
    sc = ET.fromstring(charts.scatter("T", pts).split("\n", 1)[1])
    assert {e.get("val") for e in sc.iter(f"{C}crossBetween")} == {"midCat"}


def test_scatter_fit_series_carries_a_linear_trendline_and_no_markers():
    # The line through the peers is Excel's own linear trendline on one unlabelled series of every peer's point
    # (a left-out peer is #N/A there), so it refits whenever the user flips an Include cell.
    pts = [{"name": "PODD", "x": ("'Multiples'!$S$41", 0.20), "y": ("'Multiples'!$U$41", 55.0), "subject": False}]
    fit = {"x": ("'Multiples'!$S$40:$S$42", [0.14, 0.20, 0.1]), "y": ("'Multiples'!$U$40:$U$42", [None, 55.0, 30.0])}
    root = ET.fromstring(charts.scatter("t", pts, fit=fit).split("\n", 1)[1])
    sers = list(root.iter(f"{C}ser"))
    assert len(sers) == 2
    tl = sers[-1].find(f"{C}trendline")
    assert tl is not None and tl.find(f"{C}trendlineType").get("val") == "linear"
    assert sers[-1].find(f"{C}marker/{C}symbol").get("val") == "none"
    assert all(s.find(f"{C}trendline") is None for s in sers[:-1])
