"""Map release lines to MOD rows by their prior-period values (spec 'Matching'); apply the agent's answers.

usage: python3 match.py match --release release_lines.json --model MODEL --values values.json --quarter "Q3 26E" --out match.json
       python3 match.py apply --match match.json --answers reader_answers.json --model MODEL --release-root DIR \
           --values values.json --quarter "Q3 26E" --out match.json
       (apply needs --values and --quarter too: an agent-mapped line gets the same sign, year-to-date and recast
       handling as a matched one)
match.json: matched, combined, diffs, leftover, ambiguous, zero_skipped, new_lines, skipped, no_layout (the table's
columns can't be told apart, e.g. segment columns: reported, never guessed), no_prior (fewer than two values).
Each matched entry has sign (-1 when the model keeps the line with the opposite sign: costs stored negative)."""
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
# A reconciliation or KPI line whose own section has no row may land in the other one of these two, never anywhere
# else: statement lines stay on their statement, and analysis sections (drivers, bridges, ROIC, leverage, free cash
# flow) hold ratios and derived numbers that can equal a printed value by chance.
FALLBACK = {"recon": ("KEY OPERATING",), "other": ("NON-GAAP",)}
BUCKETS = ("matched", "combined", "diffs", "leftover", "ambiguous", "zero_skipped", "new_lines", "skipped",
           "no_layout", "no_prior")


