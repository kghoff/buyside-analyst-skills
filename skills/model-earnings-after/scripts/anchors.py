"""(Copied from model-earnings-before, Nov 2026; keep _cell, _line and the number rules in sync. _walk, _quotes,
_quote's normalising and negation check, and the free-text number check are model-earnings-after's.) Every anchored
number and quote in after_plan.json checked against the research line it cites. Run it only on a plan that passed
plan.py (that is where shapes, enums and the call-documents-only rule are checked); a malformed plan still gets
problems here, never a crash.

check(plan, values_path, research_root, context, context_md="") returns plain-English problems; [] = every anchor holds.
- a research line (<path>.md:N, relative to <research_dir>/<TICKER>/ and inside it): line N must print the number,
  as is, as a percent (x100 when followed by %) or in bps (x10,000 when the line says bps). "20-25%" prints 20% and
  25% (a hyphen between digits is a range); a number glued to letters before it (Q2, FY25, x2) is not a figure.
  The long-term target's anchor_value and its year must both be printed on its line.
- a cell (Sheet!$A$1): the recalculated model's value must match anchor_value, allowing the rounding anchor_value
  shows; text must be equal. (No after-print field cites a cell today; kept in sync with the sibling.)
- a quote: at least 4 words, found on the cited line ignoring case, spacing, curly quotes and dash styles, and not
  straight after a negation (not / no / never / unlikely / ...n't within the 3 words before it): a quote that drops
  the "not" reverses the company's words.
- free text (every reason, the react fields, headline, quarter_thoughts): each figure must be printed in context.md
  or on the item's own cited line, as written (8% matches 8.0%; no x100 conversion); otherwise the agent made it up.

usage: anchors.py --plan P --context C [--values V] [--research R | --research-dir D]   (prints the problems; exit 1 if any)
(--values defaults to context.json "values"; the research root to context.json "research"; context.md is read from
beside context.json.)"""
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
    """(name, anchored dict) for every anchored number: the long-term target and its year."""
    lt = plan.get("lt_target")
    if isinstance(lt, dict):
        yield "lt_target", {"anchor": lt.get("anchor"), "anchor_value": lt.get("anchor_value")}
        yield "lt_target.year", {"anchor": lt.get("anchor"), "anchor_value": lt.get("year")}


def _items(plan, key):
    v = plan.get(key)
    return v if isinstance(v, dict) else {}


def _quotes(plan):
    """(name, anchor, quote) for every quoted line: SFOT, the call notes, guidance and the long-term target. An SFOT
    row anchored 'none' (the call was silent on it; plan.py checks the rule) has no quote to check."""
    for k, x in _items(plan, "sfot").items():
        if isinstance(x, dict) and x.get("anchor") != "none":
            yield f"sfot.{k}", x.get("anchor"), x.get("quote")
    for t, lst in _items(plan, "call_notes").items():
        for i, x in enumerate(lst if isinstance(lst, list) else []):
            if isinstance(x, dict):
                yield f"call_notes.{t}[{i}]", x.get("anchor"), x.get("quote")
    g = plan.get("guidance")
    for i, x in enumerate(g if isinstance(g, list) else []):
        if isinstance(x, dict):
            yield f"guidance[{i}]", x.get("anchor"), x.get("quote")
    lt = plan.get("lt_target")
    if isinstance(lt, dict):
        yield "lt_target", lt.get("anchor"), lt.get("quote")


QUOTE_WORDS = 4
NEGATION = re.compile(r"^(not|no|never|unlikely|cannot|.+n't)$")
_SUBS = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "}


def _flat(s):
    """Lower case, one space, straight quotes and apostrophes, plain hyphens: how a quote and its line compare."""
    s = str(s).lower()
    for a, b in _SUBS.items():
        s = s.replace(a, b)
    return " ".join(s.split())


