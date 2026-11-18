import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "scripts")
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, FIX)
import make_fixture  # noqa: E402

RESEARCH = os.path.join(FIX, "research", "TEST")
FPLAN = os.path.join(FIX, "forecast_plan.json")
TODAY = "2026-11-18"


@pytest.fixture(scope="session")
def fixture_model(tmp_path_factory):
    """TEST_model.xlsx with model-consensus's empty variance skeleton, built once per session."""
    return make_fixture.build(str(tmp_path_factory.mktemp("fx") / "TEST_model.xlsx"))


@pytest.fixture(scope="session")
def work_base(fixture_model, tmp_path_factory):
    """W as the skill leaves it before the build: earnings.json, context.json/.md, rowmap.md, the example plan."""
    import context
    w = tmp_path_factory.mktemp("work") / "w"
    w.mkdir()
    (w / "earnings.json").write_text(json.dumps(make_fixture.EARN))
    context.run(fixture_model, str(w), "TEST", values=fixture_model, research=RESEARCH, forecast_plan=FPLAN,
                today=TODAY)
    shutil.copy(os.path.join(FIX, "plan_example.json"), w / "earnings_plan.json")
    return str(w)


@pytest.fixture
def work(work_base, tmp_path):
    dest = str(tmp_path / "w")
    shutil.copytree(work_base, dest)
    return dest


@pytest.fixture
def model(fixture_model, tmp_path):
    p = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(fixture_model, p)
    return p
