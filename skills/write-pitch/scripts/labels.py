"""The verdicts and hurdles plan.py checks the call against, read by their row labels from the recalculated copy.

usage: python3 labels.py --values <recalculated copy>
Prints JSON {"valuation_verdict", "short_verdict", "irr_hurdle", "buy_rr", "pound_rr", "notes": [...]}: each key is
the plan.py flag of the same name (null = leave the flag out). Labels sit in column A, values in column B (as
model-valuation and model-short write them; model-summary links them the same way).
- Valuation "Overall verdict (the agent's call: Buy / Hold / Sell)"; empty = "Hold" (the brief's rule), with a note.
- Short Check "Verdict (agent's call)", else "Verdict (the rule)"; no Short Check tab = null.
- Valuation "IRR hurdle" (a fraction; 20 read as percentage points becomes 0.2), "Buy at R/R", "Table-pound at R/R";
  missing = null, so plan.py uses its house defaults, with a note.
"""
import argparse
import json

import openpyxl

VAL_VERDICT = "Overall verdict (the agent's call: Buy / Hold / Sell)"
SHORT_AGENT, SHORT_RULE = "Verdict (agent's call)", "Verdict (the rule)"
HURDLE_LABELS = {"irr_hurdle": "IRR hurdle", "buy_rr": "Buy at R/R", "pound_rr": "Table-pound at R/R"}


def by_label(ws):
    """{label in column A: value in column B}; the first row wins when a label repeats."""
    out = {}
    for a, b in ws.iter_rows(min_col=1, max_col=2, values_only=True):
        if isinstance(a, str) and a.strip() not in out:
            out[a.strip()] = b
    return out


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def read(values):
    wb = openpyxl.load_workbook(values, read_only=True, data_only=True)
    try:
        val = by_label(wb["Valuation"]) if "Valuation" in wb.sheetnames else {}
        short = by_label(wb["Short Check"]) if "Short Check" in wb.sheetnames else None
    finally:
        wb.close()
    out, notes = {}, []
    out["valuation_verdict"] = _text(val.get(VAL_VERDICT))
    if not out["valuation_verdict"]:
        out["valuation_verdict"] = "Hold"
        notes.append(f'Valuation "{VAL_VERDICT}" is empty: read as Hold')
    if short is None:
        out["short_verdict"] = None
        notes.append("no Short Check tab: no short verdict")
    else:
        out["short_verdict"] = _text(short.get(SHORT_AGENT)) or _text(short.get(SHORT_RULE))
        if not _text(short.get(SHORT_AGENT)):
            notes.append(f'Short Check "{SHORT_AGENT}" is empty: used "{SHORT_RULE}" ({out["short_verdict"]})')
    for key, lab in HURDLE_LABELS.items():
        v = val.get(lab)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            out[key] = None
            notes.append(f'Valuation "{lab}" not found or not a number: plan.py uses the house default')
            continue
        if key == "irr_hurdle" and v > 1:
            v = v / 100
            notes.append(f'Valuation "{lab}" held percentage points: read as {v:.0%}')
        out[key] = float(v)
    out["notes"] = notes
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--values", required=True)
    print(json.dumps(read(ap.parse_args(argv).values), indent=1))


if __name__ == "__main__":
    main()
