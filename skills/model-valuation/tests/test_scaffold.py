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
