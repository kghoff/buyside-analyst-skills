"""Map release lines to MOD rows by their prior-period values (spec 'Matching'); apply the agent's answers.

usage: python3 match.py match --release release_lines.json --model MODEL --values values.json --quarter "Q3 26E" --out match.json
       python3 match.py apply --match match.json --answers reader_answers.json --model MODEL --release-root DIR --out match.json
match.json: matched, combined, diffs, leftover, ambiguous, zero_skipped, new_lines, skipped."""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap      # noqa: E402
import release                 # noqa: E402

SECTIONS = {"is": ("INCOME STATEMENT",), "bs": ("BALANCE SHEET", "ASSETS", "LIABILITIES"),
            "cf": ("CASH FLOW",), "recon": ("NON-GAAP",), "other": ("KEY OPERATING",)}


def norm(s):
    s = re.sub(r"\(\d+\)", "", str(s).lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def sim(a, b):
    x, y = set(norm(a).split()), set(norm(b).split())
    return len(x & y) / len(x | y) if x | y else 0.0


def _section(key):
    return key.split(" | ")[0].upper()


def _rows(m, kind):
    rows = [(r, k) for r, k, _ in m.lines]
    pref = [(r, k) for r, k in rows if _section(k).startswith(SECTIONS[kind])]
    return pref, rows


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _priors(m, grid, row, q, kind, ytd):
    """[(basis label, model value)] this line's prior value may be compared with."""
    py = m.pyq(q)
    if kind == "cf" and ytd:
        qs = [p for p in m.quarters_of(m.fy_of(py)) if m.is_q(p)]
        qs = qs[:qs.index(py) + 1]
        vals = [_num(grid.get(f"{m.col(p)}{row}")) for p in qs]
        return [("YTD " + py, sum(vals))] if all(v is not None for v in vals) else []
    out = [(py, _num(grid.get(f"{m.col(py)}{row}")))]
    if kind == "bs":
        q4 = m.quarters_of(m.fy_of(py))[-1]
        out.append((q4, _num(grid.get(f"{m.col(q4)}{row}"))))
    return [(b, v) for b, v in out if v is not None]


def _cur(m, grid, row, q, line, kind, ytd):
    v = line["values"][0] * line["factor"]
    if kind == "cf" and ytd:
        qs = [p for p in m.quarters_of(m.fy_of(q)) if m.is_q(p)]
        before = [_num(grid.get(f"{m.col(p)}{row}")) for p in qs[:qs.index(q)]]
        if any(x is None for x in before):
            return None
        v -= sum(before)
    return v


def _entry(m, grid, q, line, row, by, basis, model_prior, ytd):
    key = next(k for r, k, _ in m.lines if r == row)
    return {"line": line["id"], "label": line["label"], "row": row, "key": key, "by": by, "basis": basis,
            "printed": line["values"][0], "prior": line["values"][1] * line["factor"], "model_prior": model_prior,
            "cur": _cur(m, grid, row, q, line, line["kind"], ytd), "ytd": ytd, "file": line["file"],
            "lineno": line["line"], "tol": release.tolerance(line), "factor": line["factor"]}


def match(rel, m, grid, q):
    res = {k: [] for k in ("matched", "combined", "diffs", "leftover", "ambiguous", "zero_skipped", "new_lines", "skipped")}
    claims, pending = {}, []
    for line in rel["lines"]:
        if len(line["values"]) < 2:
            continue
        kind, ytd = line["kind"], rel["tables"][line["table"]]["ytd"]
        prior, tol = line["values"][1] * line["factor"], release.tolerance(line)
        pref, every = _rows(m, kind)
        if prior == 0:
            exact = [r for r, k in pref if norm(k.split(" | ")[-1]) == norm(line["label"])]
            if len(exact) == 1:
                claims.setdefault(exact[0], []).append((line, "label", None, None, ytd))
            elif line["values"][0] == 0:
                res["zero_skipped"].append({"line": line["id"], "label": line["label"]})
            else:
                pending.append((line, ytd))
            continue
        hit = None
        for rows in (pref, every):
            cands = []
            for r, k in rows:
                for basis, v in _priors(m, grid, r, q, kind, ytd):
                    if v != 0 and abs(v - prior) <= tol:
                        cands.append((r, k, basis, v))
                        break
            if cands:
                hit = cands
                break
        if not hit:
            pending.append((line, ytd))
            continue
        if len(hit) > 1:
            scored = sorted(((sim(k.split(" | ")[-1], line["label"]), r, k, b, v) for r, k, b, v in hit), reverse=True)
            if scored[0][0] == 0 or scored[0][0] == scored[1][0]:
                res["ambiguous"].append({"line": line["id"], "label": line["label"], "rows": [r for r, *_ in hit]})
                continue
            hit = [scored[0][1:]]
        r, k, b, v = hit[0]
        claims.setdefault(r, []).append((line, "value", b, v, ytd))
    for r, cl in claims.items():
        if len(cl) > 1:
            for line, *_ in cl:
                res["ambiguous"].append({"line": line["id"], "label": line["label"], "rows": [r]})
            continue
        line, by, b, v, ytd = cl[0]
        res["matched"].append(_entry(m, grid, q, line, r, by, b, v, ytd))
    taken = {e["row"] for e in res["matched"]}
    for line, ytd in pending:
        pref, _ = _rows(m, line["kind"])
        exact = [r for r, k in pref if norm(k.split(" | ")[-1]) == norm(line["label"]) and r not in taken]
        if len(exact) == 1:
            ps = _priors(m, grid, exact[0], q, line["kind"], ytd)
            b, v = ps[0] if ps else (None, None)
            e = _entry(m, grid, q, line, exact[0], "recast", b, v, ytd)
            res["matched"].append(e)
            taken.add(exact[0])
            res["diffs"].append(_diff(m, e))
            continue
        comb = _combined(m, grid, q, line, ytd, pref, taken)
        if comb:
            res["combined"].append(comb)
            taken.update(comb["rows"])
            continue
        res["leftover"].append({"line": line["id"], "label": line["label"], "values": line["values"],
                                "kind": line["kind"], "file": line["file"], "lineno": line["line"],
                                "factor": line["factor"], "decimals": line["decimals"]})
    return res


def _diff(m, e):
    ref = None
    if e["basis"] and not e["basis"].startswith("YTD"):
        ref = f"{m.col(e['basis'])}{e['row']}"
    return {"ref": ref, "key": e["key"], "period": e["basis"], "model": e["model_prior"], "new": e["prior"],
            "label": e["label"], "file": e["file"], "lineno": e["lineno"]}


def _combined(m, grid, q, line, ytd, pref, taken):
    prior, tol = line["values"][1] * line["factor"], release.tolerance(line)
    order = [r for r, _ in pref]
    found = []
    for i in range(len(order)):
        for n in (2, 3, 4):
            run = order[i:i + n]
            if len(run) < n or any(r in taken for r in run) or len({_section(k) for r, k in pref if r in run}) > 1:
                continue
            if any(run[j + 1] - run[j] > 3 for j in range(n - 1)):
                continue                                  # adjacent lines only (analysis rows may sit between)
            for basis in {b for r in run for b, _ in _priors(m, grid, r, q, line["kind"], ytd)}:
                vals = [dict(_priors(m, grid, r, q, line["kind"], ytd)).get(basis) for r in run]
                if all(v is not None for v in vals) and abs(sum(vals) - prior) <= tol and run not in [f[0] for f in found]:
                    found.append((run, basis))
    if len(found) != 1:
        return None
    run, basis = found[0]
    return {"line": line["id"], "label": line["label"], "rows": run,
            "keys": [k for r, k in pref if r in run], "cur": line["values"][0] * line["factor"],
            "prior": prior, "basis": basis, "file": line["file"], "lineno": line["line"], "tol": release.tolerance(line)}


def check_anchor(answer, line_by_id, root):
    """The agent's anchor must be the line's own file:line, and that line must contain the printed number."""
    ln = line_by_id[answer["line"]]
    a = answer.get("anchor", "")
    if a != f"{ln['file']}:{ln['lineno']}":
        return f"{answer['line']}: anchor {a!r} is not the line's own ({ln['file']}:{ln['lineno']})"
    text = open(os.path.join(root, ln["file"]), encoding="utf-8").read().split("\n")[ln["lineno"] - 1]
    v = ln["values"][0]
    if f"{abs(v):,.{max(0, ln.get('decimals', 1))}f}" not in text and str(abs(v)) not in text:
        return f"{answer['line']}: {v} is not on {a}"
    return None


def apply_answers(res, answers, m, root):
    """answers: [{line, action: map|combined|new_line|skip, key?, keys?, anchor, reason}] for every leftover and
    ambiguous line. Returns (res, problems)."""
    open_ = {e["line"]: e for e in res["leftover"] + res["ambiguous"]}
    lines = {e["line"]: e for e in res["leftover"]}
    problems, seen = [], set()
    for a in answers:
        if a["line"] not in open_:
            problems.append(f"{a['line']}: not an open line")
            continue
        seen.add(a["line"])
        if a["line"] in lines:
            p = check_anchor(a, lines, root)
            if p:
                problems.append(p)
                continue
        if a["action"] == "map" and a.get("key") not in m.keys:
            problems.append(f"{a['line']}: no MOD row '{a.get('key')}'")
            continue
        if a["action"] == "combined" and any(k not in m.keys for k in a.get("keys", [])):
            problems.append(f"{a['line']}: a combined key is not a MOD row")
            continue
        if not a.get("reason"):
            problems.append(f"{a['line']}: no reason")
    for lid in open_:
        if lid not in seen:
            problems.append(f"{lid}: not answered")
    if problems:
        return res, problems
    for a in answers:
        e = open_[a["line"]]
        if a["action"] == "map":
            row = m.row(a["key"])
            if "factor" not in e:
                problems.append(f"{a['line']}: an ambiguous line can't be mapped by the agent; answer skip and tell the user")
                continue
            res["matched"].append({"line": e["line"], "label": e["label"], "row": row, "key": a["key"], "by": "agent",
                                   "reason": a["reason"], "cur": e["values"][0] * e["factor"], "printed": e["values"][0],
                                   "file": e["file"], "lineno": e["lineno"], "ytd": False, "basis": None,
                                   "prior": None, "model_prior": None, "tol": release.tolerance(e), "factor": e["factor"]})
        elif a["action"] == "combined" and "factor" in e:
            res["combined"].append({"line": e["line"], "label": e["label"], "rows": [m.row(k) for k in a["keys"]],
                                    "keys": a["keys"], "cur": e["values"][0] * e["factor"], "by": "agent",
                                    "file": e["file"], "lineno": e["lineno"], "tol": release.tolerance(e)})
        elif a["action"] == "new_line":
            res["new_lines"].append({**e, "reason": a["reason"]})
        else:
            res["skipped"].append({**e, "reason": a["reason"]})
    if problems:
        return res, problems
    res["leftover"], res["ambiguous"] = [], []
    return res, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["match", "apply"])
    ap.add_argument("--release"), ap.add_argument("--model", required=True), ap.add_argument("--values")
    ap.add_argument("--quarter"), ap.add_argument("--match"), ap.add_argument("--answers")
    ap.add_argument("--release-root"), ap.add_argument("--out", required=True)
    a = ap.parse_args()
    m = ModMap(a.model)
    if a.cmd == "match":
        g = json.load(open(a.values))["MOD"]
        res = match(json.load(open(a.release)), m, g, a.quarter)
    else:
        res, problems = apply_answers(json.load(open(a.match)), json.load(open(a.answers)), m, a.release_root)
        if problems:
            print("\n".join(problems))
            sys.exit(1)
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: len(v) for k, v in res.items()}))


if __name__ == "__main__":
    main()
