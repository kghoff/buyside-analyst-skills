# skills/write-pitch/scripts/anchors.py
"""Truth check of the agent's pitch_plan.json: every number and quote is proved against the model and the research.

usage: python3 anchors.py --plan pitch_plan.json --values <recalculated model copy> --research <research root>
                          [--json out.json]
Prints one problem per line, each starting with its rule id ([A1] ... [A5], plan_schema.md section 12), or
"anchors OK"; exit 1 if any. --json writes [{"key" or "quote", "rule", "problem"}] for the skill's UNVERIFIED list.

The rounding rule: `shown` sets the tolerance. The shown number's last digit gives a half-unit (0.5 for "28x" or
"$1,250", 0.005 for "$72.40"); a "%" makes `value` a fraction, so the half-unit is divided by 100 ("+31%" allows 0.005
on 0.31, "12.5%" allows 0.0005). The cell (or calc result) must be within that of `value`, and `value` shown at that
precision must read as `shown` (value 72.4 with shown "$74.20" is a problem). Negatives: a "-", an en dash, a minus
sign or a "(" before the number. A cell holding percentage points (31 for "31%") also passes, since the model
sometimes stores them that way. Units m / bn / k are not scaled: money is in the units the cell holds (plan_schema.md
section 3), so show "$1,250m" for a cell holding 1250 in millions; a cell that differs by x1000 / x1e6 gets a
units hint. A cell empty in the values copy but holding a formula in the model means the copy is not recalculated."""
import argparse
import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I

CALC = re.compile(r"^\s*calc:\s*(?P<expr>.+?)\s*$", re.I)
CELL = re.compile(r"^\s*(?:'(?P<q>[^']+)'|(?P<u>[^!']+))!\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)\s*$")
LINE = re.compile(r"^\s*(?P<path>.+):(?P<n>\d+)\s*$")
SHOWN = re.compile(r"\d[\d,]*(?:\.\d+)?")
# a whole number: not glued to a letter, digit or point before ("Q3" is not 3, "150" is not 15), nor followed by a
# digit, ".digit" or a letter other than a unit (x, m, mn, mm, k, b, bn, bp, bps, pct)
TOKEN = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\d|\.\d|(?!(?:x|m|mn|mm|k|b|bn|bp|bps|pct)\b)[A-Za-z])")
# what may follow a line's number for each unit a shown number carries (the line's equivalents of "%", "x", ...)
UNIT_AFTER = {"%": r"\s?(?:%|percent\b|per cent\b|pct\b)", "x": r"\s?(?:[xX\u00d7](?![A-Za-z])|times\b)",
              "bps": r"\s?(?:bps|bp|basis points?)\b", "m": r"\s?(?:m|mn|mm|million)\b",
              "bn": r"\s?(?:bn|b|billion)\b", "k": r"\s?(?:k|thousand)\b"}
DOLLAR_BEFORE = re.compile(r"(?:\$|US\$|USD)\s?[(\-\u2212\u2013]?\s?$")
# words that contradict a signed shown number when they sit just before it (3 words) or just after it (1 word)
DOWN_WORDS = re.compile(r"^(?:fell|fall|falls|falling|declin\w*|down|decreas\w*)$", re.I)
UP_WORDS = re.compile(r"^(?:rose|rise|rises|risen|rising|grew|grow|grows|growing|up|increas\w*)$", re.I)
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
    neg = any(c in s[:m.start()] for c in "-\u2212\u2013(")
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
    if pct and abs(value) >= 1 and abs(abs(value) - num) <= 0.5 * 10 ** -d + EPS:
        return (f"value {value:g} does not read as shown {shown!r}: % numbers are fractions in `value` "
                "(0.31 for 31%)")
    if abs(abs(v) - num) > 0.5 * 10 ** -d + EPS or (neg and num != 0 and v > 0) or (not neg and v < 0 and abs(v) > 0.5 * 10 ** -d):
        return f"value {value:g} does not read as shown {shown!r}"
    return None


