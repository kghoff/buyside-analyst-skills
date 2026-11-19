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


@pytest.fixture(scope="session")
def recalc_run(fixture_dirs, tmp_path_factory):
    """The suite's two LibreOffice starts, once per session: recalculate the fixture model (so context reads real
    values, as the skill does), then context, the example plan, build, and verify (the second recalculation).
    Returns {work, out, values_in, layout, verify}. Slow tests only; copy work before changing anything in it."""
    import json

    import build
    import context
    import lo
    import verify
    model = fixture_dirs[0]
    root = tmp_path_factory.mktemp("recalc")
    values_in = lo.recalc(model, str(root / "values_in"))
    w = root / "w"
    w.mkdir()
    (w / "yahoo_after.json").write_text(json.dumps(make_fixture.YAHOO))
    context.run(model, str(w), "TEST", values=values_in, research=fixture_dirs[2], today="2027-02-28")
    shutil.copy(os.path.join(HERE, "fixtures", "plan_example.json"), w / "after_plan.json")
    out = str(root / "out.xlsx")
    build.build(model, str(w), "TEST", out)
    res = verify.run(out, str(w))
    return {"work": str(w), "out": out, "values_in": values_in, "verify": res,
            "layout": json.load(open(w / "layout.json"))}
