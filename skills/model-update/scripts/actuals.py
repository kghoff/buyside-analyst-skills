"""Enter a reported quarter into a COPY of the model (MOD tab, raw XML). See the spec's 'Entering actuals'.

usage: python3 actuals.py --model MODEL --quarter "Q3 26E" --match match.json --out OUT.xlsx --state state.json [--restate yes|no]
       python3 actuals.py --model MODEL --quarter "Q3 26" --match match_10q.json --out OUT.xlsx --state state.json --tenq [--take-10q refs.json]
Prints a JSON report: typed, formulas, awaiting, typed_subtotals, restated, restate_skipped, header."""
import argparse
import json
import os
import re
import sys

import openpyxl
from openpyxl.formula.translate import Translator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap                      # noqa: E402
from xledit import set_cells, unshare          # noqa: E402
from xlsx import Package, Styles               # noqa: E402
import mnotes                                  # noqa: E402

TAB = "MOD"
BLUE, BLACK = "FF0000FF", "FF000000"
REF = re.compile(r"(?<![A-Z$!])\$?([A-Z]{1,3})\$?(\d+)")


def _part(pkg):
    return next(p for n, _, _, p in pkg.sheets() if n == TAB)


def _cells(model):
    """{ref: formula text without '=' or None} and {ref: value} straight from the file (formulas as written)."""
    ws = openpyxl.load_workbook(model)[TAB]
    f, v = {}, {}
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                f[c.coordinate] = c.value[1:]
            elif c.value is not None:
                v[c.coordinate] = c.value
    return f, v


def _style_of(xml, ref):
    m = re.search(rf'<c r="{ref}"(?:\s[^>]*?)?\ss="(\d+)"', xml)
    return int(m.group(1)) if m else 0


def _fmt(x):
    return f"{x:,.2f}" if abs(x) < 10 and x != int(x) else f"{x:,.1f}"


def _note(e):
    v = _fmt(e["printed"]) if e.get("printed") is not None else ""
    ytd = " YTD" if e.get("ytd") else ""
    tail = " less earlier quarters in MOD" if e.get("ytd") else ""
    return f"{mnotes.NOTE}{e['label']}{ytd} {v}{tail} - {e['file']} line {e['lineno']}"


def build(model, quarter, res, out, state_path, restate=False):
    m = ModMap(model)
    q, py = quarter, m.pyq(quarter)
    qc, pc = m.col(q), m.col(py)
    formulas, values = _cells(model)
    pkg = Package(model)
    part = _part(pkg)
    xml = unshare(pkg.text(part), TAB, TAB)
    st = Styles(pkg.text("xl/styles.xml"))
    mapped = {e["row"]: e for e in res["matched"] if e.get("cur") is not None}
    combined_rows = {r for c in res["combined"] for r in c["rows"]}
    plan, notes = {}, {}
    awaiting, typed_sub, typed = set(), [], {}
    for row, key, _ in m.lines:
        if row <= 2:
            continue                                  # title and period-header rows
        ref, pref = f"{qc}{row}", f"{pc}{row}"
        if row in mapped and row not in combined_rows:
            if pref in formulas:
                plan[ref] = ("f", Translator("=" + formulas[pref], origin=pref).translate_formula(ref)[1:])
            else:
                plan[ref] = ("n", float(mapped[row]["cur"]))
        elif pref in formulas:
            plan[ref] = ("f", Translator("=" + formulas[pref], origin=pref).translate_formula(ref)[1:])
        elif ref in formulas or ref in values:
            plan[ref] = ("", None)
            awaiting.add(ref)
    changed = True
    while changed:                                    # a formula over a waiting cell can't stand
        changed = False
        for ref, (kind, val) in list(plan.items()):
            if kind != "f":
                continue
            refs = {f"{c}{r}" for c, r in REF.findall(val) if c == qc}
            if refs & awaiting:
                row = int(ref[len(qc):])
                if row in mapped:
                    plan[ref] = ("n", float(mapped[row]["cur"]))
                    typed_sub.append({"ref": ref, "formula": val})
                else:
                    plan[ref] = ("", None)
                    awaiting.add(ref)
                changed = True
    cells = {}
    for ref, (kind, val) in plan.items():
        s = _style_of(xml, ref)
        if kind == "n":
            cells[ref] = ("n", val, st.recolor(s, BLUE))
            row = int(ref[len(qc):])
            notes[ref] = _note(mapped[row])
            typed[ref] = val
        elif kind == "f":
            cells[ref] = ("f", val, st.recolor(s, BLACK))
        else:
            cells[ref] = ("", None, s)
    cells[f"{qc}2"] = ("s", q.rstrip("E"), _style_of(xml, f"{qc}2"))
    header = [q.rstrip("E")]
    if q.startswith("Q4"):
        fy, pfy = m.fy_of(q), m.fy_of(py)
        fc, pfc = m.col(fy), m.col(pfy)
        cells[f"{fc}2"] = ("s", fy.rstrip("E"), _style_of(xml, f"{fc}2"))
        header.append(fy.rstrip("E"))
        for row, key, _ in m.lines:
            if f"{pfc}{row}" in formulas:
                src = f"{pfc}{row}"
                cells[f"{fc}{row}"] = ("f", Translator("=" + formulas[src], origin=src).translate_formula(f"{fc}{row}")[1:],
                                       st.recolor(_style_of(xml, f"{fc}{row}"), BLACK))
    restated, skipped = [], []
    if restate:
        for d in res["diffs"]:
            if not d.get("ref"):
                skipped.append({**d, "why": "year-to-date difference: no single cell"})
            elif d["ref"] in formulas:
                skipped.append({**d, "why": "the model cell is a formula"})
            else:
                cells[d["ref"]] = ("n", float(d["new"]), st.recolor(_style_of(xml, d["ref"]), BLUE))
                notes[d["ref"]] = f"{mnotes.NOTE}recast in {d['file']} line {d['lineno']} (was {d['model']})"
                restated.append(d["ref"])
    xml, _ = set_cells(xml, cells, replace=True)
    pkg.put(part, xml)
    mnotes.add_notes(pkg, part, notes)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import modfill; modfill.fix(out, out)
    import notebox; notebox.fix(out, out)
    key_of = {f"{qc}{r}": k for r, k, _ in m.lines}
    state = {"quarter": q.rstrip("E"), "column": qc,
             "awaiting": [{"ref": r, "key": key_of.get(r)} for r in sorted(awaiting)],
             "typed_subtotals": typed_sub, "release_values": typed,
             "combined": res["combined"], "tenq_checked": False}
    json.dump(state, open(state_path, "w"), indent=1)
    return {"typed": len(typed), "formulas": sum(1 for k, *_ in cells.values() if k == "f"),
            "awaiting": state["awaiting"], "typed_subtotals": typed_sub, "restated": restated,
            "restate_skipped": skipped, "header": header}


