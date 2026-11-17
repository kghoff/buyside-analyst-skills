"""Every number the agent starts from is printed where it says (CLAUDE.md: never type a number that isn't printed in
a source); rounding the way a reader would is allowed, a wrong cell or line is not."""
import copy
import json
import os

import anchors
import lo
from conftest import FIX

OK = json.load(open(os.path.join(FIX, "plan_example.json")))
CTX = {"ticker": "TEST", "house": {"hurdle": .2, "buy_rr": 2.0, "pound_rr": 3.0, "discount": .15,
                                   "horizon_months": 12, "position": "long", "mkt_rev": .05, "mkt_oi": .08, "mkt_eps": .12}}


def test_cells_and_rounding(fixture_model, tmp_path):
    v = lo.recalc(fixture_model, str(tmp_path))
    assert anchors.check(OK, v, str(tmp_path), CTX) == []
    p = copy.deepcopy(OK)
    p["inputs"]["reward_multiple.pe"]["anchor_value"] = 36.0
    assert any("Multiples!B7" in x for x in anchors.check(p, v, str(tmp_path), CTX))
    p["inputs"]["reward_multiple.pe"].update(anchor="Multiples!C7", anchor_value=81.8)   # cell holds 81.755
    assert anchors.check(p, v, str(tmp_path), CTX) == []


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


def test_house_and_tree(fixture_model, tmp_path):
    """A house input may leave chapter 11's default only with a real reason; tree targets are checked like inputs."""
    v = lo.recalc(fixture_model, str(tmp_path / "v"))
    p = copy.deepcopy(OK)
    p["inputs"]["hurdle"].update(value=0.25, reason="Higher.")
    assert any("hurdle" in x for x in anchors.check(p, v, str(tmp_path), CTX))
    p["inputs"]["hurdle"]["reason"] = ("A 25% hurdle because the filings show two dilutive deals in three years, "
                                       "so the cost of being wrong is higher than usual.")
    assert anchors.check(p, v, str(tmp_path), CTX) == []
    p = copy.deepcopy(OK)
    p["tree"][4]["target"]["anchor_value"] = 60.0                    # DCF!$C$40 holds 54.84
    assert any("DCF!$C$40" in x for x in anchors.check(p, v, str(tmp_path), CTX))


def test_missing_sheet_or_file_is_named(fixture_model, tmp_path):
    v = lo.recalc(fixture_model, str(tmp_path / "v"))
    p = copy.deepcopy(OK)
    p["inputs"]["reward_multiple.pe"]["anchor"] = "Nope!B7"
    p["inputs"]["risk_metric.pe"].update(anchor="Filings Research/missing.md:3")
    probs = anchors.check(p, v, str(tmp_path), CTX)
    assert any("Nope" in x for x in probs) and any("missing.md" in x for x in probs)
