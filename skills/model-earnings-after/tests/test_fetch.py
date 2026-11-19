"""The Yahoo fetch only feeds the gap at the open and open-to-close; tests never touch the network, so this checks
the script parses and documents its failure path (the skill carries on with '?')."""
import os
import shutil
import subprocess

import pytest

F = os.path.join(os.path.dirname(__file__), "..", "scripts", "fetch_after.mjs")


@pytest.mark.skipif(not shutil.which("node"), reason="no node")
def test_parses():
    subprocess.run(["node", "--check", F], check=True)


def test_documents_failure_path():
    assert "exits 1" in open(F).read(800)