def _read_line(name, a, root):
    """(line text, None) or (None, problem) for a file.md:N anchor inside root."""
    m = LINE.match(str(a))
    if not m:
        return None, f"{name}: a quote needs a file.md:line anchor, got {a!r}"
    path = os.path.join(root, m["path"])
    if os.path.isabs(m["path"]) or not os.path.realpath(path).startswith(os.path.realpath(root) + os.sep):
        return None, f"{name}: {a}: cite a file inside {root}"
    if not os.path.isfile(path):
        return None, f"{name}: {a}: no such file under {root}"
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    n = int(m["n"])
    if not 1 <= n <= len(lines):
        return None, f"{name}: {a}: the file has {len(lines)} lines"
    return lines[n - 1], None


def _quote(name, a, quote, root):
    if not isinstance(quote, str) or len(quote.split()) < QUOTE_WORDS:
        return f"{name}: the quote needs at least {QUOTE_WORDS} words, got {quote!r}"
    line, p = _read_line(name, a, root)
    if p:
        return p
    q, t = _flat(quote), _flat(line)
    at = [i for i in range(len(t)) if t.startswith(q, i)]
    if not at:
        return f"{name}: {a} reads {line.strip()[:120]!r}, not {quote!r}"
    if all(any(NEGATION.match(w.strip(".,;:!?\"'()")) for w in t[:i].split()[-3:]) for i in at):
        return f"{name}: {a}: the quote drops a negation: the line reads {line.strip()[:120]!r}"
    return None


FIG = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def _figures(text):
    return [float(x.replace(",", "")) for x in FIG.findall(str(text))]


def _printed(f, seen):
    """f (as written, its decimals giving the rounding: 8 matches 8.0, 7.5 does not match 7.6) is one of seen.
    No x100 here: context.md prints percents as percents, and a fraction path would let 9.9% match a 0.1%."""
    d = _decimals(f)
    return any(_close(abs(s), f, d) for s in seen)


def _free_text(plan):
    """(name, text, anchor or None) for every free-text field whose figures must come from a source."""
    for k, x in _items(plan, "sfot").items():
        if isinstance(x, dict):
            yield f"sfot.{k}.reason", x.get("reason"), x.get("anchor")
    yield "checkpoint.reason", _items(plan, "checkpoint").get("reason"), None
    for k in ("reason", "wrong_if", "watch"):
        yield f"react.{k}", _items(plan, "react").get(k), None
    yield "played_out.reason", _items(plan, "played_out").get("reason"), None
    for k in ("headline", "quarter_thoughts"):
        yield k, plan.get(k), None


def _numbers(plan, root, context_md):
    out, md = [], _figures(context_md or "")
    for name, text, a in _free_text(plan):
        if not isinstance(text, str):
            continue
        line = _read_line(name, a, root)[0] if a and LINE.match(str(a)) else None
        seen = md + (_figures(line) if line else [])
        for raw in FIG.findall(text):
            if not _printed(float(raw.replace(",", "")), seen):
                out.append(f"{name}: the number {raw} isn't in context.md or the quoted line; copy it from there")
    return out


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


def check(plan, values_path, research_root, context, context_md=""):
    """Plain-English problems with the plan's anchors; [] means every anchored number and quote is where it says.
    context_md is context.md's text, the only other place a figure in free text may come from."""
    if not isinstance(plan, dict):
        return [f"plan: must be a JSON object, got {type(plan).__name__}"]
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
    return out + _numbers(plan, research_root, context_md)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--values", help="the recalculated model; default: context.json 'values'")
    ap.add_argument("--context", required=True)
    ap.add_argument("--research", help="the ticker's research folder (<research_dir>/<TICKER>); default: from settings")
    ap.add_argument("--research-dir", help="the parent research_dir, used with the ticker when --research is not given")
    a = ap.parse_args(argv)
    ctx = json.load(open(a.context))
    root = a.research or ctx.get("research")
    if not root:
        rd = a.research_dir
        if not rd:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
            import settings
            rd = settings.research_dir()
        root = os.path.join(rd, ctx["ticker"])
    md = os.path.join(os.path.dirname(os.path.abspath(a.context)), "context.md")
    if not os.path.isfile(md):
        print(f"no context.md beside {a.context}: rerun context.py", file=sys.stderr)
        return 2
    probs = check(json.load(open(a.plan)), a.values or ctx.get("values"), root, ctx, open(md).read())
    print("\n".join(probs) if probs else "anchors OK")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
