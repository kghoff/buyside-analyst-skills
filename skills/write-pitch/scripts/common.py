# skills/write-pitch/scripts/common.py
import json, pathlib

CORE_TYPES = ["title", "summary", "setup", "thesis", "risks", "why_now", "valuation", "different",
              "risk_reward", "catalysts"]                      # slides 1-10, in this order
SUPPORT_LAYOUTS = ["text_chart", "table", "quote", "two_column", "image"]
# characters allowed per text field (fits the template's boxes at its font sizes; tune in NOTES.md, not here twice)
BUDGET = {"title": 70, "takeaway": 160, "bullet": 170, "box": 420, "note": 1500, "quote": 400, "cell": 24}
SUM_BOXES = ["Thesis Summary", "Trading Plan", "Valuation Thoughts", "Buy price", "No-brainer price", "Mgmt contact"]
HURDLES = {"buy_rr": 2.0, "pound_rr": 3.0, "irr": 0.20}       # chapter 11 / 14 house defaults
CALLS = ["Long", "Short", "Watch"]

def load(p): return json.loads(pathlib.Path(p).read_text())
def save(p, obj): pathlib.Path(p).write_text(json.dumps(obj, indent=2))