def fill_tenq(model, quarter, res, out, state_path, take=None):
    state = json.load(open(state_path))
    qc = state["column"]
    formulas, values = _cells(model)
    pkg = Package(model)
    part = _part(pkg)
    xml = unshare(pkg.text(part), TAB, TAB)
    st = Styles(pkg.text("xl/styles.xml"))
    waiting = {a["ref"] for a in state["awaiting"]}
    cells, notes, diffs, filled = {}, {}, [], []
    new = {}
    for e in res["matched"]:
        if e.get("cur") is None:
            continue
        ref = f"{qc}{e['row']}"
        new[ref] = e
        if ref in waiting:
            cells[ref] = ("n", float(e["cur"]), st.recolor(_style_of(xml, ref), BLUE))
            notes[ref] = _note(e)
            filled.append(ref)
        elif ref in state["release_values"] and abs(state["release_values"][ref] - e["cur"]) > e["tol"]:
            diffs.append({"ref": ref, "key": e["key"], "release": state["release_values"][ref], "tenq": e["cur"],
                          "file": e["file"], "lineno": e["lineno"]})
            if take and ref in take:
                cells[ref] = ("n", float(e["cur"]), st.recolor(_style_of(xml, ref), BLUE))
                notes[ref] = _note(e) + f" (release said {state['release_values'][ref]})"
    for c in state["combined"]:
        parts = [new.get(f"{qc}{r}") for r in c["rows"]]
        if all(parts) and abs(sum(p["cur"] for p in parts) - c["cur"]) > c["tol"] * len(parts):
            diffs.append({"ref": None, "key": " + ".join(c["keys"]), "release": c["cur"],
                          "tenq": sum(p["cur"] for p in parts), "file": c["file"], "lineno": c["lineno"], "combined": True})
    waiting -= set(filled)
    restored, still = [], []
    for t in state["typed_subtotals"]:
        refs = {f"{c}{r}" for c, r in REF.findall(t["formula"]) if c == qc}
        if refs & waiting:
            still.append(t)
        else:
            cells[t["ref"]] = ("f", t["formula"], st.recolor(_style_of(xml, t["ref"]), BLACK))
            restored.append(t["ref"])
    xml, _ = set_cells(xml, cells, replace=True)
    pkg.put(part, xml)
    mnotes.add_notes(pkg, part, notes)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import modfill; modfill.fix(out, out)
    import notebox; notebox.fix(out, out)
    state["awaiting"] = [a for a in state["awaiting"] if a["ref"] in waiting]
    state["typed_subtotals"] = still
    state["tenq_checked"] = not diffs or take is not None
    json.dump(state, open(state_path, "w"), indent=1)
    return {"filled": filled, "restored": restored, "differences": diffs, "awaiting": state["awaiting"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True), ap.add_argument("--quarter", required=True)
    ap.add_argument("--match", required=True), ap.add_argument("--out", required=True)
    ap.add_argument("--state", required=True), ap.add_argument("--restate", default="no")
    ap.add_argument("--tenq", action="store_true"), ap.add_argument("--take-10q")
    a = ap.parse_args()
    if os.path.abspath(a.out) == os.path.abspath(a.model):
        sys.exit("--out must be a new file, not the model itself")
    res = json.load(open(a.match))
    if a.tenq:
        take = json.load(open(a.take_10q)) if a.take_10q else None
        print(json.dumps(fill_tenq(a.model, a.quarter, res, a.out, a.state, take), indent=1))
    else:
        print(json.dumps(build(a.model, a.quarter, res, a.out, a.state, a.restate == "yes"), indent=1))


if __name__ == "__main__":
    main()
