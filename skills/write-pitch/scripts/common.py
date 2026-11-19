# skills/write-pitch/scripts/common.py
import json, pathlib

CORE_TYPES = ["title", "summary", "setup", "thesis", "risks", "why_now", "valuation", "different",
              "risk_reward", "catalysts"]                      # slides 1-10, in this order
SUPPORT_LAYOUTS = ["text_chart", "table", "quote", "two_column", "image", "checklist"]
# characters allowed per text field (fits the template's boxes at its font sizes; tune in NOTES.md, not here twice)
BUDGET = {"title": 70, "takeaway": 160, "bullet": 170, "box": 420, "note": 1500, "quote": 400, "cell": 24, "row": 90}
SUM_BOXES = ["Thesis Summary", "Trading Plan", "Valuation Thoughts", "Buy price", "No-brainer price", "Mgmt contact"]
# chapter 11 / 14 house defaults, used only when the Valuation tab's own inputs (IRR hurdle, Buy at R/R,
# Table-pound at R/R) are missing; buy price = 3-yr target / (1+irr)^3, no-brainer = 3-yr target / (1+nobrainer_irr)^3
HURDLES = {"buy_rr": 2.0, "pound_rr": 3.0, "irr": 0.20, "nobrainer_irr": 0.30}
CALLS = ["Long", "Short", "Watch"]

def load(p): return json.loads(pathlib.Path(p).read_text())
def save(p, obj): pathlib.Path(p).write_text(json.dumps(obj, indent=2))

# the look of the deck (navy banker style); make_template.py draws the template from it and the builder imports it
THEME = {"navy": "0B2545", "band": "E8EEF6", "line": "C9D6E8", "good": "0A7D2C", "bad": "B3261E",
         "amber": "D07A00", "grey": "888888", "text": "1D1D1D", "strip": "F4F4F4", "font": "Arial"}
