"""The one LibreOffice check of a finished copy: every checked cell recalculates to aftermath's number, no cell in
bands 9-15 or on Call Notes shows an error, and Call Notes holds this quarter. This is where a formula and the
Python math drifting apart shows. With context reading a recalculated input (as the skill does), the band 1-2 cells
the fast build tests cannot check (no cached values) are checked here too."""
import pytest


@pytest.mark.slow
def test_recalculated_copy_matches_the_math(recalc_run):
    r = recalc_run["verify"]
    assert r["problems"] == [], r["problems"][:5]
    lay = recalc_run["layout"]
    for lab in ("Preview's upside move (band 2)", "Preview's downside move (band 2)",
                "Expected move (preview, band 1)"):
        assert lab not in lay["unchecked"], lab
        assert lay["refs"][lab].replace("$", "") in lay["expected"], lab
