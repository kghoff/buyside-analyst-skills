"""Firm names and rating words, for any stock.

The same firm is spelled differently by each source: Yahoo ("JP Morgan"), Nasdaq (15-character truncations such as
"JP MORGAN SECUR"), report file names ("JPM"). match() maps any of them to one firm from firms.json, or None (never a
guess). Each firm has a type: bank / independent / specialist (the analysts the broker table holds; house default),
rating shop / quant (kept in a separate box). bucket() groups each firm's own rating words into Buy / Hold / Sell.

usage: python3 firms.py check --snapshot W/snapshots/<date>.json
prints the firm names and rating words not in firms.json (last 5 years of actions + Nasdaq's broker list); exit 1 if
any. The agent adds them to firms.json (proposing a type) and tells the user."""
import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "firms.json")
ANALYST = ("bank", "independent", "specialist")
MIN_PREFIX = 5          # Nasdaq truncates names at 15 characters: "barclays capita" is a prefix of "barclays capital"


def norm(s):
    s = (s or "").lower().replace("&", " and ").replace(".", "")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s)


class Firms:
    def __init__(self, path=DB):
        d = json.load(open(path))
        names = [f["name"] for f in d["firms"]]
        dup = {n for n in names if names.count(n) > 1}
        if dup:
            raise ValueError(f"duplicate firms in {path}: {sorted(dup)}")
        self.firms = d["firms"]
        self.alias = {}
        for f in self.firms:
            for a in [f["name"]] + f.get("aliases", []):
                self.alias[norm(a)] = f
        self.buckets = {b.capitalize(): {norm(w) for w in ws} for b, ws in d["buckets"].items()}

    def match(self, raw):
        k = norm(raw)
        if not k:
            return None
        if k in self.alias:
            return self.alias[k]
        hits = {f["name"]: f for a, f in self.alias.items()
                if (min(len(a), len(k)) >= MIN_PREFIX and a.startswith(k)) or k.startswith(a + " ")}
        return next(iter(hits.values())) if len(hits) == 1 else None

    def bucket(self, grade):
        g = norm(grade)
        return next((b for b, ws in self.buckets.items() if g in ws), None)


def check(snap, F):
    asof = date.fromisoformat(snap["asof"])
    recent = [h for h in snap["yahoo"]["history"] if h["epochGradeDate"][:10] >= (asof - timedelta(days=1827)).isoformat()]
    names = {h["firm"] for h in recent} | set((snap["nasdaq"].get("ratings") or {}).get("brokerNames") or [])
    grades = {g for h in recent for g in (h.get("toGrade"), h.get("fromGrade")) if g}
    return {"unknown_firms": sorted(n for n in names if F.match(n) is None),
            "unknown_grades": sorted(g for g in grades if F.bucket(g) is None)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args()
    out = check(json.load(open(a.snapshot)), Firms())
    print(json.dumps(out, indent=1))
    sys.exit(1 if out["unknown_firms"] or out["unknown_grades"] else 0)
