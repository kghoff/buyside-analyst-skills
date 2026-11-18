"""The copied scripts say where they came from (so a fix upstream is carried here), and lo.py has its own
LibreOffice profile: two skills sharing one profile collide when they run at once (model-valuation NOTES)."""
import os

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def test_copies_name_their_source():
    for f in ("lo.py", "xlsx.py", "modmap.py", "notebox.py"):
        head = open(os.path.join(SCRIPTS, f)).read(400)
        assert "Copied from" in head, f


def test_lo_profile_is_this_skills_own():
    src = open(os.path.join(SCRIPTS, "lo.py")).read()
    assert '"model-short-lo-profile"' in src
    assert "model-valuation-lo-profile" not in src
