"""Every number the agent starts from is printed where it says (CLAUDE.md: never type a number that isn't printed in
a source); rounding the way a reader would is allowed, a wrong cell or line is not."""
import copy
import json
import os

import pytest

import anchors
import lo
import metrics
from conftest import FIX

OK = json.load(open(os.path.join(FIX, "plan_example.json")))
CTX = {"ticker": "TEST", "house": {"hurdle": .2, "buy_rr": 2.0, "pound_rr": 3.0, "discount": .15,
                                   "horizon_months": 12, "position": "long", "mkt_rev": .05, "mkt_oi": .08, "mkt_eps": .12}}


@pytest.fixture(scope="module")
def ctx(fixture_model, tmp_path_factory):
    """CTX plus the forward metrics context.json carries (the ntm: / ntm1: / y3: anchors are checked against them)."""
    v = lo.recalc(fixture_model, str(tmp_path_factory.mktemp("v")))
    return dict(CTX, metrics=metrics.collect(fixture_model, v))


def test_cells_and_rounding(fixture_model, tmp_path, ctx):
    v = lo.recalc(fixture_model, str(tmp_path))
    assert anchors.check(OK, v, str(tmp_path), ctx) == []
    p = copy.deepcopy(OK)
    p["inputs"]["reward_multiple.pe"]["anchor_value"] = 36.0
    assert any("Multiples!B7" in x for x in anchors.check(p, v, str(tmp_path), ctx))
    p["inputs"]["reward_multiple.pe"].update(anchor="Multiples!C7", anchor_value=81.8)   # cell holds 81.755
    assert anchors.check(p, v, str(tmp_path), ctx) == []


def test_research_line(fixture_model, tmp_path):
    v = lo.recalc(fixture_model, str(tmp_path / "v"))
    rd = tmp_path / "Filings Research"
    rd.mkdir()
    (rd / "r.md").write_text("intro\nGross margin reached 62.5% in 2025, with 1,234 sites.\n")
    p = copy.deepcopy(OK)
    p["inputs"]["risk_metric.pe"].update(anchor="Filings Research/r.md:2", anchor_value=0.625)
    assert anchors.check(p, v, str(tmp_path), CTX) == []
    p["inputs"]["risk_metric.pe"].update(anchor="Filings Research/r.md:1")
    assert anchors.check(p, v, str(tmp_path), CTX)


def test_line_thousands_and_bps(fixture_model, tmp_path):
    """A count printed with commas and a change printed in bps are read as a reader would read them."""
    v = lo.recalc(fixture_model, str(tmp_path / "v"))
    (tmp_path / "r.md").write_text("Sites rose to 1,234; gross margin fell 150 bps.\n")
    p = copy.deepcopy(OK)
    p["inputs"]["risk_metric.pe"].update(anchor="r.md:1", anchor_value=1234)
    assert anchors.check(p, v, str(tmp_path), CTX) == []
    p["inputs"]["risk_metric.pe"].update(anchor_value=0.015)
    assert anchors.check(p, v, str(tmp_path), CTX) == []
    p["inputs"]["risk_metric.pe"].update(anchor_value=0.02)
    assert anchors.check(p, v, str(tmp_path), CTX)
    p["inputs"]["risk_metric.pe"].update(anchor="r.md:9")          # past the end of the file
    assert anchors.check(p, v, str(tmp_path), CTX)


def test_house_and_tree(fixture_model, tmp_path, ctx):
    """A house input may leave chapter 11's default only with a real reason; tree targets are checked like inputs."""
    v = lo.recalc(fixture_model, str(tmp_path / "v"))
    p = copy.deepcopy(OK)
    p["inputs"]["hurdle"].update(value=0.25, reason="Higher.")
    assert any("hurdle" in x for x in anchors.check(p, v, str(tmp_path), ctx))
    p["inputs"]["hurdle"]["reason"] = ("A 25% hurdle because the filings show two dilutive deals in three years, "
                                       "so the cost of being wrong is higher than usual.")
    assert anchors.check(p, v, str(tmp_path), ctx) == []
    p = copy.deepcopy(OK)
    p["tree"][4]["target"]["anchor_value"] = 60.0                    # DCF!$C$40 holds 54.84
    assert any("DCF!$C$40" in x for x in anchors.check(p, v, str(tmp_path), ctx))


def test_missing_sheet_or_file_is_named(fixture_model, tmp_path):
    v = lo.recalc(fixture_model, str(tmp_path / "v"))
    p = copy.deepcopy(OK)
    p["inputs"]["reward_multiple.pe"]["anchor"] = "Nope!B7"
    p["inputs"]["risk_metric.pe"].update(anchor="Filings Research/missing.md:3")
    probs = anchors.check(p, v, str(tmp_path), CTX)
    assert any("Nope" in x for x in probs) and any("missing.md" in x for x in probs)


