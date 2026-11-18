"""(Copied from model-valuation, Nov 2026; keep _cell, _line and the number rules in sync. _walk and the quote check are model-short's.) Every anchored number and quote in short_plan.json checked against the cell or research line it cites.

check(plan, values_path, research_root, context) returns plain-English problems; [] means every anchor holds.
- a cell (Sheet!$A$1): the recalculated model's value must match anchor_value, allowing the rounding anchor_value
  shows (a stated 81.8 matches 81.755; decimals are counted as written, so 30.0 matches 29.96 but not 29.6); text
  must be equal.
- a research line (<path>.md:N, relative to <research_dir>/<TICKER>/ and inside it): line N must print the number,
  as is, as a percent (x100 when followed by %) or in bps (x10,000 when the line says bps). "20-25%" prints 20% and
  25% (a hyphen between digits is a range); a number glued to letters before it (Q2, FY25, x2) is not a figure.
- house: the value must be the house default (context["house"]) unless a reason of >= 12 words says why not.
(model-valuation's ntm:<metric> forward-sum anchor is left out: plan.py allows only cell and line anchors here.)
- judgment: not checked here (plan.py checks where it is allowed).

usage: anchors.py --plan P --values V --context C [--research R | --research-dir D]   (prints the problems; exit 1 if any)"""
import argparse
import decimal
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I

CELL = re.compile(r"^(?P<sheet>[A-Za-z' &]+)!\$?(?P<col>[A-Z]{1,3})\$?(?P<row>\d+)$")
LINE = re.compile(r"^(?P<path>.+\.md):(?P<n>\d+)$")
# A figure: not glued to a letter, digit or point before it; "-" is a minus only when nothing alphanumeric precedes
# it; an optional "-25" / "–25" straight after is the top of a range, not a negative number.
NUM = re.compile(r"(?<![\w.])(?P<neg>-)?(?P<a>\d+(?:\.\d+)?)(?:[-–](?P<b>\d+(?:\.\d+)?))?")
HOUSE_WHY_WORDS = 12


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _decimals(x):
    """Decimals x is written to, from repr(x): 81.8 -> 1, 30.0 -> 1, 34 -> 0, 1e-05 -> 5."""
    return max(0, -decimal.Decimal(repr(x)).as_tuple().exponent)


def _close(seen, claimed, d=None):
    d = _decimals(claimed) if d is None else d
    return abs(seen - claimed) <= max(1e-6 * abs(seen), 0.5 * 10 ** -d)


def _walk(plan):
    """(name, anchored dict) for every anchored number: the inputs and any tick that carries an anchor_value."""
    for k, x in (plan.get("inputs") or {}).items():
        yield k, x
    for k, x in (plan.get("ticks") or {}).items():
        if isinstance(x, dict) and "anchor_value" in x:
            yield f"ticks.{k}", x


def _quotes(plan):
    """(name, anchor, quote) for every quoted line: ticks, smoke flags and the catalyst."""
    for k, x in (plan.get("ticks") or {}).items():
        if isinstance(x, dict) and x.get("quote"):
            yield f"ticks.{k}", x.get("anchor"), x["quote"]
    for i, s in enumerate(plan.get("smoke") or []):
        yield f"smoke[{i}]", s.get("anchor"), s.get("quote")
    c = plan.get("catalyst") or {}
    if c.get("quote"):
        yield "catalyst", c.get("anchor"), c["quote"]


def _quote(name, a, quote, root):
    m = LINE.match(str(a))
    if not m:
        return f"{name}: a quote needs a file.md:line anchor, got {a!r}"
    path = os.path.join(root, m["path"])
    if os.path.isabs(m["path"]) or not os.path.realpath(path).startswith(os.path.realpath(root) + os.sep):
        return f"{name}: {a}: cite a file inside {root}"
    if not os.path.isfile(path):
        return f"{name}: {a}: no such file under {root}"
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    n = int(m["n"])
    if not 1 <= n <= len(lines):
        return f"{name}: {a}: the file has {len(lines)} lines"
    flat = lambda s: " ".join(str(s).lower().split())   # noqa: E731
    return None if flat(quote) in flat(lines[n - 1]) else f"{name}: {a} reads {lines[n - 1].strip()[:120]!r}, not {quote!r}"


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
    if os.path.isabs(m["path"]):
        return f"{name}: {a}: an absolute path; cite the file relative to {root}"
    path = os.path.join(root, m["path"])
    base = os.path.realpath(root)
    if not os.path.realpath(path).startswith(base + os.sep):
        return f"{name}: {a}: resolves outside {root}; cite a file inside it"
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
    d = _decimals(claimed)
    for mt in NUM.finditer(flat):
        a_ = float(mt["a"])
        seen = [-a_ if mt["neg"] else a_] + ([float(mt["b"])] if mt["b"] else [])
        pct = flat[mt.end():].lstrip().startswith("%")
        tries = [(claimed, d)] + ([(claimed * 100, max(0, d - 2))] if pct else []) + \
            ([(claimed * 10000, max(0, d - 4))] if bps else [])
        if any(_close(p, t, td) for p in seen for t, td in tries):
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
                out.append(f"{name}: the house default is {want!r}, plan says {x.get('value')!r}; a change "
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
    for name, a, q in _quotes(plan):
        p = _quote(name, a, q, research_root)
        if p:
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--values", required=True, help="the recalculated model (context.json 'values')")
    ap.add_argument("--context", required=True)
    ap.add_argument("--research", help="the ticker's research folder (<research_dir>/<TICKER>); default: from settings")
    ap.add_argument("--research-dir", help="the parent research_dir, used with the ticker when --research is not given")
    a = ap.parse_args(argv)
    ctx = json.load(open(a.context))
    root = a.research
    if not root:
        rd = a.research_dir
        if not rd:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
            import settings
            rd = settings.research_dir()
        root = os.path.join(rd, ctx["ticker"])
    probs = check(json.load(open(a.plan)), a.values, root, ctx)
    print("\n".join(probs) if probs else "anchors OK")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
