"""This quarter's call transcript: find it under collect-documents' name, or file one the user supplies.

usage: python3 transcript.py find --root R --ticker T --quarter "Q4 26"            prints the relative path or exits 1
       python3 transcript.py ingest --root R --ticker T --quarter "Q4 26" --file F  files F as the transcript
(ingest never overwrites a transcript already in the folder; it does not touch the manifest, SKILL.md does that.)"""
import argparse
import os
import shutil
import sys


def name(ticker, quarter):
    q, yy = quarter.strip().rstrip("E").split()
    return f"{2000 + int(yy)} {q} {ticker} call"


def find(root, ticker, quarter):
    rel = f"Earnings Calls/_md/{name(ticker, quarter)}.md"
    return rel if os.path.isfile(os.path.join(root, rel)) else None


def ingest(root, ticker, quarter, src):
    rel = f"Earnings Calls/_md/{name(ticker, quarter)}.md"
    out = os.path.join(root, rel)
    if os.path.exists(out):
        raise SystemExit(f"{rel} already exists in the folder; it is kept. Delete it first if you want to replace it.")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if src.lower().endswith(".pdf"):
        import fitz
        with fitz.open(src) as doc:
            text = "\n\n".join(p.get_text() for p in doc)
        shutil.copy(src, os.path.join(root, "Earnings Calls", name(ticker, quarter) + ".pdf"))
    else:
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    return rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["find", "ingest"])
    ap.add_argument("--root", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--quarter", required=True)
    ap.add_argument("--file")
    a = ap.parse_args()
    if a.cmd == "ingest" and not a.file:
        sys.exit("ingest needs --file")
    got = find(a.root, a.ticker, a.quarter) if a.cmd == "find" else ingest(a.root, a.ticker, a.quarter, a.file)
    print(got or "")
    sys.exit(0 if got else 1)


if __name__ == "__main__":
    main()
