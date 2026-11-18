# skills/model-earnings-before/scripts/links.py
"""Links to the other tabs the preview reads, found by their labels: Multiples (P/E today and its 5-year min,
median, max and percentile), Consensus (the mean row: EPS and revenue for next quarter, this year and next year,
and the latest snapshot date) and Filings Charts (each 'Guidance vs actual' block's last 4 years)."""
from openpyxl.utils import column_index_from_string as ci, get_column_letter as L

import earnmath as em

MEAN_COLS = {"eps_q": "J", "eps_fy": "K", "eps_fy1": "L", "rev_q": "M", "rev_fy": "N", "rev_fy1": "O"}  # model-consensus BT
GUIDE = "Guidance vs actual: "


def col_a(g):
    return sorted((r, str(v).strip()) for (r, c), v in g.items() if c == 1 and isinstance(v, str))


def multiples(g):
    a = col_a(g)
    hdr = next((r for r, t in a if t == "Metric"), None)
    if hdr is None:
        return {}
    heads = {str(v).strip(): c for (r, c), v in g.items() if r == hdr and isinstance(v, str)}
    pe = next((r for r, t in a if r > hdr and t == "P/E"), None)
    out = {}
    for name, head in (("pe_today", "Today"), ("pe_min5", "5 years min"), ("pe_med5", "5 years median"),
                       ("pe_max5", "5 years max"), ("pe_pct", "5 years percentile")):
        c = heads.get(head)
        v = g.get((pe, c)) if pe and c else None
        if em._n(v):
            out[name] = {"ref": f"Multiples!${L(c)}${pe}", "value": v}
    return out


def consensus(g):
    out = {}
    row = next((r for (r, c), v in g.items() if c == 2 and isinstance(v, str) and v.strip() == "Consensus mean"), None)
    if row:
        for k, col in MEAN_COLS.items():
            v = g.get((row, ci(col)))
            if em._n(v):
                out[k] = {"ref": f"Consensus!${col}${row}", "value": v}
    top = next((r for r, t in col_a(g) if t.startswith("5. CONSENSUS SNAPSHOTS")), None)
    snaps = []
    if top:
        cs = next((c for (r, c), v in g.items() if r == top + 1 and v == "Snapshot"), None)
        r = top + 2
        while cs and g.get((r, cs)) is not None:
            snaps.append(str(g[(r, cs)])[:10])
            r += 1
    out["snapshot"] = max(snaps) if snaps else None
    return out


def guidance(g):
    blocks = []
    for (r, c), v in sorted(g.items()):
        if not (c == 2 and isinstance(v, str) and v.startswith(GUIDE)):
            continue
        hr = next((x for x in range(r + 1, r + 6) if g.get((x, 2)) == "Fiscal year"), None)
        if hr is None:
            continue
        heads = {str(x).strip(): cc for (rr, cc), x in g.items() if rr == hr and isinstance(x, str)}
        cv, cn = heads.get("vs first mid"), heads.get("Changes")
        if not cv:
            continue
        rows, k = [], hr + 1
        while g.get((k, 2)) not in (None, ""):
            rows.append({"year": str(g[(k, 2)]),
                         "vs_mid": {"ref": f"'Filings Charts'!${L(cv)}${k}", "value": g.get((k, cv))},
                         "changes": {"ref": f"'Filings Charts'!${L(cn)}${k}", "value": g.get((k, cn))} if cn else None})
            k += 1
        rows = rows[-4:]
        blocks.append({"title": v[len(GUIDE):], "rows": rows,
                       "habitual": em.flag_text(em.habitual([x["vs_mid"]["value"] for x in rows]))})
    return blocks[:3]
