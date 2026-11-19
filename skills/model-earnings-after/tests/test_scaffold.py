# tests/test_scaffold.py
"""Copied scripts name their source so an upstream fix is carried here; lo.py has its own LibreOffice profile (two
skills sharing one collide when run at once); rates.py must not import model-earnings-before's earnmath (skills
stay separate)."""
import os

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def test_copies_name_their_source():
    for f in ("lo.py", "xlsx.py", "tabkit.py", "modmap.py", "notebox.py", "rates.py"):
        assert "Copied from" in open(os.path.join(SCRIPTS, f)).read(600), f


def test_lo_profile_is_this_skills_own():
    src = open(os.path.join(SCRIPTS, "lo.py")).read()
    assert '"model-earnings-after-lo-profile"' in src and "model-earnings-before-lo-profile" not in src


def test_rates_uses_aftermath():
    src = open(os.path.join(SCRIPTS, "rates.py")).read()
    assert "import aftermath as em" in src and "import earnmath" not in src
