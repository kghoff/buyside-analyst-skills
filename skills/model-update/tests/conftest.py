import os
import sys

import pytest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "scripts")
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, FIX)
import make_fixture  # noqa: E402


@pytest.fixture
def model(tmp_path):
    """A fresh TEST_model.xlsx (actuals through Q2 26; Q3 26E is the quarter being reported)."""
    return make_fixture.model(str(tmp_path / "TEST_model.xlsx"))


@pytest.fixture
def research(tmp_path):
    """<tmp>/research/TEST with the normal Q3 26 release Markdown."""
    return make_fixture.research(str(tmp_path / "research"))


@pytest.fixture
def grid():
    """MOD values of the fixture's actual columns (what a recalculation of the fixture returns there)."""
    return make_fixture.values()
