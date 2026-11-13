import glob
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
FIX = os.path.join(HERE, "fixtures")
# The accepted DXCM model (copied from model-industry's tests; has MOD and Px Data). Never a live file.
REFERENCE = os.path.join(FIX, "reference_model.xlsx")


def snap_path(t):
    """The one saved snapshot for ticker t (captured in Task 1)."""
    return sorted(glob.glob(os.path.join(FIX, t.lower(), "snapshots", "*.json")))[-1]


def snap(t):
    return json.load(open(snap_path(t)))