def _norm_anchor(a):
    return re.sub(r"[\s$']", "", str(a)).lower()


def _inside(root, rel):
    """Real path of rel under root, or None if absolute or outside it."""
    if os.path.isabs(rel) or "\\" in rel:
        return None
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, rel))
    return path if path.startswith(base + os.sep) else None


def _read_lines(root, rel, n):
    """(lines, problem): the file's lines, or why line n of rel cannot be read."""
    path = _inside(root, rel)
    if path is None:
        return None, f"{rel} is not a file inside the research folder; cite a path relative to it, with forward slashes"
    if not os.path.isfile(path):
        return None, f"{rel}: no such file under the research folder"
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    if not 1 <= n <= len(lines):
        return None, f"{rel} has {len(lines)} lines, not {n}"
    return lines, None


class Cells:
    """Read-only access to the recalculated workbook's values; each sheet is read once, in one pass."""

    def __init__(self, path):
        self.path, self.wbs, self.cache = path, {}, {}

    def _sheet(self, sheet, data_only):
        import openpyxl
        if data_only not in self.wbs:
            self.wbs[data_only] = openpyxl.load_workbook(self.path, read_only=True, data_only=data_only)
        wb = self.wbs[data_only]
        names = {n.lower(): n for n in wb.sheetnames}
        if sheet not in wb.sheetnames and sheet.lower() not in names:
            raise KeyError(f"there is no {sheet!r} tab in the model")
        real = sheet if sheet in wb.sheetnames else names[sheet.lower()]
        if (real, data_only) not in self.cache:
            self.cache[(real, data_only)] = {c.coordinate: c.value for row in wb[real].iter_rows() for c in row
                                             if c.value is not None}
        return self.cache[(real, data_only)]

    def get(self, sheet, ref):
        return self._sheet(sheet, True).get(ref)

    def has_formula(self, sheet, ref):
        v = self._sheet(sheet, False).get(ref)
        return isinstance(v, str) and v.startswith("=")


def check_cell(m, value, shown, cells):
    """[A1] the recalculated cell equals value at the rounding shown implies."""
    sheet = (m["q"] or m["u"]).strip()
    ref = f"{m['col'].upper()}{m['row']}"
    try:
        seen = cells.get(sheet, ref)
        if seen is None and cells.has_formula(sheet, ref):
            return f"{sheet}!{ref} holds a formula but no value: the values copy may not be recalculated"
    except KeyError as e:
        return e.args[0]
    if seen is None:
        return f"{sheet}!{ref} is empty"
    if not _num(seen):
        return f"{sheet}!{ref} holds {seen!r}, not a number"
    p = parse_shown(shown)
    if not p:
        return None
    tol = _tolerance(p) + EPS
    if abs(seen - value) <= tol:
        return None
    if p[2] and abs(seen - value * 100) <= tol * 100:
        return None        # the cell holds percentage points (31 for 31%)
    if p[4] and any(abs(seen * f - value) <= tol for f in (1e3, 1e-3, 1e6, 1e-6)):
        return (f"{sheet}!{ref} holds {seen:g}, the same figure in other units than shown {shown!r}; show it in "
                "the cell's units (e.g. '$1,250m')")
    return f"{sheet}!{ref} holds {seen:g}, but value is {value:g} (shown {shown!r})"


def _shown_units(shown):
    """The units a shown number carries, as UNIT_AFTER keys, plus "$" (needed only when no m / bn / k follows it)."""
    s = str(shown)
    num = SHOWN.search(s)
    after = s[num.end():]
    units = [u for u, pat in (("%", r"\s?%"), ("x", r"\s?[xX](?![A-Za-z])"), ("bps", r"\s?(?:bps|bp)\b"),
                              ("m", r"\s?(?:m|mn)\b"), ("bn", r"\s?bn\b"), ("k", r"\s?k\b"))
             if re.match(pat, after, re.I)]
    if "$" in s and not set(units) & {"m", "bn", "k"}:
        units.append("$")
    return units


