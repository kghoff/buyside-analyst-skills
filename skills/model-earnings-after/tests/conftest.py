import os
import shutil
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(HERE, "fixtures"))
import make_fixture  # noqa: E402


@pytest.fixture(scope="session")
def fixture_dirs(tmp_path_factory):
    """(model path, model dir, research folder), built once per session by model-earnings-before's own scripts."""
    root = tmp_path_factory.mktemp("fx")
    md, rr = str(root / "models"), str(root / "research" / "TEST")
    return make_fixture.build(md, rr), md, rr


@pytest.fixture(scope="session")
def fixture_model(fixture_dirs):
    return fixture_dirs[0]


@pytest.fixture(scope="session")
def fixture_research(fixture_dirs):
    return fixture_dirs[2]


@pytest.fixture
def model(fixture_dirs, tmp_path):
    """A private copy of the model dir (model + _model_work) per test."""
    d = str(tmp_path / "models")
    shutil.copytree(fixture_dirs[1], d)
    return os.path.join(d, "TEST_model.xlsx")
