"""Every anchored number in valuation_plan.json checked against the cell or research line it cites.

check(plan, values_path, research_root, context) returns plain-English problems; [] means every anchor holds.
- a cell (Sheet!$A$1): the recalculated model's value must match anchor_value, allowing the rounding anchor_value
  shows (a stated 81.8 matches 81.755); text must be equal.
- a research line (<path>.md:N, relative to <research_dir>/<TICKER>/): line N must print the number, as is, as a
  percent (x100 when followed by %) or in bps (x10,000 when the line says bps).
- house: the value must be chapter 11's default (context["house"]) unless a reason of >= 12 words says why not.
- judgment: not checked here (plan.py checks where it is allowed).

usage: anchors.py --plan P --values V --context C [--research-dir D]   (prints the problems; exit 1 if any)"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I

CELL = re.compile(r"^(?P<sheet>[A-Za-z' &]+)!\$?(?P<col>[A-Z]{1,3})\$?(?P<row>\d+)$")
LINE = re.compile(r"^(?P<path>.+\.md):(?P<n>\d+)$")
NUM = re.compile(r"-?\d+(?:\.\d+)?")
HOUSE_WHY_WORDS = 12


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _decimals(x):
    """Decimals x is stated to, e.g. 81.8 -> 1, 1502.4 -> 1, 34 -> 0 (float noise from scaling rounded away)."""
    s = repr(round(float(x), 9))
    return len(s.split(".")[1].rstrip("0")) if "." in s and "e" not in s else 0


def _close(seen, claimed, d=None):
    d = _decimals(claimed) if d is None else d
    return abs(seen - claimed) <= max(1e-6 * abs(seen), 0.5 * 10 ** -d)


def _walk(plan):
    """(name, anchored dict) for every anchored input: inputs, normalization fields, tree targets and probabilities."""
    for k, x in (plan.get("inputs") or {}).items():
        yield k, x
    for k, x in (plan.get("normalization") or {}).items():
        if isinstance(x, dict):
            yield f"normalization.{k}", x
    for i, t in enumerate(plan.get("tree") or []):
        nm = t.get("name", i)
        for f in ("target", "prob"):
            if isinstance(t.get(f), dict):
                yield f"tree[{nm}].{f}", t[f]


class _Cells:
    def __init__(self, values_path):
        self.path, self.wb = values_path, None

    def get(self, sheet, ref):
        if self.wb is None:
            import openpyxl
            self.wb = openpyxl.load_workbook(self.path, read_only=True, data_only=True)
        if sheet not in self.wb.sheetnames:
            raise KeyError(f"there is no {sheet!r} tab")
        return self.wb[sheet][ref].value


def _cell(name, a, m, claimed, cells):
    sheet = m["sheet"].strip("'")
    try:
        v = cells.get(sheet, f"{m['col']}{m['row']}")
    except KeyError as e:
        return f"{name}: {a}: {e.args[0]}"
    if _num(claimed) and _num(v):
        return None if _close(v, claimed) else f"{name}: {a} holds {v:g}, plan says {claimed:g}"
    if v == claimed or (isinstance(v, str) and isinstance(claimed, str) and v.strip() == claimed.strip()):
        return None
    return f"{name}: {a} holds {v!r}, plan says {claimed!r}"


def _line(name, a, m, claimed, root):
    path = os.path.join(root, m["path"])
    n = int(m["n"])
    if not os.path.isfile(path):
        return f"{name}: {a}: no such file under {root}"
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    if not 1 <= n <= len(lines):
        return f"{name}: {a}: the file has {len(lines)} lines"
    text = lines[n - 1]
    if not _num(claimed):
        return f"{name}: {a}: anchor_value must be a number, got {claimed!r}"
    flat = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    bps = "bps" in flat.lower()
    for mt in NUM.finditer(flat):
        p = float(mt.group())
        pct = flat[mt.end():].lstrip().startswith("%")
        tries = [claimed] + ([claimed * 100] if pct else []) + ([claimed * 10000] if bps else [])
        if any(_close(p, t) for t in tries):
            return None
    return f"{name}: {a} reads {text.strip()[:120]!r}, which does not print {claimed:g}"


def check(plan, values_path, research_root, context):
    """Plain-English problems with the plan's anchors; [] means every anchored number is where it says."""
    house = (context or {}).get("house") or {}
    cells, out = _Cells(values_path), []
    for name, x in _walk(plan):
        if not isinstance(x, dict) or "link" in x:
            continue
        a = x.get("anchor")
        if a == "judgment" or not isinstance(a, str):
            continue
        if a == "house":
            want = house.get(name)
            if x.get("value") != want and len(str(x.get("reason", "")).split()) < HOUSE_WHY_WORDS:
                out.append(f"{name}: chapter 11's default is {want!r}, plan says {x.get('value')!r}; a change "
                           f"needs a reason of at least {HOUSE_WHY_WORDS} words saying why")
            continue
        claimed = x.get("anchor_value")
        m = CELL.match(a)
        if m:
            p = _cell(name, a, m, claimed, cells)
        elif LINE.match(a):
            p = _line(name, a, LINE.match(a), claimed, research_root)
        else:
            p = f"{name}: anchor {a!r} is not a cell (Sheet!$A$1) or a research line (file.md:123)"
        if p:
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--values", required=True, help="the recalculated model (context.json 'values')")
    ap.add_argument("--context", required=True)
    ap.add_argument("--research-dir", help="default: settings research_dir")
    a = ap.parse_args(argv)
    ctx = json.load(open(a.context))
    rd = a.research_dir
    if not rd:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
        import settings
        rd = settings.research_dir()
    probs = check(json.load(open(a.plan)), a.values, os.path.join(rd, ctx["ticker"]), ctx)
    for p in probs:
        print(p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
