# skills/write-pitch/tests/test_scaffold.py
import pathlib, sys
SK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "scripts"))

def test_common_tables():
    import common
    assert len(common.CORE_TYPES) == 10 and common.CORE_TYPES[0] == "title"
    assert set(common.SUM_BOXES) >= {"Thesis Summary", "Trading Plan", "Buy price"}

def test_agent_definition_has_no_web_or_shell():
    a = (SK.parents[1] / "agents" / "pitch-analyst.md").read_text()
    tools = [l for l in a.splitlines() if l.startswith("tools:")][0]
    assert "Bash" not in tools and "Web" not in tools
    assert "model: opus" in a
