import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
FIX = os.path.join(HERE, "fixtures")
REFERENCE = os.path.join(FIX, "reference_model.xlsx")   # copy of examples/DXCM/DXCM_model.xlsx (has a forecast); never a live file
DCF = os.path.abspath(os.path.join(HERE, "..", "..", "model-dcf", "scripts"))

# The Multiples stub: the rows model-valuation's agent and anchors read (labels as model-multiples writes them).
MULT_STUB = [
    ("A1", "TEST multiples: where the stock trades against its history, the market and its peers"),
    ("A5", "RANGES"), ("B5", "1 year"), ("C5", "5 years"), ("D5", "10 years"),
    ("A6", "P/E min"), ("B6", 26.2), ("C6", 26.2), ("D6", 20.1),
    ("A7", "P/E median"), ("B7", 34.1), ("C7", 81.755), ("D7", 70.2),
    ("A8", "P/E max"), ("B8", 52.3), ("C8", 344.6), ("D8", 344.6),
    ("A9", "EV/EBITDA median"), ("B9", 22.4), ("C9", 41.0), ("D9", 39.9),
    ("A40", "WEEKLY DATA"),
]


def _dcf_build(model):
    """Build model-dcf's DCF tab into `model` (in place: a test copy) through its own scripts, in its own process."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "import context, solve, build;"
        "m = sys.argv[2]; ctx = context.build(m);"
        "kept, formulas, kind, _ = build.read_inputs(m, ctx, None);"
        "s = solve.solve(ctx, kept, kind, as_of='2026-11-17', formulas=formulas);"
        "build.build(m, ctx, s, m + '.out.xlsx', m + '.written.json')"
    )
    subprocess.run([sys.executable, "-c", code, DCF, model], check=True)
    os.replace(model + ".out.xlsx", model)


@pytest.fixture(scope="session")
def fixture_model(tmp_path_factory):
    """reference model + DCF tab + Multiples stub, built once per session. Tests copy it before changing it."""
    import openpyxl
    d = tmp_path_factory.mktemp("fx")
    m = str(d / "TEST_model.xlsx")
    shutil.copy(REFERENCE, m)
    wb = openpyxl.load_workbook(m)
    ws = wb.create_sheet("Multiples")
    for ref, v in MULT_STUB:
        ws[ref] = v
    wb.save(m)
    _dcf_build(m)
    return m


@pytest.fixture(scope="session")
def fixture_values(fixture_model, tmp_path_factory):
    """fixture_model recalculated in LibreOffice once per session (read-only): the values the anchor and metric
    checks read. test_scaffold proves it really was recalculated."""
    import lo
    return lo.recalc(fixture_model, str(tmp_path_factory.mktemp("values")))


@pytest.fixture
def model(fixture_model, tmp_path):
    p = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(fixture_model, p)
    return p


@pytest.fixture(scope="session")
def work_base(fixture_model, tmp_path_factory):
    """W as the skill leaves it before the build (context.json, dcf_ctx.json, the example plan, a scenario result),
    made once per session: context.py recalculates the model twice in LibreOffice (about 12 s). Read-only; tests use
    `work`, their own copy."""
    import json
    w = tmp_path_factory.mktemp("work") / "w"
    w.mkdir()
    subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "context.py"), "--model", fixture_model, "--work",
                    str(w), "--ticker", "TEST", "--research-dir", str(w.parent / "none")], check=True)
    shutil.copy(os.path.join(FIX, "plan_example.json"), w / "valuation_plan.json")
    # scenario result for round 1 from the example plan's final cases
    plan = json.load(open(w / "valuation_plan.json"))
    t = {"round": 1, "final": True, "why": "x", "cases": {k: {"inputs": v["inputs"], "story": v["story"]}
                                                          for k, v in plan["scenarios"]["final"].items()}}
    (w / "scenarios_try_1.json").write_text(json.dumps(t))
    c = json.load(open(w / "context.json"))
    subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "scenario_eval.py"), "eval", "--dcf",
                    str(w / "dcf_ctx.json"), "--try", str(w / "scenarios_try_1.json"),
                    "--ntm-eps", str(c["metrics"]["eps"]["ntm"]["value"]),
                    "--ntm1-eps", str(c["metrics"]["eps"]["ntm1"]["value"]),
                    "--out", str(w / "scenarios_result_1.json")], check=True)
    return str(w)


def copy_work(base, dest):
    """Copy a work folder; paths inside its JSON files that point into `base` are pointed at `dest` instead, so a
    test that edits its copy never touches the shared one."""
    shutil.copytree(base, dest)
    for root, _, files in os.walk(dest):
        for f in files:
            if f.endswith(".json"):
                p = os.path.join(root, f)
                s = open(p).read()
                if base in s:
                    open(p, "w").write(s.replace(base, dest))
    return dest


@pytest.fixture
def work(work_base, tmp_path):
    return copy_work(work_base, str(tmp_path / "w"))


def pytest_unconfigure(config):
    # Same as model-multiples: a SWIG warning at shutdown hid run-tests.sh's pass count.
    import warnings
    warnings.filterwarnings("ignore", message="builtin type swigvarlink", category=DeprecationWarning)
