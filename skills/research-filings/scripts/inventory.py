"""Step 2 - list every company document /collect-documents saved, and nothing else.

usage: python3 inventory.py --src <ticker folder>
Writes _work/inventory.json (one row per document) and _work/inventory.md (counts by type and year, PDF-only
documents, and anything not read with the reason). Sell-side research and investor letters are outside voices:
they never enter the filings research."""
import argparse, collections, os

from common import COMPANY, EXCLUDED, NO_FILES, doc_date, load, save, sha, work_dir

PDF_ONLY_BYTES = 40_000   # size estimate for slicing a document that has no markdown copy


def build(src):
    m = load(os.path.join(src, "_manifest.json"))
    if not m:
        raise SystemExit(f"no _manifest.json in {src}")
    docs, skipped, not_saved = [], [], []
    for item_id, it in m["items"].items():
        cat, label = it.get("category"), it.get("label", item_id)
        if cat in EXCLUDED or cat in NO_FILES:
            continue
        if cat not in COMPANY:
            skipped.append((label, f"unknown category {cat!r}"))
            continue
        if it.get("status") != "found":
            not_saved.append((label, it.get("status"), it.get("reason", "")))
            continue
        files = it.get("files", [])
        md = next((f for f in files if f.lower().endswith(".md") and os.path.exists(os.path.join(src, f))), None)
        pdf = next((f for f in files if f.lower().endswith(".pdf") and os.path.exists(os.path.join(src, f))), None)
        if not md and not pdf:
            skipped.append((label, "registered as found but no file on disk"))
            continue
        docs.append({"id": item_id, "category": cat, "label": label, "date": doc_date(item_id, label),
                     "md": md, "pdf": pdf,
                     "bytes": os.path.getsize(os.path.join(src, md)) if md else PDF_ONLY_BYTES,
                     "sha": sha(os.path.join(src, md or pdf))})
    dupes = [l for l, n in collections.Counter(d["label"] for d in docs).items() if n > 1]
    if dupes:
        raise SystemExit("duplicate document labels (citations need unique labels): " + "; ".join(dupes))
    docs.sort(key=lambda d: (COMPANY.index(d["category"]), d["date"] or "", d["label"]))
    return docs, skipped, not_saved


def summary(docs, skipped, not_saved):
    by = collections.defaultdict(collections.Counter)
    for d in docs:
        by[d["category"]][(d["date"] or "????")[:4]] += 1
    years = sorted({y for c in by.values() for y in c})
    lines = ["# Inventory", "", f"{len(docs)} company documents.", "",
             "| Type | " + " | ".join(years) + " | Total |", "|---|" + "---|" * (len(years) + 1)]
    for cat in COMPANY:
        if cat in by:
            lines.append(f"| {cat} | " + " | ".join(str(by[cat].get(y, "")) for y in years)
                         + f" | {sum(by[cat].values())} |")
    pdf_only = [d["label"] for d in docs if not d["md"]]
    if pdf_only:
        lines += ["", "PDF only (no markdown copy; the reader reads the PDF):", *[f"- {x}" for x in pdf_only]]
    if skipped:
        lines += ["", "Not read:", *[f"- {label}: {why}" for label, why in skipped]]
    if not_saved:
        lines += ["", "Registered but not saved (gaps in the company record):",
                  *[f"- {label}: {status} - {reason}" for label, status, reason in not_saved]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    src = ap.parse_args().src
    docs, skipped, not_saved = build(src)
    w = work_dir(src)
    save(os.path.join(w, "inventory.json"), docs)
    with open(os.path.join(w, "inventory.md"), "w", encoding="utf-8") as f:
        f.write(summary(docs, skipped, not_saved))
    print(f"{len(docs)} company documents; {len(skipped)} not read, {len(not_saved)} not saved (see inventory.md)")
