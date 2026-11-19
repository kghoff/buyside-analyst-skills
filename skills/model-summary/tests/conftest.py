import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(HERE, "fixtures"))
import make_fixture  # noqa: E402


@pytest.fixture(scope="session")
def fixture_model(tmp_path_factory):
    """TEST_model.xlsx, built once per session. Tests that change it copy it first."""
    return make_fixture.build(str(tmp_path_factory.mktemp("fx") / "TEST_model.xlsx"))


def no_fetch(work, ticker):
    raise AssertionError("Yahoo must not be called when the model already has the ADV")


@pytest.fixture(scope="session")
def built(fixture_model, tmp_path_factory):
    """One build of the fixture: (out path, report, work dir)."""
    import build
    work = str(tmp_path_factory.mktemp("work"))
    out = os.path.join(work, "out.xlsx")
    rep = build.build(fixture_model, work, "TEST", out, research_dir=str(tmp_path_factory.mktemp("rd")),
                      fetch=no_fetch)
    return out, rep, work
