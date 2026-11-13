"""Step 4 - cut the filtered documents into reader-sized stretches, by type and era.

usage: python3 slices.py --src <ticker folder> [--budget 400000]
Investor Events use a smaller cap (CATEGORY_BUDGET, 100 KB) so a full investor day gets its own reader.
A slice holds one document type in date order, up to --budget bytes of filtered text (~100k tokens), so a reader sees
that type's whole arc (how risk factors or guidance language changed) and no file is read twice.
Writes _work/slices.json: [{id, title, category, hash, files: [{label, read, md, pdf, bytes, sha}]}].
'read' is relative to the ticker folder: the filtered copy, or the original when there is none (a PDF-only deck)."""
import argparse, hashlib, os

from common import OUT, load, save, work_dir

BUDGET = 400_000
CATEGORY_BUDGET = {"Investor Events": 100_000}  # investor days are the densest documents: one reader each


def plan(docs, stats, budget=BUDGET):
    groups = []
    for cat in dict.fromkeys(d["category"] for d in docs):
        budget_c = min(budget, CATEGORY_BUDGET.get(cat, budget))
        cur, size = [], 0
        for d in (d for d in docs if d["category"] == cat):
            st = stats.get(d["label"])
            b = st["filtered_bytes"] if st else d["bytes"]
            if cur and size + b > budget_c:
                groups.append((cat, cur))
                cur, size = [], 0
            cur.append((d, b, st))
            size += b
        if cur:
            groups.append((cat, cur))
    out = []
    for i, (cat, items) in enumerate(groups, 1):
        years = [d["date"][:4] for d, _, _ in items if d["date"]]
        span = (years[0] if min(years) == max(years) else f"{min(years)}–{max(years)}") if years else ""
        files = [{"label": d["label"],
                  "read": os.path.join(OUT, "_work", st["filtered"]) if st else (d["md"] or d["pdf"]),
                  "md": d["md"], "pdf": d["pdf"], "bytes": b, "sha": d["sha"]} for d, b, st in items]
        h = hashlib.sha256("|".join(sorted(f["sha"] for f in files)).encode()).hexdigest()[:16]
        out.append({"id": f"s{i:02d}", "title": f"{cat} {span}".strip(), "category": cat, "hash": h, "files": files})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--budget", type=int, default=BUDGET)
    a = ap.parse_args()
    w = work_dir(a.src)
    sl = plan(load(os.path.join(w, "inventory.json")), load(os.path.join(w, "filter_stats.json"), {}), a.budget)
    save(os.path.join(w, "slices.json"), sl)
    for s in sl:
        print(f"{s['id']}  {s['title']:<32} {len(s['files']):>3} files  {sum(f['bytes'] for f in s['files']) / 1e3:>6.0f} KB")
