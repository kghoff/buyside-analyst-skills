"""A small synthetic ticker folder with a finished filings research, for street research tests."""
import json, os

SEMI = "2026-10-21 JPM flash note - Formulary Shifts Favor Libre; Modest 2027 US Headwind"
SELLSIDE = {
    "2026-10-29 JPM earnings recap - Good 3Q": "# JPM\n\n## Page 1\n\nWe see US growth of 14% and model 2027 gross margin of 63.5%. "
                                               "We believe pricing pressure persists as \"PBM rebates step up again in 2027\".\n",
    SEMI: "# JPM flash\n\n## Page 1\n\nThe formulary loss is less than 4% of US revenue, a modest 2027 headwind.\n",
    "2026-10-30 Morningstar company report - Smooth Sailing": "# MS\n\n## Page 1\n\n" + ("Moat narrative words here. " * 400),
}
GAPS_MD = """## 15 Gaps → street research list

### A. Questions the company documents could not answer

**Driver 1: active customer base (volume)**
1. **Quarterly customer base.** Only annual totals exist [DXCM 2025 10-K, Item 1].
2. **Gross adds and churn.** Retention was never quantified.

**Driver 2: revenue per customer**

3. **Price per sensor.** Never disclosed.
    - a sub-bullet that is not a gap

### B. Framework Part 4 methods, mapped

| Method | What | Gaps |
|---|---|---|
| Consensus | x | 39 |
"""
MOVES_MD = """## 12.1 The long view

Text.

## 12.2 The big moves around company events

| Event (release date) | What the company said | Close | SPY | Driver |
|---|---|---|---|---|
| CMS class (January 2017; exact day not in the company documents) | said | a | b | 1 |
| **Q2 2024 (2024-07-25)** | Guide cut | 96 → 64 | x | 2 |

| Release date | DXCM next day | SPY next day |
|---|---|---|
| 2024-07-25 | -33% | +1% |

## 12.3 Big moves with no company event

- **July to October 2023.** The close fell from 132.38 (2023-07-28) to 84.35 (2023-10-25).
- **Early 2020 (COVID).** The close fell hard.

> - **Not a row.** (2020-01-01) inside a callout
"""
P1_REPORT = ("## 10 Key drivers\n\nRevenue per customer fell 6.4% in 2025 to 1,480.0 per customer [Calc, drivers_math Price].\n\n"
             "The company said the base grew in the mid-to-upper teens and that pricing is stabilising in the US market "
             "according to the chief financial officer on the third quarter call this year.\n")


def make_src(root, sellside=SELLSIDE, phase1=True, extra_items=None, as_of="2026-10-29"):
    items = {}
    for label, text in sellside.items():
        rel = f"Sellside Research/_md/{label}.md"
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        items["sellside:" + label[:10] + label[-6:]] = {
            "category": "Sellside Research", "label": label, "status": "found", "date": label[:10],
            "firm": label.split()[1], "type": "report", "files": [f"Sellside Research/{label}.pdf", rel]}
    items["10-K:2025-12-31"] = {"category": "10-Ks", "label": "DXCM 2025 10-K", "status": "found",
                                "files": ["10-Ks/_md/DXCM 2025 10-K.md"]}
    for iid, it in (extra_items or {}).items():
        items[iid] = it
    with open(os.path.join(root, "_manifest.json"), "w") as f:
        json.dump({"ticker": "DXCM", "company": "DexCom, Inc.", "items": items}, f)
    k = os.path.join(root, "10-Ks", "_md", "DXCM 2025 10-K.md")
    os.makedirs(os.path.dirname(k), exist_ok=True)
    open(k, "w").write("# 10-K\n\nRevenue was $4,662.0 million in 2025.\n")
    if phase1:
        p1 = os.path.join(root, "Filings Research")
        sec = os.path.join(p1, "sections")
        os.makedirs(sec, exist_ok=True)
        open(os.path.join(sec, "00-cover.md"), "w").write(f"<div class=\"cover\">Filings research, as of {as_of} (Q3)</div>\n")
        open(os.path.join(sec, "01-executive-summary.md"), "w").write("## 01 Executive summary\n\nThree drivers.\n")
        open(os.path.join(sec, "10-key-drivers.md"), "w").write(P1_REPORT)
        open(os.path.join(sec, "12-stock-vs-drivers.md"), "w").write(MOVES_MD)
        open(os.path.join(sec, "15-gaps.md"), "w").write(GAPS_MD)
        open(os.path.join(sec, "16-appendix.md"), "w").write("## 16 Appendix\n")
        open(os.path.join(p1, "2026-11-08 DXCM Filings Research Report.md"), "w").write(P1_REPORT + "\n" + MOVES_MD + "\n" + GAPS_MD)
        w = os.path.join(p1, "_work")
        os.makedirs(w, exist_ok=True)
        json.dump([{"label": "DXCM 2025 10-K", "md": "10-Ks/_md/DXCM 2025 10-K.md"}], open(os.path.join(w, "inventory.json"), "w"))
        open(os.path.join(w, "series.csv"), "w").write("metric,period,value,unit,source\nRevenue,FY2025,4662.0,$M,\"Model, MOD!BP7\"\n")
        json.dump({"Price": {"rev_per_customer": [1480.0, -6.4]}}, open(os.path.join(w, "drivers_math.json"), "w"))
        open(os.path.join(w, "price.csv"), "w").write("date,close,spy\n2024-07-25,96.0,540.0\n2024-07-26,64.0,544.0\n")
    return root
