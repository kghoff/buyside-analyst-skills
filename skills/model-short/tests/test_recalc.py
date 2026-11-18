# skills/model-short/tests/test_recalc.py
"""The one LibreOffice test: the tab's formulas, recalculated, give exactly what shortmath says (verdict, wedge,
risk case, sizing, every tick). If a formula and the Python drift apart, this is where it shows."""
import pytest

import build
import verify


@pytest.mark.slow
def test_recalculated_tab_matches_shortmath(model, work, tmp_path):
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out, borrow=0.03)
    res = verify.run(out, work)
    assert res["problems"] == []
