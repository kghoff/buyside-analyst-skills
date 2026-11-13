"""The user's inputs, value per share and the reverse DCF.

usage: python3 solve.py --model M.xlsx --ctx context.json --written inputs_written.json --out solved.json
Inputs: what the user typed in the yellow cells of the model's DCF tab (read only): a cell is theirs if it differs from what
the last build wrote (inputs_written.json) or holds a formula. Every other cell takes the defaults (dcfmath.defaults).
Reverse DCF: for today's price and the 3-year high and low, the shift in one driver at a time (each revenue-identity
factor's growth, and the gross-margin change), added to its first five input years after MOD (others at the user's
inputs), that makes value per share equal the price. Writes solved.json and prints which inputs were kept and which defaulted."""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dcfmath import defaults, factor_names, label, prepare, run, to_scn, value_only  # noqa: E402

SHIFT_YEARS = 5


def drivers(ctx):
    """The reverse DCF's drivers: each revenue-identity factor (by name), then the gross-margin change."""
    return factor_names(ctx) + ["dgm"]


def _range(d):
    return 2000.0 if d == "dgm" else 0.5


def _bisect(f, lo, hi):
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo > 0) == (fhi > 0):
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2


def shift_years(ctx):
    """The first five input years after MOD (DXCM: 2031E-2035E): where the reverse DCF adds its shift."""
    return [label(ctx, ctx["k"] + t) for t in range(1, SHIFT_YEARS + 1)]


def shift(inputs, ctx, driver, x):
    """The user's inputs with x added to `driver` in the first five input years after MOD (a copy)."""
    s = dict(inputs)
    s[driver] = dict(inputs[driver])
    for y in shift_years(ctx):
        s[driver][y] += x
    return s


def _value(inputs, ctx):
    c = prepare(ctx, inputs)
    return value_only(to_scn(inputs, c), c)


def metrics(inputs, ctx, driver=None):
    """Over the shift years (last MOD year -> 5 years on): revenue CAGR, gross margin at the end, and the moved
    driver's own CAGR (a factor) or end gross margin (dgm)."""
    c = prepare(ctx, inputs)
    r = run(to_scn(inputs, c), c)
    a, e = ctx["k"] - 1, ctx["k"] + SHIFT_YEARS - 1
    cagr = lambda x, y: (y / x) ** (1 / SHIFT_YEARS) - 1 if x and y and x > 0 and y > 0 else float("nan")
    out = {"rev_cagr5": cagr(r["rev"][a], r["rev"][e]), "rev_end": r["rev"][e], "gm_end": r["gm"][e],
           "value": r["value_per_share"]}
    if driver and driver != "dgm":
        j = factor_names(ctx).index(driver)
        out["driver_cagr5"] = cagr(r["levels"][a][j], r["levels"][e][j])
    return out


def reverse(price, inputs, ctx):
    out = {"price": price}
    for d in drivers(ctx):
        x = _bisect(lambda v: _value(shift(inputs, ctx, d, v), ctx) - price, -_range(d), _range(d))
        out[d] = ({"status": "out of range"} if x is None
                  else {"status": "ok", "shift": x, **metrics(shift(inputs, ctx, d, x), ctx, d)})
    return out


def solve(ctx, kept=None, kept_from=None, as_of=None, formulas=None):
    """formulas: {input: {year: formula}} the user typed as formulas (their values are in kept); build writes them back."""
    inputs = defaults(ctx, kept)
    c = prepare(ctx, inputs)
    r = run(to_scn(inputs, c), c)
    rev = {name: reverse(p["value"], inputs, ctx) for name, p in ctx["price"].items()}
    return {"as_of": as_of or dt.date.today().isoformat(), "inputs": inputs, "formulas": formulas or {},
            "value_per_share": r["value_per_share"], "tv_share": r["tv_share"], "user": metrics(inputs, ctx),
            "shift_years": shift_years(ctx), "reverse": rev, "kept_from": kept_from,
            **dict(zip(("kept", "defaulted"), summary(kept or {}, ctx)))}


def summary(kept, ctx):
    """({input: [years]} kept from the tab, {input: [years]} defaulted), over the tab's input cells only."""
    import build
    k_out, d_out = {}, {}
    for name, years in build.input_cells(ctx).items():
        for y in years:
            hit = (y is None and name in kept) or (y is not None and y in kept.get(name, {}))
            (k_out if hit else d_out).setdefault(name, []).append(y or "value")
    return k_out, d_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ctx", required=True)
    ap.add_argument("--written", required=True, help="inputs_written.json of the last build (need not exist yet)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import build
    ctx = json.load(open(a.ctx))
    kept, formulas, kind, orphans = build.read_inputs(a.model, ctx, a.written)
    out = solve(ctx, kept, kind, formulas=formulas)
    out["orphans"] = orphans
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({"wrote": a.out, "value_per_share": round(out["value_per_share"], 2),
                      "tv_share": round(out["tv_share"], 3), "existing_tab": kind, "orphans": orphans,
                      "identity_fallback": ctx.get("identity_fallback"),
                      "kept": {n: build.span(v) for n, v in out["kept"].items()},
                      "defaulted": {n: build.span(v) for n, v in out["defaulted"].items()}}, indent=1))


if __name__ == "__main__":
    main()
