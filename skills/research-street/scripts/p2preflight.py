"""Step 0 - check that the street research can run, and plan the sell-side reader groups.

usage: python3 p2preflight.py --ticker T [--src DIR] [--as-of YYYY-MM-DD]
Prints JSON {status: ok|warn|stop, missing: [{what, fix}], newer_docs, sellside, groups, src, out}.
stop = no folder, no filings research report, a sell-side report without markdown, or a PDF in Sellside Research/ that
the manifest doesn't list yet. warn = company documents newer than the filings research's as-of date, or no sell-side reports (web only).
Writes <src>/Street Research/_work/run.json."""
import argparse, datetime, glob, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
import settings  # noqa: E402
from p2common import COMPANY_NEWS, SELLSIDE, doc_date, load, p1_dir, phase_dir, save, sellside_items, work_dir

GROUP_WORDS = 15000
GROUP_FILES = 4


def groups(items):
    out, cur, words = [], [], 0
    for it in items:
        if cur and (len(cur) >= GROUP_FILES or words + it["words"] > GROUP_WORDS):
            out.append(cur)
            cur, words = [], 0
        cur.append(it["label"])
        words += it["words"]
    if cur:
        out.append(cur)
    return [{"id": f"s{i + 1}", "labels": g} for i, g in enumerate(out)]


def phase1_as_of(sections):
    cover = os.path.join(sections, "00-cover.md")
    text = open(cover, encoding="utf-8").read() if os.path.exists(cover) else ""
    m = re.search(r"as of (\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else None


def run(ticker, src, as_of):
    if not os.path.isdir(src):
        return {"status": "stop", "missing": [{"what": f"folder {src}", "fix": f"Run /collect-documents {ticker} first."}]}
    reports = sorted(glob.glob(os.path.join(p1_dir(src), "*Filings Research Report.md")))
    sections = os.path.join(p1_dir(src), "sections")
    if not reports or not os.path.isdir(sections):
        return {"status": "stop", "missing": [{"what": "filings research report",
                                                "fix": f"Run /research-filings {ticker} first; research-street starts from it."}]}
    items, missing = sellside_items(src), []
    registered = {os.path.basename(it["pdf"]) for it in items if it["pdf"]}
    dropped = glob.glob(os.path.join(src, SELLSIDE, "*.pdf")) + glob.glob(os.path.join(src, SELLSIDE, "*", "*.pdf"))  # root or a tier folder
    new_pdfs = sorted(os.path.basename(p) for p in dropped if os.path.basename(p) not in registered)
    if new_pdfs:
        return {"status": "stop", "missing": [{"what": "sell-side PDFs not filed yet: " + ", ".join(new_pdfs),
                                                "fix": f"Run /collect-documents {ticker} to file and convert the new sell-side PDFs."}]}
    for it in items:
        path = os.path.join(src, it["md"]) if it["md"] else None
        if not path or not os.path.exists(path):
            missing.append({"what": f"Markdown copy of {it['label']}",
                            "fix": f"Run /collect-documents {ticker}; its step 4 converts the sell-side PDFs."})
        else:
            it["words"] = len(open(path, encoding="utf-8").read().split())
    if missing:
        return {"status": "stop", "missing": missing}
    p1_as_of = phase1_as_of(sections)
    m = load(os.path.join(src, "_manifest.json"), {}) or {}
    newer = sorted(it["label"] for iid, it in (m.get("items") or {}).items()
                   if it.get("category") in COMPANY_NEWS and it.get("status") == "found" and p1_as_of
                   and (doc_date(iid, it["label"]) or "") > p1_as_of)
    run_json = {"ticker": ticker, "src": src, "as_of": as_of, "phase1_report": reports[-1],
                "phase1_sections": sections, "phase1_as_of": p1_as_of, "sellside": items,
                "groups": groups(items), "newer_docs": newer}
    save(os.path.join(work_dir(src), "run.json"), run_json)
    return {"status": "warn" if newer or not items else "ok", "missing": [], "newer_docs": newer,
            "sellside": len(items), "groups": len(run_json["groups"]), "src": src, "out": phase_dir(src)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--src")
    ap.add_argument("--as-of", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    src = a.src or os.path.join(settings.research_dir(), a.ticker.upper())
    print(json.dumps(run(a.ticker.upper(), src, a.as_of), indent=1))
