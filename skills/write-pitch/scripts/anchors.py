# skills/write-pitch/scripts/anchors.py
"""Truth check of the agent's pitch_plan.json: every number and quote is proved against the model and the research.

usage: python3 anchors.py --plan pitch_plan.json --values <recalculated model copy> --research <research root>
                          [--json out.json]
Prints one problem per line, each starting with its rule id ([A1] ... [A5], plan_schema.md section 12), or
"anchors OK"; exit 1 if any. --json writes [{"key" or "quote", "rule", "problem"}] for the skill's UNVERIFIED list.

The rounding rule: `shown` sets the tolerance. The shown number's last digit gives a half-unit (0.005 for "$72.40",
0.5 for "28x" or "$1,250", 0.0005 for "12.5%"); a "%" scales that to the fraction (0.005 / 100 for "+31%" ... i.e.
"+31%" allows 0.005 on 0.31). The cell (or calc result) must be within that of `value`, and `value` shown at that
precision must read as `shown` (value 72.4 with shown "$74.20" is a problem). Units m / bn / k are not scaled: `value`
is in the units `shown` prints, as plan_schema.md section 3 says."""
import argparse
import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I

CALC = re.compile(r"^\s*calc:\s*(?P<expr>.+?)\s*$", re.I)
CELL = re.compile(r"^\s*(?:'(?P<q>[^']+)'|(?P<u>[^!']+))!\$?(?P<col>[A-Z]{1,3})\$?(?P<row>\d+)\s*$")
LINE = re.compile(r"^\s*(?P<path>.+):(?P<n>\d+)\s*$")
SHOWN = re.compile(r"\d[\d,]*(?:\.\d+)?")
TOKEN = re.compile(r"\d+(?:\.\d+)?")
EPS = 1e-9
FUNCS = {"abs": abs, "min": min, "max": max}
BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
          ast.Div: lambda a, b: a / b}
MAX_POW = 100


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_shown(shown):
    """(number as printed, decimals, is_percent, is_negative, unit) of a shown string, or None if it has no number."""
    s = str(shown).strip()
    m = SHOWN.search(s)
    if not m:
        return None
    txt = m.group().replace(",", "")
    neg = s[:1] in "-−(" or s[:2] in ("$-", "($")
    pct = "%" in s
    unit = re.match(r"\s*(bn|m|k)\b", s[m.end():], re.I)
    return float(txt), len(txt.split(".")[1]) if "." in txt else 0, pct, neg, unit.group(1).lower() if unit else ""


def _tolerance(p):
    """Half-unit of the last shown digit, as a tolerance on `value` (a % is a fraction, so divide by 100)."""
    return 0.5 * 10 ** -p[1] / (100 if p[2] else 1)


def _consistent(value, shown):
    """None if `value` reads as `shown` at its precision, else the problem."""
    p = parse_shown(shown)
    if p is None:
        return f"shown {shown!r} has no number in it"
    if not _num(value):
        return f"value must be a number, got {value!r}"
    num, d, pct, neg, _ = p
    v = value * 100 if pct else value
    if abs(abs(v) - num) > 0.5 * 10 ** -d + EPS or (neg and num != 0 and v > 0) or (not neg and v < 0 and abs(v) > 0.5 * 10 ** -d):
        return f"value {value:g} does not read as shown {shown!r}"
    return None


def _norm_anchor(a):
    return re.sub(r"[\s$']", "", str(a)).lower()


def _inside(root, rel):
    """Real path of rel under root, or None if absolute or outside it."""
    if os.path.isabs(rel):
        return None
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, rel))
    return path if path.startswith(base + os.sep) else None


def _read_lines(root, rel, n):
    """(lines, problem): the file's lines, or why line n of rel cannot be read."""
    path = _inside(root, rel)
    if path is None:
        return None, f"{rel} is not a file inside the research folder; cite a path relative to it"
    if not os.path.isfile(path):
        return None, f"{rel}: no such file under the research folder"
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    if not 1 <= n <= len(lines):
        return None, f"{rel} has {len(lines)} lines, not {n}"
    return lines, None


class Cells:
    """Read-only access to the recalculated workbook's values."""

    def __init__(self, path):
        self.path, self.wb = path, None

    def get(self, sheet, ref):
        if self.wb is None:
            import openpyxl
            self.wb = openpyxl.load_workbook(self.path, read_only=True, data_only=True)
        names = {n.lower(): n for n in self.wb.sheetnames}
        if sheet not in self.wb.sheetnames and sheet.lower() not in names:
            raise KeyError(f"there is no {sheet!r} tab in the model")
        return self.wb[sheet if sheet in self.wb.sheetnames else names[sheet.lower()]][ref].value


def check_cell(m, value, shown, cells):
    """[A1] the recalculated cell equals value at the rounding shown implies."""
    sheet = (m["q"] or m["u"]).strip()
    ref = f"{m['col']}{m['row']}"
    try:
        seen = cells.get(sheet, ref)
    except KeyError as e:
        return e.args[0]
    if seen is None:
        return f"{sheet}!{ref} is empty"
    if not _num(seen):
        return f"{sheet}!{ref} holds {seen!r}, not a number"
    p = parse_shown(shown)
    if p and abs(seen - value) > _tolerance(p) + EPS:
        return f"{sheet}!{ref} holds {seen:g}, but value is {value:g} (shown {shown!r})"
    return None


def check_line(m, shown, root):
    """[A2] the shown number is printed on that line, as a whole number token."""
    n = int(m["n"])
    lines, bad = _read_lines(root, m["path"], n)
    if bad:
        return bad
    p = parse_shown(shown)
    if p is None:
        return None
    text = re.sub(r"(?<=\d),(?=\d{3})", "", lines[n - 1])
    if any(abs(float(t) - p[0]) < EPS for t in TOKEN.findall(text)):
        return None
    return f"{m['path']}:{n} reads {lines[n - 1].strip()[:120]!r}, which does not print {shown!r}"


