"""fetch.mjs helpers, run through node (no network)."""
import json
import os
import shutil
import subprocess

import pytest

FETCH = os.path.join(os.path.dirname(__file__), "..", "scripts", "fetch.mjs")
NODE = shutil.which("node")


def js(expr):
    code = f"import('{os.path.abspath(FETCH)}').then(m => console.log(JSON.stringify({expr})))"
    r = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_yahoo_symbol_dashes_share_classes_only():
    # Yahoo answers BRK.B with an empty object (no error) but knows BRK-B; foreign suffixes must stay dotted
    assert js("m.yahooSymbol('BRK.B')") == "BRK-B"
    assert js("m.yahooSymbol('BF.A')") == "BF-A"
    assert js("m.yahooSymbol('SAP.DE')") == "SAP.DE"
    assert js("m.yahooSymbol('7203.T')") == "7203.T"
    assert js("m.yahooSymbol('DXCM')") == "DXCM"


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_empty_yahoo_answer_is_detected():
    # nothing at all = a wrong ticker: fetch must stop rather than write an empty snapshot
    assert js("m.yahooEmpty({price: {value: null}, yahoo: {history: [], trend: []}})") is True
    assert js("m.yahooEmpty({price: {value: 81.5}, yahoo: {history: [], trend: []}})") is False
    assert js("m.yahooEmpty({price: {value: null}, yahoo: {history: [{}], trend: []}})") is False


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_importing_fetch_does_not_run_it():
    assert js("typeof m.fetchAll") == "function"