def _printed_negative(text, start, end):
    """The line prints this number negative: a minus glued before it, or "(" before and ")" after."""
    before = text[:start]
    if re.search(r"(?<![\w%)])[-\u2212\u2013]\s?\$?$", before) or re.search(r"\$\s?[-\u2212\u2013]$", before):
        return True
    return bool(re.search(r"\(\s?\$?$|\$\s?\($", before) and re.match(r"\s?\)", text[end:]))


def _line_match(text, tok, units, sign):
    """None if this number token on the line reads as the shown number (its units next to it, no sign contradicted),
    else why not. sign: +1 shown with "+", -1 shown negative, 0 unsigned."""
    end = tok.end()
    for u in units:
        if u == "$":
            if not DOLLAR_BEFORE.search(text[:tok.start()]) and not re.match(r"\s?dollars\b", text[end:], re.I):
                return "no $ next to it"
            continue
        m = re.match(UNIT_AFTER[u], text[end:], re.I)
        if not m:
            return f"no {u} next to it"
        end += m.end()
    neg = _printed_negative(text, tok.start(), end)
    if sign == 0:
        return "it is printed negative" if neg else None
    words = re.findall(r"[A-Za-z]+", text[:tok.start()])[-3:] + re.findall(r"[A-Za-z]+", text[end:])[:1]
    if sign > 0 and (neg or any(DOWN_WORDS.match(w) for w in words)):
        return "the line says it went down"
    if sign < 0 and not neg and any(UP_WORDS.match(w) for w in words):
        return "the line says it went up"
    return None


def check_line(m, shown, root):
    """[A2] the shown number is printed on that line, as a whole number token, with the shown unit next to it (an
    equivalent form counts: "31 percent" for "31%", "$31 million" or "31 million" for "$31m", "25 basis points" for
    "25bps"). A shown "+" or negative must not be contradicted by the words around it ("+5%" fails on "fell 5%" or
    "(5%)"; "-5%" fails on "grew 5%"); an unsigned shown number passes any words but not a number printed negative."""
    n = int(m["n"])
    lines, bad = _read_lines(root, m["path"], n)
    if bad:
        return bad
    p = parse_shown(shown)
    if p is None:
        return None
    text = re.sub(r"(?<=\d),(?=\d{3})", "", lines[n - 1])
    s = str(shown)
    sign = -1 if p[3] else 1 if "+" in s[:SHOWN.search(s).start()] else 0
    units = _shown_units(s)
    why = None
    for tok in TOKEN.finditer(text):
        if abs(float(tok.group()) - p[0]) < EPS:
            why = _line_match(text, tok, units, sign)
            if why is None:
                return None
    reason = f" (the number is there, but {why})" if why else ""
    return f"{m['path']}:{n} reads {lines[n - 1].strip()[:120]!r}, which does not print {shown!r}{reason}"


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
            args = [walk(a) for a in n.args]
            if len(args) != 1 if n.func.id == "abs" else len(args) < 2:
                raise ValueError(f"{n.func.id}() takes {'one number' if n.func.id == 'abs' else 'two or more numbers'}")
            return FUNCS[n.func.id](*args)
        raise ValueError(f"{type(n).__name__} is not allowed; use names, numbers, + - * / ^ ( ), abs, min, max")

    try:
        return walk(tree)
    except ZeroDivisionError:
        raise ValueError("division by zero")
    except OverflowError:
        raise ValueError("number too large")


def _names(expr):
    """Names an expression uses (the allowed functions abs / min / max left out), in order; None if it does not parse."""
    try:
        tree = ast.parse(expr.replace("^", "**"), mode="eval")
    except SyntaxError:
        return None
    called = {id(n.func) for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS}
    return list(dict.fromkeys(n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in called))


