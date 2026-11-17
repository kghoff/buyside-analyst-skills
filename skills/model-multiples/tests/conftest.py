import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
FIX = os.path.join(HERE, "fixtures")
# The accepted DXCM model (copied from model-consensus's tests; MOD, Px Events, Px Data, forecast to 2030E).
# Never a live file.
REFERENCE = os.path.join(FIX, "reference_model.xlsx")
