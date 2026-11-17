"""The scenario loop's bridge to model-dcf's own math (so a scenario's value equals what the DCF tab would show).

Runs ONLY as its own process: model-dcf's scripts go first on sys.path, and its build / context / xlsx / lo / modmap /
notebox share names with model-valuation's modules. Never import this file.

usage:
  scenario_eval.py context --model M.xlsx --out dcf.json [--plan forecast_plan.json]
  scenario_eval.py eval --dcf dcf.json --try scenarios_try_<n>.json --ntm-eps a --ntm1-eps b --out result.json
  scenario_eval.py typecheck --after OUT.xlsx --dcf dcf.json --plan valuation_plan.json --work DIR"""
import os
import sys

DCF = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "model-dcf", "scripts")
sys.path.insert(0, os.path.abspath(DCF))      # model-dcf's build/context/xlsx/lo win; never import this file
import build, context, dcfmath, solve          # noqa: E402,E401  (model-dcf's)
sys.path.insert(1, os.path.dirname(os.path.realpath(__file__)))
import scenarios                                # noqa: E402  (model-valuation's; model-dcf has no such module)

import argparse  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402

STALE = 0.02


def _cached_vps(model, row, work=None):
    """The DCF tab's value per share as last calculated; a file never recalculated is recalculated in a temp copy."""
    import openpyxl
    import lo
    read = lambda p: openpyxl.load_workbook(p, read_only=True, data_only=True)[build.TAB].cell(row, 3).value
    v = read(model)
    if v is None:
        v = read(lo.recalc(model, work or tempfile.mkdtemp(prefix="val_dcf_")))
    return v


def cmd_context(a):
    ctx = context.build(a.model, a.plan)
    w = os.path.join(os.path.dirname(os.path.abspath(a.model)), "_model_work", "dcf", "inputs_written.json")
    kept, formulas, kind, _ = build.read_inputs(a.model, ctx, w if os.path.exists(w) else None)
    if kind is None:
        raise SystemExit("model-valuation: the model has no DCF tab. Run /model-dcf first.")
    solved = solve.solve(ctx, kept, kind, formulas=formulas)
    R = build.layout(ctx)["rows"]
    ref = lambda n: f"{build.TAB}!$C${R[n]}"
    out = {"ctx": ctx, "inputs": solved["inputs"], "value_per_share": solved["value_per_share"],
           "tv_share": solved["tv_share"], "price": ctx["price"],
           "input_years": [dcfmath.label(ctx, t) for t in range(ctx["k"] + 1, 31)],
           "names": dcfmath.factor_names(ctx) + ["dgm", *dcfmath.COST, "wacc", "tv_mult"],
           "refs": {"net_debt": ref("net_debt"), "shares": ref("shares"), "vps": ref("vps"), "price": ref("price")},
           "reverse": solved["reverse"]}
    tab = _cached_vps(a.model, R["vps"])
    if not isinstance(tab, (int, float)) or abs(tab - out["value_per_share"]) > STALE:
        shown = f"${tab:.2f}" if isinstance(tab, (int, float)) else repr(tab)
        out["stale"] = (f"the DCF tab shows {shown} but its inputs give ${out['value_per_share']:.2f}: "
                        "rerun /model-dcf")
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({"wrote": a.out, "value_per_share": round(out["value_per_share"], 2),
                      "names": out["names"], "stale": out.get("stale")}, indent=1))


def _case(dcf, spec, ctx):
    inputs = scenarios.expand(spec, dcf["inputs"], dcf["input_years"], dcf["names"])
    c = dcfmath.prepare(ctx, inputs)
    o = dcfmath.run(dcfmath.to_scn(inputs, c), c)
    return inputs, o, solve.metrics(inputs, ctx)


