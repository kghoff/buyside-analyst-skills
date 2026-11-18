"""The copies carry their keep-in-sync line; lo.py has its own profile (two skills running at once collided before);
the fixture has the tabs model-valuation needs."""
import os

import openpyxl

from conftest import SCRIPTS

COPIES = ("xlsx.py", "lo.py", "modmap.py", "notebox.py", "brief.py", "subject.py")


def test_copies_say_where_from():
    for f in COPIES:
        assert "Copied from model-multiples" in open(os.path.join(SCRIPTS, f)).read(), f


def test_own_lo_profile():
    import lo
    assert lo.PROFILE.endswith("model-valuation-lo-profile")


def test_fixture_has_dcf_and_multiples(fixture_model):
    names = openpyxl.load_workbook(fixture_model, read_only=True).sheetnames
    for t in ("MOD", "Px Data", "DCF", "Multiples"):
        assert t in names


def test_shared_values_really_were_recalculated(fixture_model, fixture_values):
    """The anchor and metric tests share one recalculated copy. A DCF formula the fixture build left without a cached
    value has a number only after a real recalculation; without this check, sharing could quietly mean
    "never recalculated" and every anchor test would read blanks."""
    formulas = openpyxl.load_workbook(fixture_model)["DCF"]
    cached = openpyxl.load_workbook(fixture_model, data_only=True)["DCF"]
    after = openpyxl.load_workbook(fixture_values, data_only=True)["DCF"]
    uncached = [c.coordinate for row in formulas.iter_rows() for c in row
                if isinstance(c.value, str) and c.value.startswith("=") and cached[c.coordinate].value is None]
    assert uncached, "the fixture's DCF tab already has cached values; this check needs another proof"
    filled = [x for x in uncached if after[x].value is not None]   # a few IFERROR(...,"") cells are blank by design
    assert len(filled) >= 0.9 * len(uncached), f"{len(filled)} of {len(uncached)} formulas have a value"
