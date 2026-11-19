"""Shared constants and helpers for /research-street. research-filings' scripts are reused by import, never copied."""
import csv, glob, os, sys

P1_SKILL = os.environ.get("RP1_SKILL") or os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "research-filings")
P1_SCRIPTS = os.path.join(P1_SKILL, "scripts")
if P1_SCRIPTS not in sys.path:
    sys.path.append(P1_SCRIPTS)

from common import doc_date, load, save  # noqa: E402,F401  (research-filings' helpers)

OUT = "Street Research"
P1_OUT = "Filings Research"
SELLSIDE = "Sellside Research"
COMPANY_NEWS = ("10-Ks", "10-Qs", "Earnings Calls", "Press Releases")
LEDGER_COLS = ["id", "topic", "claim", "phase1_cite", "phase1_section"]
TOPIC = r"^(driver\d|industry|plan|debate|turning|gap|other)$"
MARK_COLS = ["claim_id", "stance", "view", "reasoning", "holder", "holder_type", "tier", "date", "source"]
STANCES = ("agrees", "differs", "adds", "gap-closed")
HOLDER_TYPES = ("sell-side", "buy-side", "independent", "short-report", "press-quoted", "anonymous", "official", "press")
TIERS = ("primary", "secondary", "opinion")
FETCH_COLS = ["url", "fetched_on", "status", "title", "published"]
FETCH_STATUS = ("ok", "blocked", "failed")


def phase_dir(src):
    return os.path.join(src, OUT)


def work_dir(src):
    return os.path.join(src, OUT, "_work")


def p1_dir(src):
    return os.path.join(src, P1_OUT)


def p1_work(src):
    return os.path.join(src, P1_OUT, "_work")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def peer_items(src):
    """Peer documents fetched for agents (collect-documents' peer_docs.mjs writes peer_docs.json in the agent's folder):
    [{label, md, ticker, agents}], one per label, only those found or already on disk. Kept out of run.json, which
    preflight rewrites every run."""
    w, out = work_dir(src), {}
    paths = glob.glob(os.path.join(w, "readers", "*", "peer_docs.json")) + glob.glob(os.path.join(w, "research", "*", "peer_docs.json")) \
        + glob.glob(os.path.join(w, "synthesis", "peer_docs.json"))
    for p in sorted(paths):
        agent = os.path.basename(os.path.dirname(p))
        for d in load(p, []) or []:
            if d.get("status") in ("found", "local") and d.get("md") and os.path.exists(d["md"]):
                it = out.setdefault(d["label"], {"label": d["label"], "md": d["md"], "ticker": d.get("ticker", ""), "agents": []})
                if agent not in it["agents"]:
                    it["agents"].append(agent)
    return sorted(out.values(), key=lambda d: d["label"])


def sellside_items(src):
    """Registered sell-side reports: [{id, label, pdf, md, date, firm, type, tier}], sorted by date then label.
    tier: 1 broker research, 2 independent research, 3 independent analysis, 4 news and trade press (None if unfiled)."""
    m = load(os.path.join(src, "_manifest.json"), {}) or {}
    out = []
    for iid, it in (m.get("items") or {}).items():
        if it.get("category") != SELLSIDE or it.get("status") != "found":
            continue
        files = it.get("files", [])
        out.append({"id": iid, "label": it["label"],
                    "pdf": next((f for f in files if f.lower().endswith(".pdf")), None),
                    "md": next((f for f in files if f.endswith(".md")), None),
                    "date": it.get("date") or doc_date(iid, it["label"]),
                    "firm": it.get("firm", ""), "type": it.get("type", ""), "tier": it.get("tier")})
    return sorted(out, key=lambda d: (d["date"] or "", d["label"]))