def cmd_eval(a):
    dcf = json.load(open(a.dcf))
    ctx, px = dcf["ctx"], dcf["price"]
    cases = scenarios.check_cases(json.load(open(a.try_)))
    out = {}
    for name in scenarios.CASES:
        inputs, o, mt = _case(dcf, cases[name].get("inputs"), ctx)
        v = o["value_per_share"]
        out[name] = {"value_per_share": v, "tv_share": o["tv_share"], "rev_cagr5": mt["rev_cagr5"],
                     "gm_end": mt["gm_end"], "pct_vs_price": v / px["last"]["value"] - 1,
                     "pct_vs_high3y": v / px["high3y"]["value"] - 1, "pct_vs_low3y": v / px["low3y"]["value"] - 1,
                     "implied_pe_ntm": v / a.ntm_eps, "implied_pe_ntm1": v / a.ntm1_eps, "inputs": inputs}
    out["implied"] = solve.reverse(px["last"]["value"], out["base"]["inputs"], ctx)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"{'case':<6}{'value/sh':>10}{'vs price':>10}{'TV share':>10}{'rev CAGR5':>11}{'P/E NTM':>9}{'NTM+1':>8}")
    for n in scenarios.CASES:
        r = out[n]
        print(f"{n:<6}{r['value_per_share']:>10.2f}{r['pct_vs_price']:>10.1%}{r['tv_share']:>10.1%}"
              f"{r['rev_cagr5']:>11.1%}{r['implied_pe_ntm']:>9.1f}{r['implied_pe_ntm1']:>8.1f}")
    print(f"today's price ${px['last']['value']:.2f} on the base case needs, one driver at a time "
          f"(added to {solve.shift_years(ctx)[0]}-{solve.shift_years(ctx)[-1]}):")
    for d, r in out["implied"].items():
        if d != "price":
            print(f"  {d}: " + (f"{r['shift']:+.4f}" if r["status"] == "ok" else r["status"]))


def cmd_typecheck(a):
    """Each final case typed into the DCF tab's yellow cells (model-dcf check.reverse_in_tab's method), recalculated
    in LibreOffice: its value per share must equal the plan's to $0.02."""
    import lo
    import xlverify
    from xledit import set_cells
    from xlsx import Package
    dcf = json.load(open(a.dcf))
    ctx = dcf["ctx"]
    final = json.load(open(a.plan))["scenarios"]["final"]
    R = build.layout(ctx)["rows"]
    cols = {dcfmath.label(ctx, t): build.tcol(t) for t in range(0, 31)}
    part = {s[0]: s[3] for s in Package(a.after).sheets()}[build.TAB]
    os.makedirs(a.work, exist_ok=True)
    problems, n = [], 0
    for name in scenarios.CASES:
        if name not in final:
            problems.append(f"{name}: not in the plan's final scenarios")
            continue
        inputs = scenarios.expand(final[name].get("inputs"), dcf["inputs"], dcf["input_years"], dcf["names"])
        cells = {f"C{R['wacc']}": ("n", inputs["wacc"], 0), f"C{R['mult']}": ("n", inputs["tv_mult"], 0)}
        for inp, years in build.input_cells(ctx).items():
            if inp in scenarios.SINGLE:
                continue
            row = R[inp] if inp in R else build.driver_row(ctx, R, inp)
            for y in years:
                cells[f"{cols[y]}{row}"] = ("n", inputs[inp][y], 0)
        pkg = Package(a.after)
        xml = pkg.text(part)
        # keep each cell's own style: replace the value only
        pkg.put(part, set_cells(xml, {r: (k, v, _style(xml, r)) for r, (k, v, _) in cells.items()}, replace=True)[0])
        p = os.path.join(a.work, f"typecheck_{name}.xlsx")
        pkg.save(p)
        v = xlverify._grid(lo.recalc(p, os.path.join(a.work, f"tc_{name}")))[build.TAB].get((R["vps"], 3))
        n += 1
        want = final[name].get("value_per_share")
        if not isinstance(v, (int, float)) or not isinstance(want, (int, float)) or abs(v - want) > STALE:
            problems.append(f"{name}: typing its inputs into the DCF tab gives {v!r}, the plan says {want!r}")
    print(json.dumps({"checked": n, "problems": problems}, indent=1))
    sys.exit(1 if problems else 0)


def _style(xml, ref):
    import re
    m = re.search(rf'<c r="{ref}"[^>]*?\ss="(\d+)"', xml)
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("context")
    c.add_argument("--model", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--plan", help="forecast_plan.json (default: the model's _model_work/forecast/forecast_plan.json)")
    e = sub.add_parser("eval")
    e.add_argument("--dcf", required=True)
    e.add_argument("--try", dest="try_", required=True)
    e.add_argument("--ntm-eps", type=float, required=True)
    e.add_argument("--ntm1-eps", type=float, required=True)
    e.add_argument("--out", required=True)
    t = sub.add_parser("typecheck")
    for n in ("after", "dcf", "plan", "work"):
        t.add_argument(f"--{n}", required=True)
    a = ap.parse_args()
    try:
        {"context": cmd_context, "eval": cmd_eval, "typecheck": cmd_typecheck}[a.cmd](a)
    except ValueError as x:
        raise SystemExit(f"model-valuation: {x}")


if __name__ == "__main__":
    main()
