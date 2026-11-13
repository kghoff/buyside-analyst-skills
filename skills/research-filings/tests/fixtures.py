"""Synthetic /collect-documents folders and MOD workbooks, small enough to reason about by hand."""
import json, os

import openpyxl


def make_src(root, docs, ticker="TEST"):
    """docs: (item_id, category, label, markdown text or None, status). Writes <category>/_md/<label>.md."""
    items = {}
    for item_id, cat, label, text, status in docs:
        files = []
        if text is not None:
            rel = f"{cat}/_md/{label}.md"
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            files.append(rel)
        items[item_id] = {"files": files, "category": cat, "label": label, "status": status}
    with open(os.path.join(root, "_manifest.json"), "w") as f:
        json.dump({"ticker": ticker, "company": "Test Co", "items": items}, f)
    return root


def make_model(path, px_rows=None):
    """MOD in model-historicals layout: periods in row 2 from column D, sections in A, labels in B, units in C."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    ws["A1"] = "TEST - Model"
    ws["A2"], ws["C2"] = "PROJECTIONS", "Units"
    for col, h in zip("DEFGHIJ", ["Q1 24", "Q2 24", "Q3 24", "Q4 24", 2024, None, "Q1 25E"]):
        ws[f"{col}2"] = h
    ws["A4"] = "INCOME STATEMENT"
    ws["B5"], ws["C5"] = "Revenue:", "$ M"
    ws["B6"] = "% yoy"
    ws["B7"], ws["C7"] = "(-) Cost of Sales", "$ M"
    ws["B8"], ws["C8"] = "Gross Profit", "$ M"
    ws["A10"] = "NON-GAAP METRICS"
    ws["B11"], ws["C11"] = "Gross Profit", "$ M"
    ws["B12"], ws["C12"] = "Gross Profit", "$ M"
    for col, rev, cogs in zip("DEFG", [100, 110, 120, 130], [-40, -44, -48, -52]):
        ws[f"{col}5"], ws[f"{col}7"] = rev, cogs
        ws[f"{col}6"] = 0.1
        ws[f"{col}8"] = f"={col}5+{col}7"
        ws[f"{col}11"] = f"={col}8"
        ws[f"{col}12"] = f"={col}8"
    ws["H5"], ws["H7"], ws["H8"] = "=SUM(D5:G5)", "=SUM(D7:G7)", "=H5+H7"
    ws["J5"] = 999
    ws["B3"], ws["C3"] = "Orders", "#"
    ws["D3"] = 7
    ws["B13"] = "% of Total Rev"
    ws["D13"] = 0.5
    ws["B14"] = "FCF conversion %"
    ws["D14"] = 0.9
    ws["B15"] = "Organic Revenue Growth"
    ws["D15"] = 0.05
    ws["A17"] = "KPIS"
    ws["B18"] = "Employee Count"
    ws["B19"], ws["D19"] = "United States", 10
    ws["B21"] = "Distributor"
    ws["B22"], ws["D22"] = "United States", 20
    if px_rows is not None:
        px = wb.create_sheet("Px Data")
        px["A1"] = "TEST and SPY daily closes"
        px.append([])
        px.append(["Date", "TEST close", "SPY close"])
        for row in px_rows:
            px.append(list(row))
    wb.save(path)
    return path
