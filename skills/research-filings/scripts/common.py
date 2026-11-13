"""Shared constants and helpers for /research-filings."""
import hashlib, json, os, re

# Everything the company itself released. The filings research reads these and nothing else.
COMPANY = ["10-Ks", "10-Qs", "Earnings Calls", "Press Releases", "Investor Decks", "Investor Events",
           "Segment Recasts", "Proxy Statements"]
EXCLUDED = {"Sellside Research", "Investor Letters"}   # outside voices: the street research, never the filings research
NO_FILES = {"_index"}                                  # manifest bookkeeping (8-K index rows), no documents
OUT = "Filings Research"
QEND = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def phase_dir(src):
    return os.path.join(src, OUT)


def work_dir(src):
    return os.path.join(src, OUT, "_work")


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def doc_date(item_id, label):
    """Best date for ordering: a YYYY-MM-DD in the label (release / filing / event date), else in the id (period
    end), else the quarter end of a 'YYYY Qn' label or 'YYYYQn' id."""
    for s in (label, item_id):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return m.group(1)
    for s in (label, item_id):
        m = re.search(r"(\d{4}) ?Q([1-4])", s)
        if m:
            return f"{m.group(1)}-{QEND[int(m.group(2))]}"
    return None
