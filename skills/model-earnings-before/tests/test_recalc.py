# skills/model-earnings-before/tests/test_recalc.py
"""The one LibreOffice test: the tab's formulas (and the Consensus cells), recalculated, give exactly what earnmath
says: the rule, the set-up side, every check, base rate and variance. If a formula and the Python drift apart, this
is where it shows."""
import pytest

import build
import verify


@pytest.mark.slow
def test_recalculated_tab_matches_earnmath(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out, variance="consensus")
    res = verify.run(out, work)
    assert res["problems"] == []
