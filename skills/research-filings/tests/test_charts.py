import os

import pytest

from charts import draw

SERIES = {"Rev | US": {"FY2023": 70, "FY2024": 80}, "Rev | Intl": {"FY2023": 30, "FY2024": 50}}


def spec(**kw):
    base = {"id": "c1", "kind": "stacked", "title": "Revenue by geography", "metrics": list(SERIES),
            "labels": ["US", "International"], "freq": "FY", "start": 2023, "end": 2024, "unit": "$M",
            "source": "Model, MOD rows 20-26"}
    base.update(kw)
    return base


def test_a_chart_without_a_source_is_refused():
    # every figure in the report carries a source line the user can trace
    with pytest.raises(ValueError, match="source"):
        draw(spec(source=""), SERIES, "", "")


@pytest.mark.parametrize("kind", ["line", "bar", "stacked", "share"])
def test_series_charts_write_a_png(tmp_path, kind):
    out = draw(spec(kind=kind), SERIES, str(tmp_path), str(tmp_path))
    assert os.path.getsize(out) > 5000


def test_an_unknown_metric_is_named_in_the_error():
    with pytest.raises(ValueError, match="Rev \\| Nowhere"):
        draw(spec(metrics=["Rev | Nowhere"]), SERIES, "", "")


def test_waterfall_and_diagram(tmp_path):
    w = draw({"id": "w", "kind": "waterfall", "title": "Bridge", "source": "Calc",
              "steps": [["=FY2023", 250], ["Revenue", 50], ["Opex", -10], ["=FY2024", 290]]}, {}, "", str(tmp_path))
    d = draw({"id": "d", "kind": "diagram", "title": "Build", "source": "This report",
              "boxes": [{"x": 5, "y": 50, "w": 40, "h": 30, "title": "Volume", "body": "users"}],
              "arrows": [[45, 65, 60, 65]]}, {}, "", str(tmp_path))
    assert os.path.exists(w) and os.path.exists(d)


def test_guidance_chart_reads_the_guidance_track(tmp_path):
    (tmp_path / "guidance_track.csv").write_text(
        "fiscal_year,metric,basis,initial_date,initial_kind,initial_low,initial_high,revisions,latest_date,"
        "latest_low,latest_high,actual,vs_initial_mid,sources\n2024,Revenue,reported,2024-02-01,hard,100,110,0,,,,112,0.06,x\n")
    out = draw({"id": "g", "kind": "guidance", "title": "Guide vs actual", "metric": "Revenue", "source": "Press releases"},
               {}, str(tmp_path), str(tmp_path))
    assert os.path.exists(out)


def test_quarterly_ticks_mark_only_q1_with_the_year():
    from charts import tick_marks
    ps = [f"Q{q} {y}" for y in (2016, 2017) for q in range(1, 5)]
    assert tick_marks(ps) == [(0, "2016"), (4, "2017")]


def test_derived_series_ratio_and_growth_values():
    from charts import _value
    s = {"Cost": {"FY2024": -60.0, "FY2023": -50.0}, "Rev": {"FY2024": 100.0, "FY2023": 100.0, "Q3 2024": 110.0, "Q3 2023": 100.0}}
    assert _value({"ratio": ["Cost", "Rev"]}, "FY2024", s) == 60.0      # cost line shows as a positive %
    assert _value({"growth": "Rev"}, "Q3 2024", s) == pytest.approx(10.0)
    assert _value({"ratio": ["Cost", "Rev"]}, "Q3 2024", s) is None     # missing input leaves a gap


def test_derived_series_chart_draws_and_names_a_missing_input(tmp_path):
    s = {"Cost": {"FY2023": -50, "FY2024": -60}, "Rev": {"FY2023": 100, "FY2024": 100}}
    out = draw(spec(kind="line", metrics=[{"ratio": ["Cost", "Rev"]}, {"growth": "Rev"}], labels=["Cost %", "Growth"],
                    unit="%"), s, "", str(tmp_path))
    assert os.path.getsize(out) > 5000
    with pytest.raises(ValueError, match="Rev \\| Nowhere"):
        draw(spec(metrics=[{"ratio": ["Cost", "Rev | Nowhere"]}]), s, "", "")
