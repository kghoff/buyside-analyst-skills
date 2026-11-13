import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))

from mod_fixture import make_mod  # noqa: E402


@pytest.fixture
def mod_path(tmp_path):
    p = tmp_path / "TEST_model.xlsx"
    make_mod(str(p))
    return str(p)