def evaluate(expr, names):
    """Value of an arithmetic expression over names, by walking an allow-list of ast nodes. Raises ValueError."""
    try:
        tree = ast.parse(expr.replace("^", "**"), mode="eval")
    except SyntaxError:
        raise ValueError(f"cannot parse {expr!r}")

    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and _num(n.value):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in names:
                raise ValueError(f"unknown name {n.id!r}")
            return names[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = walk(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and type(n.op) in BINOPS:
            return BINOPS[type(n.op)](walk(n.left), walk(n.right))
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
            a, b = walk(n.left), walk(n.right)
            if abs(b) > MAX_POW:
                raise ValueError("exponent too large")
            r = a ** b
            if isinstance(r, complex):
                raise ValueError("result is not a real number")
            return r
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS
                and n.args and not n.keywords):
            return FUNCS[n.func.id](*[walk(a) for a in n.args])
        raise ValueError(f"{type(n).__name__} is not allowed; use names, numbers, + - * / ^ ( ), abs, min, max")

    try:
        return walk(tree)
    except ZeroDivisionError:
        raise ValueError("division by zero")
    except OverflowError:
        raise ValueError("number too large")


def _calc_cycles(numbers):
    """Keys on a calc cycle (a uses b uses a)."""
    deps = {}
    for k, x in numbers.items():
        m = CALC.match(str(x.get("anchor", ""))) if isinstance(x, dict) else None
        if m:
            try:
                deps[k] = {n.id for n in ast.walk(ast.parse(m["expr"].replace("^", "**"), mode="eval"))
                           if isinstance(n, ast.Name) and n.id in numbers and n.id not in FUNCS}
            except SyntaxError:
                deps[k] = set()
    bad = set()

    def reaches(start, k, seen):
        for d in deps.get(k, ()):
            if d == start:
                return True
            if d not in seen and d in deps:
                seen.add(d)
                if reaches(start, d, seen):
                    return True
        return False

    for k in deps:
        if reaches(k, k, set()):
            bad.add(k)
    return bad


def check(plan, values_path, research_root):
    """Problems as [(key or None, quote id or None, rule, problem)]."""
    out = []
    numbers = plan.get("numbers") or {}
    cells = Cells(values_path)
    values = {k: x["value"] for k, x in numbers.items() if isinstance(x, dict) and _num(x.get("value"))}
    cyc = _calc_cycles(numbers)
    for k, x in numbers.items():
        if not isinstance(x, dict):
            out.append((k, None, "A1", f"{k}: must be an object with value, shown and anchor"))
            continue
        a, v, shown = x.get("anchor"), x.get("value"), x.get("shown")
        cm, cell, ln = CALC.match(str(a)), CELL.match(str(a)), LINE.match(str(a))
        rule = "A3" if cm else "A1" if cell else "A2" if ln else "A1"
        bad = _consistent(v, shown)
        if not bad:
            if cm:
                if k in cyc:
                    bad = "calc anchor is part of a cycle (a key's calc uses a key that uses it); anchor one to a cell"
                else:
                    try:
                        r = evaluate(cm["expr"], {n: w for n, w in values.items() if n != k})
                        p = parse_shown(shown)
                        if abs(r - v) > _tolerance(p) + EPS:
                            bad = f"calc gives {r:g}, but value is {v:g} (shown {shown!r})"
                    except ValueError as e:
                        bad = f"calc: {e}"
            elif cell:
                bad = check_cell(cell, v, shown, cells)
            elif ln:
                bad = check_line(ln, shown, research_root)
            else:
                bad = f"anchor {a!r} is not Tab!Cell, file:line or calc: <expression>"
        if bad:
            out.append((k, None, rule, f"{k}: {bad}"))
    seen = {}
    for k, x in numbers.items():
        if isinstance(x, dict) and x.get("anchor"):
            first = seen.setdefault(_norm_anchor(x["anchor"]), k)
            if first != k and str(numbers[first].get("shown")) != str(x.get("shown")):
                out.append((k, None, "A5", f"{k}: same anchor as {first} but shown {x.get('shown')!r} vs "
                            f"{numbers[first].get('shown')!r}; show a repeated number the same way"))
    for q in plan.get("quotes") or []:
        bad = check_quote(q, research_root)
        if bad:
            out.append((None, q.get("id"), "A4", f"{q.get('id')}: {bad}"))
    return out


def _flat(s):
    """Whitespace-normalised, curly quotes and dashes made straight: Markdown conversion varies in both. Case stays."""
    s = str(s).translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-", 0x2212: "-",
                          0x00A0: " "})
    return " ".join(s.split())


def check_quote(q, root):
    """[A4] the quote text is verbatim on its line."""
    if not isinstance(q, dict) or not isinstance(q.get("line"), int):
        return "a quote needs id, text, file and an integer line"
    lines, bad = _read_lines(root, str(q.get("file")), q["line"])
    if bad:
        return bad
    if _flat(q.get("text", "")) in _flat(lines[q["line"] - 1]):
        return None
    return f"{q['file']}:{q['line']} reads {lines[q['line'] - 1].strip()[:120]!r}, not {q.get('text')!r}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--values", required=True)
    ap.add_argument("--research", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    found = check(plan, a.values, a.research)
    for _, _, rule, problem in found:
        print(f"[{rule}] {problem}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump([{**({"key": k} if k else {"quote": q}), "rule": r, "problem": p} for k, q, r, p in found], f,
                      indent=2)
    if not found:
        print("anchors OK")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
