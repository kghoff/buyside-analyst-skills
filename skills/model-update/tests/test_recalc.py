"""The one slow test: the whole print-night path on the fixture with a LibreOffice recalculation."""
import json

import pytest

import actuals
import grid
import match
import modmap
import release
import tieout
import verify
import make_fixture as mf


@pytest.mark.slow
def test_print_night_end_to_end_ties_balances_and_leaves_the_rest_alone(model, tmp_path):
    """Release -> match -> actuals -> recalc -> tieout -> verify: the release ties, the sheet balances, no new error
    cells, the rest of the workbook is intact, and the forecast still runs off the actuals."""
    rel = release.parse_text(mf.release_md("combined"), "rel.md")   # two lines wait as placeholders
    res = match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E")
    res["leftover"] = []
    out, sp = str(tmp_path / "out.xlsx"), str(tmp_path / "state.json")
    actuals.build(model, "Q3 26E", res, out, sp, grid=mf.preprint())
    state = json.load(open(sp))
    g = grid.dump(out, str(tmp_path / "rc"))
    assert tieout.check(res, g["MOD"], "L", waiting=tieout.skip_refs(state)) == []
    # the fixture is made by openpyxl (no cached values): its recalculated original has no error cells, so {} is it
    assert verify.check(model, out, state, after_grid=g, before_grid={}) == []
    assert g["MOD"]["M4"] == pytest.approx(130 * 1.1)          # the forecast still runs off last year's actuals
    assert g["MOD"]["L4"] == 140.0 and g["MOD"]["L17"] == g["MOD"]["L20"]