def _line_check(tmp_path, text, claimed, v="unused.xlsx"):
    (tmp_path / "r.md").write_text(text + "\n")
    p = copy.deepcopy(OK)
    p["inputs"] = {"risk_metric.pe": dict(OK["inputs"]["risk_metric.pe"], anchor="r.md:1", anchor_value=claimed)}
    p["tree"], p["normalization"] = [], None
    return anchors.check(p, v, str(tmp_path), CTX)


def test_line_ranges_are_not_minus_signs(tmp_path):
    """"20-25%" is a range a reader sees as 20% and 25%, not 20 and minus 25."""
    assert _line_check(tmp_path, "Long-run margin of 20-25% at scale.", 0.25) == []
    assert _line_check(tmp_path, "Long-run margin of 20-25% at scale.", 0.20) == []
    assert _line_check(tmp_path, "Long-run margin of 20-25% at scale.", -0.25)
    assert _line_check(tmp_path, "Margin fell to -3.5% in the quarter.", -0.035) == []


def test_line_numbers_glued_to_letters_do_not_count(tmp_path):
    """A period label or code (Q2, FY25, x2) is not a figure: anchoring 2 or 25 on it would cite a number never printed."""
    assert _line_check(tmp_path, "In Q2 of FY25 the x2 sensor launched.", 2)
    assert _line_check(tmp_path, "In Q2 of FY25 the x2 sensor launched.", 25)
    assert _line_check(tmp_path, "In Q2 of FY25 the x2 sensor launched 2 models.", 2) == []


def test_decimals_come_from_the_anchor_value_as_written(fixture_model, tmp_path):
    """30.0 is stated to one decimal (spec), so it vouches for 29.96 but not for 29.6; 30 vouches for 29.6."""
    assert _line_check(tmp_path, "trades at 29.96x", 30.0) == []
    assert _line_check(tmp_path, "trades at 29.6x", 30.0)
    assert _line_check(tmp_path, "trades at 29.6x", 30) == []
    assert anchors._decimals(30.0) == 1 and anchors._decimals(81.8) == 1 and anchors._decimals(34) == 0


def test_research_path_cannot_leave_the_ticker_folder(tmp_path):
    """Research anchors cite the ticker's own reports; an absolute path or ../ would let any file vouch for a number."""
    (tmp_path / "T").mkdir()
    (tmp_path / "outside.md").write_text("Margin of 25%.\n")
    p = copy.deepcopy(OK)
    p["inputs"] = {"risk_metric.pe": dict(OK["inputs"]["risk_metric.pe"], anchor="../outside.md:1", anchor_value=0.25)}
    p["tree"], p["normalization"] = [], None
    assert any("outside" in x for x in anchors.check(p, "unused.xlsx", str(tmp_path / "T"), CTX))
    p["inputs"]["risk_metric.pe"]["anchor"] = f"{tmp_path / 'outside.md'}:1"
    assert any("absolute" in x for x in anchors.check(p, "unused.xlsx", str(tmp_path / "T"), CTX))


def test_ntm_anchor_checked_against_context_metrics(ctx):
    """An NTM sum sits in no cell; the anchor is checked against the sum context.json carries, same rounding rule."""
    m = ctx["metrics"]
    p = copy.deepcopy(OK)
    p["inputs"] = {"risk_metric.pe": dict(OK["inputs"]["risk_metric.pe"])}
    p["tree"], p["normalization"] = [], None
    assert p["inputs"]["risk_metric.pe"]["anchor"] == "ntm:eps"
    assert p["inputs"]["risk_metric.pe"]["anchor_value"] == m["eps"]["ntm"]["value"]
    assert anchors.check(p, "unused.xlsx", "unused", ctx) == []
    p["inputs"]["risk_metric.pe"].update(anchor="ntm1:ebitda", anchor_value=round(m["ebitda"]["ntm1"]["value"], 1))
    assert anchors.check(p, "unused.xlsx", "unused", ctx) == []
    p["inputs"]["risk_metric.pe"].update(anchor="y3:rev", anchor_value=round(m["rev"]["y3"]["value"], 1) + 0.2)
    assert any("y3:rev" in x for x in anchors.check(p, "unused.xlsx", "unused", ctx))
    p["inputs"]["risk_metric.pe"].update(anchor="ntm:eps", anchor_value=m["eps"]["ntm"]["value"])
    assert any("metrics" in x for x in anchors.check(p, "unused.xlsx", "unused", CTX))