def _calc_deps(numbers):
    """{calc key: [keys of numbers its expression uses]}."""
    deps = {}
    for k, x in numbers.items():
        m = CALC.match(str(x.get("anchor", ""))) if isinstance(x, dict) else None
        if m:
            deps[k] = [n for n in _names(m["expr"]) or [] if n in numbers]
    return deps


def _calc_order(numbers, deps):
    """Every key, the non-calc keys first, then each calc after the calcs it uses (so a failure flows forward)."""
    order = [k for k in numbers if k not in deps]
    seen = set(order)

    def visit(k):
        if k in seen:
            return
        seen.add(k)
        for d in deps.get(k, ()):
            visit(d)
        order.append(k)

    for k in deps:
        visit(k)
    return order


def _calc_cycles(numbers):
    """Keys on a calc cycle (a uses b uses a)."""
    deps = _calc_deps(numbers)
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
    deps = _calc_deps(numbers)
    failed = {}
    results = {}
    for k in _calc_order(numbers, deps):       # a calc after the keys it uses, so they are already judged
        x = numbers[k]
        if not isinstance(x, dict):
            failed[k] = "A1"
            results[k] = (k, None, "A1", f"{k}: must be an object with value, shown and anchor")
            continue
        a, v, shown = x.get("anchor"), x.get("value"), x.get("shown")
        cm, cell, ln = CALC.match(str(a)), CELL.match(str(a)), LINE.match(str(a))
        rule = "A3" if cm else "A1" if cell else "A2" if ln else "A1"
        bad = _consistent(v, shown)
        if not bad:
            if cm:
                if k in cyc:
                    bad = "calc anchor is part of a cycle (a key's calc uses a key that uses it); anchor one to a cell"
                elif _names(cm["expr"]) == []:
                    bad = ("calc uses only constants, which proves nothing; a calc must use at least one key from "
                           "numbers (constants only beside a key, e.g. target_3y/(1+irr_3y)^3)")
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
        if cm:      # a calc on a failed key is unproved too, even if its arithmetic holds
            dep_bad = [f"depends on {u}, which failed [{failed[u]}]" for u in deps.get(k, ()) if u in failed]
            bad = "; ".join(([bad] if bad else []) + dep_bad) or None
        if bad:
            failed[k] = rule
            results[k] = (k, None, rule, f"{k}: {bad}")
    out.extend(results[k] for k in numbers if k in results)
    seen = {}
    for k, x in numbers.items():
        if isinstance(x, dict) and x.get("anchor"):
            first = seen.setdefault(_norm_anchor(x["anchor"]), k)
            if first != k and str(numbers[first].get("shown")) != str(x.get("shown")):
                out.append((k, None, "A5", f"{k}: same anchor as {first} but shown {x.get('shown')!r} vs "
                            f"{numbers[first].get('shown')!r}; show a repeated number the same way"))
    for i, q in enumerate(plan.get("quotes") or []):
        qid = q.get("id") if isinstance(q, dict) and q.get("id") else f"quotes[{i}]"
        bad = check_quote(q, research_root)
        if bad:
            out.append((None, qid, "A4", f"{qid}: {bad}"))
    return out


def _flat(s):
    """Whitespace-normalised, curly quotes and dashes made straight: Markdown conversion varies in both. Case stays."""
    s = str(s).translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-", 0x2212: "-",
                          0x00A0: " "})
    return " ".join(s.split())


def check_quote(q, root):
    """[A4] the quote text is verbatim on its line."""
    if not isinstance(q, dict):
        return "a quote must be an object with id, text, file and line"
    if not isinstance(q.get("line"), int) or isinstance(q["line"], bool) or q["line"] < 1:
        return "a quote needs a line number of 1 or more"
    if not isinstance(q.get("text"), str) or not q["text"].strip():
        return "a quote needs its text"
    if not isinstance(q.get("file"), str):
        return "a quote needs its file"
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
