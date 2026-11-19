# skills/write-pitch/tests/test_labels.py
import openpyxl

import labels


def book(tmp, val_rows, short_rows=None):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in (("Valuation", val_rows), ("Short Check", short_rows)):
        if rows is None:
            continue
        ws = wb.create_sheet(name)
        for i, (a, b) in enumerate(rows, 1):
            ws.cell(row=i, column=1, value=a)
            ws.cell(row=i, column=2, value=b)
    p = tmp / "v.xlsx"
    wb.save(p)
    return str(p)


# why: plan.py checks the call against these; reading the rule's short verdict when the agent made its own call (or
# the house hurdle when the user changed the tab's) would reject a sound plan or pass a wrong one
def test_reads_by_label(tmp_path):
    p = book(tmp_path, [("Price", 72.4), (labels.VAL_VERDICT, "Buy"), ("IRR hurdle", 0.15), ("Buy at R/R", 2.5),
                        ("Table-pound at R/R", 4)],
             [(labels.SHORT_RULE, "Watchlist"), (labels.SHORT_AGENT, "No short"), ("IRR hurdle", 0.3)])
    out = labels.read(p)
    assert (out["valuation_verdict"], out["short_verdict"]) == ("Buy", "No short")
    assert (out["irr_hurdle"], out["buy_rr"], out["pound_rr"]) == (0.15, 2.5, 4.0)   # Valuation's, not Short Check's
    assert out["notes"] == []


# why: the brief says an empty Valuation verdict is Hold and an empty agent short verdict falls back to the rule;
# every fallback is a judgment call the user must hear, so each one leaves a note
def test_fallbacks_noted(tmp_path):
    p = book(tmp_path, [(labels.VAL_VERDICT, None), ("IRR hurdle", 20)],
             [(labels.SHORT_RULE, "Watchlist"), (labels.SHORT_AGENT, None)])
    out = labels.read(p)
    assert out["valuation_verdict"] == "Hold" and out["short_verdict"] == "Watchlist"
    assert out["irr_hurdle"] == 0.2 and out["buy_rr"] is None and out["pound_rr"] is None
    assert len(out["notes"]) == 5
    assert labels.read(book(tmp_path, [(labels.VAL_VERDICT, "Sell")]))["short_verdict"] is None
