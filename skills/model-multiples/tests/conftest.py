import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
FIX = os.path.join(HERE, "fixtures")
# The accepted DXCM model (copied from model-consensus's tests; MOD, Px Events, Px Data, forecast to 2030E).
# Never a live file.
REFERENCE = os.path.join(FIX, "reference_model.xlsx")


def pytest_unconfigure(config):
    # A SWIG-built dependency prints "builtin type swigvarlink has no __module__ attribute" as Python shuts down,
    # after pytest's summary. run-tests.sh reports a suite's last output line, so that warning hid the pass count.
    import warnings
    warnings.filterwarnings("ignore", message="builtin type swigvarlink", category=DeprecationWarning)
