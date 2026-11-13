import json
import os
import sys

import pandas as pd
import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
FIX = os.path.join(HERE, "fixtures", "dxcm")
# The user's golden reference model (DXCM, 8 Nov 2026, sha1 bb0d0ff8...), kept with the tests so they never depend on the
# handoff kit's folder. Override with PH_REFERENCE.
REFERENCE = os.environ.get("PH_REFERENCE", os.path.join(FIX, "reference_model.xlsx"))


@pytest.fixture(scope="session")
def ref_values():
    return json.load(open(os.path.join(FIX, "reference_values.json")))


@pytest.fixture(scope="session")
def reference_model():
    if not os.path.exists(REFERENCE):
        pytest.skip("golden reference model not found")
    return REFERENCE


@pytest.fixture(scope="session")
def dxcm_run(ref_values, reference_model):
    import engine
    import modmap
    mod = modmap.read(reference_model)
    ev = ref_values["events"]
    full = {p: pd.Timestamp(d) for p, d in zip(ev["periods"], ev["full_dates"])}
    events = [{"date": pd.Timestamp(d), "type": t, "name": nm, "timing": tm} for d, t, nm, tm, *_ in ev["list"]]
    prices = {k: engine.load_close(os.path.join(FIX, f"{t}_us_d.csv"))
              for k, t in (("stock", "dxcm"), ("spy", "spy"), ("etf", "xhe"), ("mom", "mtum"))}
    cfg = {"oi_role": "oi_ng", "ebitda_role": "ebitda_ng", "roic_role": "roic", "eps_role": "eps_ng",
           "ttm_key": "ttm_n", "fcf_role": "fcf", "bb_roles": ["buyback_net"]}
    return engine.run(cfg, prices, mod, full, events)