def norm(s):
    s = re.sub(r"\(\d+\)", "", str(s).lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def base(key):
    """'NON-GAAP METRICS | (+/-) Amortization of Intangibles #2' -> '(+/-) Amortization of Intangibles'."""
    return re.sub(r" #\d+$", "", key.split(" | ")[-1])


def sim(a, b):
    x, y = set(norm(a).split()), set(norm(b).split())
    return len(x & y) / len(x | y) if x | y else 0.0


def _section(key):
    return key.split(" | ")[0].upper()


def _rows(m, kind, sections=None):
    secs = SECTIONS[kind] if sections is None else sections
    return [(r, k) for r, k, _ in m.lines if _section(k).startswith(secs)]


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _cp(line):
    """(current, prior) as printed, by the table's period layout."""
    return line["values"][line["cur_i"]], line["values"][line["prior_i"]]


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


def _sign(model_prior, printed_prior, key):
    """-1 when the model keeps this line with the opposite sign to the release (costs stored negative)."""
    if model_prior and printed_prior:
        return -1 if (model_prior < 0) != (printed_prior < 0) else 1
    return -1 if base(key).startswith("(-)") else 1      # no prior to compare: the house '(-) ' rows are negative


def _cur(m, grid, rows, q, line, ytd, sign):
    """The value to type, in the model's units and sign; a year-to-date cash flow less MOD's earlier quarters."""
    v = _cp(line)[0] * line["factor"] * sign
    if line["kind"] == "cf" and ytd:
        qs = [p for p in m.quarters_of(m.fy_of(q)) if m.is_q(p)]
        before = [_num(grid.get(f"{m.col(p)}{r}")) for r in rows for p in qs[:qs.index(q)]]
        if any(x is None for x in before):
            return None
        v -= sum(before)
    return v


def _full_year(m, grid, q, line, row, ytd, sign):
    """(fy_cur, fy_prior, model's year-ago FY value) for a Q4 print: the full-year column the release prints
    ('Twelve Months Ended'), or a year-to-date cash flow (at Q4 it is the year). (None, None, None) otherwise."""
    if not q.startswith("Q4"):
        return None, None, None
    f = line["factor"]
    if line.get("fy_i") is not None:
        v = line["values"]
        cur, fy_prior = v[line["fy_i"]] * f * sign, v[line["fy_prior_i"]]
    elif line["kind"] == "cf" and ytd:
        cur, fy_prior = _cp(line)[0] * f * sign, None           # the YTD prior was already checked against MOD's year
    else:
        return None, None, None
    py = m.fy_of(m.pyq(q))
    return cur, (fy_prior * f * sign if fy_prior is not None else None), _num(grid.get(f"{m.col(py)}{row}"))


def _entry(m, grid, q, line, row, by, basis, model_prior, ytd, sign):
    key = next(k for r, k, _ in m.lines if r == row)
    cur, prior = _cp(line)
    fy_cur, fy_prior, fy_model = _full_year(m, grid, q, line, row, ytd, sign)
    e = {"line": line["id"], "label": line["label"], "row": row, "key": key, "by": by, "basis": basis,
         "printed": cur, "prior": prior * line["factor"] * sign, "model_prior": model_prior, "sign": sign,
         "cur": _cur(m, grid, [row], q, line, ytd, sign), "ytd": ytd, "kind": line["kind"], "file": line["file"],
         "lineno": line["line"], "tol": release.tolerance(line), "factor": line["factor"]}
    if fy_cur is not None:
        e["fy_cur"] = fy_cur
        if fy_prior is not None:
            e["fy_prior"], e["fy_model_prior"] = fy_prior, fy_model
    return e


def _open(line, ytd, **extra):
    """A leftover / ambiguous entry: everything the agent's answer needs to become a match."""
    return {"line": line["id"], "label": line["label"], "values": line["values"], "cur_i": line["cur_i"],
            "prior_i": line["prior_i"], "fy_i": line.get("fy_i"), "fy_prior_i": line.get("fy_prior_i"), "kind": line["kind"], "ytd": ytd, "file": line["file"],
            "lineno": line["line"], "factor": line["factor"], "decimals": line["decimals"], **extra}


def _hits(m, grid, q, line, ytd, rows):
    """[(row, key, basis, model prior, sign)] whose prior equals the line's: same sign first, else opposite."""
    prior, tol = _cp(line)[1] * line["factor"], release.tolerance(line)
    for sign in (1, -1):
        out = []
        for r, k in rows:
            for basis, v in _priors(m, grid, r, q, line["kind"], ytd):
                if v != 0 and abs(v - prior * sign) <= tol:
                    out.append((r, k, basis, v, sign))
                    break
        if out:
            return out
    return []


def match(rel, m, grid, q):
    res = {k: [] for k in BUCKETS}
    claims, pending, repeats = {}, [], {}
    for line in rel["lines"]:
        ytd = rel["tables"][line["table"]]["ytd"]
        if len(line["values"]) < 2:
            res["no_prior"].append(_open(line, ytd))
            continue
        if line.get("cur_i") is None:
            res["no_layout"].append(_open(line, ytd))
            continue
        kind = line["kind"]
        cur, prior = _cp(line)
        own = _rows(m, kind)
        if prior == 0:
            exact = [r for r, k in own if norm(base(k)) == norm(line["label"])]
            if len(exact) == 1:
                claims.setdefault(exact[0], []).append((line, "label", None, None, ytd, True, None))
            elif cur == 0:
                res["zero_skipped"].append({"line": line["id"], "label": line["label"]})
            else:
                pending.append((line, ytd))
            continue
        hit, in_own = _hits(m, grid, q, line, ytd, own), True
        if not hit and kind in FALLBACK:
            fb = [(r, k) for r, k in _rows(m, kind, FALLBACK[kind])]
            hit = [h for h in _hits(m, grid, q, line, ytd, fb) if sim(base(h[1]), line["label"]) > 0]
            in_own = False
        if not hit:
            pending.append((line, ytd))
            continue
        if len(hit) > 1:
            scored = sorted(hit, key=lambda h: -sim(base(h[1]), line["label"]))
            top = sim(base(scored[0][1]), line["label"])
            best = [h for h in scored if sim(base(h[1]), line["label"]) == top]
            if top > 0 and len(best) > 1 and len({base(h[1]) for h in best}) == 1 and len({h[3] for h in best}) == 1:
                # the same adjustment repeated per reconciliation block (MOD keys them #2, #3): paired in order below
                repeats.setdefault(tuple(sorted(h[0] for h in best)), []).append((line, best, ytd, in_own))
                continue
            if top == 0 or len(best) > 1:
                res["ambiguous"].append(_open(line, ytd, rows=[h[0] for h in hit]))
                continue
            hit = best
        r, k, b, v, sg = hit[0]
        claims.setdefault(r, []).append((line, "value", b, v, ytd, in_own, sg))
    for rows, group in repeats.items():
        curs = {_cp(line)[0] for line, *_ in group}
        if len(group) == len(rows) or len(curs) == 1:
            # k-th occurrence -> k-th row. With unequal counts only when every occurrence prints the same current
            # value, so whichever row an occurrence lands on gets the right number; extra occurrences go to the agent.
            for (line, best, ytd, in_own), r in zip(group, rows):
                h = next(h for h in best if h[0] == r)
                claims.setdefault(r, []).append((line, "value", h[2], h[3], ytd, in_own, h[4]))
            for line, best, ytd, _ in group[len(rows):]:
                res["ambiguous"].append(_open(line, ytd, rows=list(rows)))
        else:
            for line, best, ytd, _ in group:
                res["ambiguous"].append(_open(line, ytd, rows=list(rows)))
    for r, cl in claims.items():
        if len(cl) > 1 and any(c[5] for c in cl):
            for c in cl:
                if not c[5]:
                    pending.append((c[0], c[4]))          # a claim from the line's own section beats a fallback one
            cl = [c for c in cl if c[5]]
        if len(cl) > 1 and len({tuple(c[0]["values"]) for c in cl}) == 1 and len({c[6] for c in cl}) == 1:
            for line, *rest in cl[1:]:                    # the same line printed twice: the first one enters
                res["ambiguous"].append(_open(line, rest[3], rows=[r], duplicate_of=cl[0][0]["id"]))
            cl = cl[:1]
        if len(cl) > 1:
            for line, *rest in cl:
                res["ambiguous"].append(_open(line, rest[3], rows=[r]))
            continue
        line, by, b, v, ytd, _, sg = cl[0]
        key = next(k for rr, k, _ in m.lines if rr == r)
        sg = sg if sg is not None else _sign(None, None, key) if _cp(line)[0] > 0 else 1
        res["matched"].append(_entry(m, grid, q, line, r, by, b, v, ytd, sg))
    taken = {e["row"] for e in res["matched"]}
    for line, ytd in pending:
        own = _rows(m, line["kind"])
        exact = [(r, k) for r, k in own if norm(base(k)) == norm(line["label"]) and r not in taken]
        if len(exact) == 1:
            r, k = exact[0]
            ps = _priors(m, grid, r, q, line["kind"], ytd)
            if r in m.label_only or not ps:
                # a layout group named like the line, or a row with no prior: nothing proves it is this line
                res["leftover"].append(_open(line, ytd))
                continue
            b, v = ps[0]
            e = _entry(m, grid, q, line, r, "recast", b, v, ytd, _sign(v, _cp(line)[1], k))
            res["matched"].append(e)
            taken.add(r)
            res["diffs"].append(_diff(m, e))
            continue
        comb = _combined(m, grid, q, line, ytd, own, taken)
        if comb:
            res["combined"].append(comb)
            taken.update(comb["rows"])
            continue
        res["leftover"].append(_open(line, ytd))
    res["diffs"] += _fy_diffs(m, q, res["matched"])
    return res


def _fy_diffs(m, q, entries):
    """Full-year prior values (Q4 print) that differ from MOD's year-ago FY column: restatement candidates too."""
    out = []
    for e in entries:
        mp, new = e.get("fy_model_prior"), e.get("fy_prior")
        if mp is None or new is None or abs(mp - new) <= e["tol"]:
            continue
        fy = m.fy_of(m.pyq(q))
        out.append({"ref": f"{m.col(fy)}{e['row']}", "key": e["key"], "period": fy, "model": mp, "new": new,
                    "label": e["label"], "line": e["line"], "file": e["file"], "lineno": e["lineno"]})
    return out


def _diff(m, e):
    ref = None
    if e["basis"] and not e["basis"].startswith("YTD"):
        ref = f"{m.col(e['basis'])}{e['row']}"
    return {"ref": ref, "key": e["key"], "period": e["basis"], "model": e["model_prior"], "new": e["prior"],
            "label": e["label"], "line": e["line"], "file": e["file"], "lineno": e["lineno"]}


def _combined(m, grid, q, line, ytd, pref, taken):
    prior, tol = _cp(line)[1] * line["factor"], release.tolerance(line)
    order = [r for r, _ in pref]
    found = []
    for i in range(len(order)):
        for n in (2, 3, 4):
            run = order[i:i + n]
            if len(run) < n or any(r in taken or r in m.label_only for r in run) \
                    or len({_section(k) for r, k in pref if r in run}) > 1:
                continue
            if any(run[j + 1] - run[j] > 3 for j in range(n - 1)):
                continue                                  # adjacent lines only (analysis rows may sit between)
            for basis in {b for r in run for b, _ in _priors(m, grid, r, q, line["kind"], ytd)}:
                vals = [dict(_priors(m, grid, r, q, line["kind"], ytd)).get(basis) for r in run]
                if any(v is None for v in vals) or not sum(vals):
                    continue
                for sign in (1, -1):
                    if abs(sum(vals) - prior * sign) <= tol and run not in [f[0] for f in found]:
                        found.append((run, basis, sign))
                        break
    if len(found) != 1:
        return None
    run, basis, sign = found[0]
    return {"line": line["id"], "label": line["label"], "rows": run, "keys": [k for r, k in pref if r in run],
            "cur": _cur(m, grid, run, q, line, ytd, sign), "sign": sign, "prior": prior * sign, "basis": basis,
            "file": line["file"], "lineno": line["line"], "tol": release.tolerance(line)}


def check_anchor(answer, line_by_id, root):
    """The agent's anchor must be the line's own file:line, and that line's cells must print the number."""
    ln = line_by_id[answer["line"]]
    a = answer.get("anchor", "")
    if a != f"{ln['file']}:{ln['lineno']}":
        return f"{answer['line']}: anchor {a!r} is not the line's own ({ln['file']}:{ln['lineno']})"
    text = open(os.path.join(root, ln["file"]), encoding="utf-8").read().split("\n")[ln["lineno"] - 1]
    v = _cp(ln)[0]
    if not any(abs(x - v) < 1e-9 for x in release.parse_row(text)[1]):   # a dash is 0; '11.2' does not print 1.2
        return f"{answer['line']}: {v} is not on {a}"
    return None


def apply_answers(res, answers, m, root, grid, q):
    """answers: [{line, action: map|combined|new_line|skip, key?, keys?, anchor, reason}] for every leftover and
    ambiguous line. Everything is checked before anything changes: returns (new res, []) or (res unchanged, problems)."""
    open_ = {e["line"]: e for e in res["leftover"] + res["ambiguous"]}
    taken = {e["row"] for e in res["matched"]} | {r for c in res["combined"] for r in c["rows"]}
    problems, seen, add, used = [], set(), {k: [] for k in BUCKETS}, {}
    for a in answers:
        lid = a.get("line")
        if lid not in open_:
            problems.append(f"{lid}: not an open line")
            continue
        if lid in seen:
            problems.append(f"{lid}: answered twice")
            continue
        seen.add(lid)
        e, act = open_[lid], a.get("action")
        p = check_anchor(a, open_, root)
        if p:
            problems.append(p)
            continue
        if not a.get("reason"):
            problems.append(f"{lid}: no reason")
            continue
        if act in ("map", "combined"):
            keys = [a.get("key")] if act == "map" else list(a.get("keys") or [])
            if not keys or any(k not in m.keys for k in keys):
                problems.append(f"{lid}: {', '.join(map(str, keys)) or 'no key'} is not a MOD row")
                continue
            rows = [m.row(k) for k in keys]
            clash = [k for k, r in zip(keys, rows) if r in taken or r in used]
            if clash:
                who = [used.get(m.row(k), "already matched") for k in clash]
                problems.append(f"{lid}: {', '.join(clash)} already has a value ({', '.join(who)})")
                continue
            used.update({r: lid for r in rows})
            prs = [_priors(m, grid, r, q, e["kind"], e["ytd"]) for r in rows]
            b = prs[0][0][0] if all(prs) else None
            mp = [dict(p).get(b) for p in prs] if b else []
            model_prior = sum(mp) if b and all(v is not None for v in mp) else None
            sign = _sign(model_prior, _cp(e)[1], keys[0])
            line = {**e, "id": e["line"], "line": e["lineno"]}
            if act == "map":
                ent = _entry(m, grid, q, line, rows[0], "agent", b, model_prior, e["ytd"], sign)
                ent["reason"] = a["reason"]
                add["matched"].append(ent)
                if model_prior is not None and abs(model_prior - ent["prior"]) > ent["tol"]:
                    add["diffs"].append(_diff(m, ent))
                add["diffs"] += _fy_diffs(m, q, [ent])
            else:
                add["combined"].append({"line": lid, "label": e["label"], "rows": rows, "keys": keys, "by": "agent",
                                        "reason": a["reason"], "cur": _cur(m, grid, rows, q, line, e["ytd"], sign),
                                        "sign": sign, "prior": _cp(e)[1] * e["factor"] * sign, "basis": b,
                                        "file": e["file"], "lineno": e["lineno"], "tol": release.tolerance(e)})
        elif act == "new_line":
            add["new_lines"].append({**e, "reason": a["reason"]})
        elif act == "skip":
            add["skipped"].append({**e, "reason": a["reason"]})
        else:
            problems.append(f"{lid}: unknown action {act!r}")
    for lid in open_:
        if lid not in seen:
            problems.append(f"{lid}: not answered")
    if problems:
        return res, problems
    out = {k: list(res.get(k, [])) + add[k] for k in BUCKETS}
    out["leftover"], out["ambiguous"] = [], []
    return out, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["match", "apply"])
    ap.add_argument("--release"), ap.add_argument("--model", required=True), ap.add_argument("--values", required=True)
    ap.add_argument("--quarter", required=True), ap.add_argument("--match"), ap.add_argument("--answers")
    ap.add_argument("--release-root"), ap.add_argument("--out", required=True)
    a = ap.parse_args()
    m = ModMap(a.model)
    g = json.load(open(a.values))["MOD"]
    if a.cmd == "match":
        res = match(json.load(open(a.release)), m, g, a.quarter)
    else:
        res, problems = apply_answers(json.load(open(a.match)), json.load(open(a.answers)), m, a.release_root,
                                      g, a.quarter)
        if problems:
            print("\n".join(problems))
            sys.exit(1)
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: len(v) for k, v in res.items()}))


if __name__ == "__main__":
    main()
