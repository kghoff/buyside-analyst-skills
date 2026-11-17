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


@pytest.fixture
def model(fixture_model, tmp_path):
    p = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(fixture_model, p)
    return p


def pytest_unconfigure(config):
    # Same as model-multiples: a SWIG warning at shutdown hid run-tests.sh's pass count.
    import warnings
    warnings.filterwarnings("ignore", message="builtin type swigvarlink", category=DeprecationWarning)
