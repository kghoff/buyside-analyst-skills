# skills/model-earnings-before/scripts/docs.py
"""Documents dated on or after the last print, from the /collect-documents manifest: the print's own release and
call (where the bar was set) and what management, the sell-side and the news said since (section 13.4's
intra-quarter scrub). Markdown copies only: Markdown is read before PDF."""
import json
import os
import re

QEND = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def doc_date(item_id, label):
    """(Copied from research-filings common.py, Nov 2026; keep in sync.) Best date for ordering: a YYYY-MM-DD in the
    label (release / filing / event date), else in the id (period end), else the quarter end of a 'YYYY Qn' label
    or 'YYYYQn' id."""
    for s in (label, item_id):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
    for s in (label, item_id):
        m = re.search(r"(\d{4}) ?Q([1-4])", s)
        if m:
            return f"{m.group(1)}-{QEND[int(m.group(2))]}"
    return None


def since(root, last):
    p = os.path.join(root, "_manifest.json")
    if not os.path.exists(p):
        return []
    out = []
    for iid, it in json.load(open(p)).get("items", {}).items():
        if it.get("status") != "found":
            continue
        d = it.get("date") or doc_date(iid, it.get("label", iid))
        if not d or d < last:
            continue
        md = next((f for f in it.get("files", []) if f.lower().endswith(".md")
                   and os.path.exists(os.path.join(root, f))), None)
        if md:
            out.append({"date": d, "label": it.get("label", iid), "category": it.get("category"), "md": md})
    return sorted(out, key=lambda x: (x["date"], x["label"]))
