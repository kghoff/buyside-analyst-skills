"""The forecast roll's guard and its approval page.

usage: python3 plandiff.py check --old forecast_plan.before.json --new forecast_plan.json --changes changes.json   (exit 1 + problems)
       python3 plandiff.py page --changes changes.json --old-head OLD.md --new-head NEW.md --guide "TEXT" --out approval.md"""
import argparse
import json
import sys

THESIS = ("none", "supports", "undercuts")


def _canon(x):
    return json.dumps(x, sort_keys=True)


def changed(old, new):
    out = []
    o = {e["key"]: _canon(e) for e in old.get("rows", [])}
    n = {e["key"]: _canon(e) for e in new.get("rows", [])}
    out += [k for k in list(o) + [k for k in n if k not in o] if o.get(k) != n.get(k)]
    for f in sorted(set(old) | set(new)):
        if f != "rows" and _canon(old.get(f)) != _canon(new.get(f)):
            out.append(f)
    return out


def check(old, new, changes):
    probs = []
    diff = changed(old, new)
    listed = [c["key"] for c in changes]
    probs += [f"{k} changed with no entry in changes.json" for k in diff if k not in listed]
    probs += [f"changes.json lists {k} but the plan did not change it" for k in listed if k not in diff]
    for c in changes:
        if c.get("thesis") not in THESIS:
            probs.append(f"{c['key']}: thesis must be none, supports or undercuts")
        for f in ("was", "now", "anchor", "reason"):
            if not c.get(f):
                probs.append(f"{c['key']}: no {f}")
    return probs


def page(changes, old_head, new_head, guide):
    order = sorted(changes, key=lambda c: c["thesis"] != "undercuts")
    L = ["# Forecast roll: what changes", "", "Changes that undercut a thesis point are bold and listed first.", "",
         "| Line | Was | Now | Thesis | Why (anchor) |", "|---|---|---|---|---|"]
    for c in order:
        k = f"**{c['key']}**" if c["thesis"] == "undercuts" else c["key"]
        L.append(f"| {k} | {c['was']} | {c['now']} | {c['thesis']} | {c['reason']} ({c['anchor']}) |")
    L += ["", "## Guidance the forecast must land inside", "", guide, "", "## Headlines before the roll", "", old_head,
          "", "## Headlines after the roll", "", new_head, ""]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "page"])
    for k in ("--old", "--new", "--changes", "--old-head", "--new-head", "--guide", "--out"):
        ap.add_argument(k)
    a = ap.parse_args()
    ch = json.load(open(a.changes))
    if a.cmd == "check":
        p = check(json.load(open(a.old)), json.load(open(a.new)), ch)
        print("\n".join(p) or "ok")
        sys.exit(1 if p else 0)
    open(a.out, "w").write(page(ch, open(a.old_head).read(), open(a.new_head).read(), a.guide))
    print(a.out)
