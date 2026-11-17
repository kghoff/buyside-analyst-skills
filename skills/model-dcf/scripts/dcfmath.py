"""The DCF math, single source in Python (pure functions). The DCF tab's Excel formulas implement the same math.

Revenue = the forecast plan's revenue identity: the sum over terms of the product of their factors (each a MOD driver
row; an `average` factor uses (this year + last year) / 2). Years 1..k (MOD's forecast years) take the factor levels
and gross margin from MOD, so revenue and gross profit equal MOD; after that each factor grows at the user's yearly input.
inputs (the user's yellow cells, by year label, years k+1..30 only): one growth row per factor (keyed by its name), dgm,
opex_inc / tax / da_pct / capex_pct / wc_inc; plus wacc, tv_mult."""

COST = ("opex_inc", "tax", "da_pct", "capex_pct", "wc_inc")
DGM_LONG_RUN = 0.0
FADE_YEARS = 10


def label(ctx, t):
    """Year label of forecast year t (0 = year 0), e.g. 2026E + 3 -> 2029E."""
    y0 = ctx["year0"]
    return f"{int(y0[:4]) + t}{y0[4:]}"


def factor_names(ctx):
    return [f["name"] for f in ctx["factors"]]


def identity(levels, prev, ctx):
    """Revenue from factor levels this year (and last year, for average factors)."""
    total = 0.0
    for term in ctx["terms"]:
        prod = 1.0
        for i in term:
            f = ctx["factors"][i]
            prod *= (levels[i] + prev[i]) / 2 if f["average"] else levels[i]
        total += prod
    return total


def prepare(ctx, inputs):
    out = dict(ctx)
    out["wacc"], out["tv_mult"] = inputs["wacc"], inputs["tv_mult"]
    return out


def run(scn, ctx):
    k, mod, wacc = ctx["k"], ctx["mod"], ctx["wacc"]
    F = ctx["factors"]
    lv = [f["level0"] for f in F]
    lv_prev = [f["level_prev"] for f in F]
    if abs(identity(lv, lv_prev, ctx) - ctx["rev0"]) > 0.005 * ctx["rev0"]:
        raise ValueError("the revenue identity does not give year-0 revenue")
    keys = ["levels", "rev", "gm", "gp", "opex", "oi", "taxr", "nopat", "da", "capex", "wc", "ufcf", "df", "pv"]
    o = {x: [] for x in keys}
    gm = ctx["gm0"]
    rev_prev, opex_prev = ctx["rev0"], ctx["opex0"]
    for i in range(30):
        t = i + 1
        new = [f["mod"][i] if t <= k else lv[j] * (1 + scn["g"][j][i]) for j, f in enumerate(F)]
        lv_prev, lv = lv, new
        rev = identity(lv, lv_prev, ctx)
        if t <= k:
            gm = mod["gp"][i] / mod["rev"][i]
            opex, taxr, da, capex, wc = mod["opex"][i], mod["tax_rate"][i], mod["da"][i], mod["capex"][i], mod["wc"][i]
        else:
            gm = gm + scn["dgm"][i] / 10000
            opex = opex_prev + scn["opex_inc"][i] * (rev - rev_prev)
            taxr = scn["tax"][i]
            da = scn["da_pct"][i] * rev
            capex = scn["capex_pct"][i] * rev
            wc = -scn["wc_inc"][i] * (rev - rev_prev)
        gpd = rev * gm
        oi = gpd - opex
        nopat = oi * (1 - taxr)
        ufcf = nopat + da - capex + wc
        df = 1 / (1 + wacc) ** t
        for name, v in zip(keys, [list(lv), rev, gm, gpd, opex, oi, taxr, nopat, da, capex, wc, ufcf, df, ufcf * df]):
            o[name].append(v)
        rev_prev, opex_prev = rev, opex
    o["pv_fcf"] = sum(o["pv"])
    o["tv"] = ctx["tv_mult"] * o["ufcf"][29]
    o["pv_tv"] = o["tv"] * o["df"][29]
    o["ev"] = o["pv_fcf"] + o["pv_tv"]
    o["equity"] = o["ev"] - ctx["net_debt"]
    o["value_per_share"] = o["equity"] / ctx["shares"]
    o["tv_share"] = o["pv_tv"] / o["ev"] if o["ev"] else float("nan")
    cum, run_sum = [], 0.0
    for v in o["pv"]:
        run_sum += v
        cum.append(run_sum / o["ev"] if o["ev"] else float("nan"))
    o["cum_pv_share"] = cum
    return o


def value_only(scn, ctx):
    return run(scn, ctx)["value_per_share"]


def to_scn(inputs, ctx):
    """Inputs -> per-year arrays for run() (index 0 = year 1). MOD years are not inputs (zeros, unused)."""
    k = ctx["k"]
    if not 1 <= k <= 5:
        raise ValueError(f"MOD needs 1-5 forecast years (k={k})")
    lab = [label(ctx, t) for t in range(1, 31)]

    def arr(name):
        try:
            return [0.0] * k + [inputs[name][x] for x in lab[k:]]
        except KeyError as e:
            raise ValueError(f"input {name} is missing year {e.args[0]}")

    scn = {"g": [arr(n) for n in factor_names(ctx)], "dgm": arr("dgm")}
    for n in COST:
        scn[n] = arr(n)
    return scn


def _last_mod(ctx):
    """Last MOD year's factor growths and gross-margin change (bps): where the fades start."""
    k, F, mod = ctx["k"], ctx["factors"], ctx["mod"]
    prev = lambda f: f["mod"][k - 2] if k >= 2 else f["level0"]
    # growth from 0 has no meaning (a term that is 0 until late in MOD): its fade starts at its long-run rate
    g = {f["name"]: f["mod"][k - 1] / prev(f) - 1 if prev(f) else f["long_run"] for f in F}
    gm_k = mod["gp"][k - 1] / mod["rev"][k - 1]
    gm_p = mod["gp"][k - 2] / mod["rev"][k - 2] if k >= 2 else ctx["gm0"]
    return g, (gm_k - gm_p) * 10000


def _mod_costs(ctx):
    """MOD's cost ratios per forecast year 1..k: incremental opex per $ of new revenue, tax rate, D&A and capex % of
    revenue, working-capital investment per $ of new revenue."""
    mod = ctx["mod"]
    rev, opex = [ctx["rev0"]] + mod["rev"], [ctx["opex0"]] + mod["opex"]
    out = {n: [] for n in COST}
    for i in range(ctx["k"]):
        dr = rev[i + 1] - rev[i]
        out["opex_inc"].append((opex[i + 1] - opex[i]) / dr)
        out["tax"].append(mod["tax_rate"][i])
        out["da_pct"].append(mod["da"][i] / rev[i + 1])
        out["capex_pct"].append(mod["capex"][i] / rev[i + 1])
        out["wc_inc"].append(-mod["wc"][i] / dr)
    return out


def defaults(ctx, kept=None):
    """The default inputs (no agent). For the 10 years after MOD each factor's growth fades in a straight line from its
    last-MOD-year growth to its long-run growth (from the forecast plan's revenue identity), and the gross-margin
    change from its last-MOD-year value to 0 bps, then holds. Cost inputs hold MOD's last-year values. WACC 8%,
    terminal multiple 10x. kept: values the user typed (same shape, any subset); they win."""
    kept = kept or {}
    k = ctx["k"]
    if k < 1:
        raise ValueError("MOD has no forecast years (run /model-forecast first)")
    lab = lambda t: label(ctx, t)
    out = {n: {} for n in factor_names(ctx) + ["dgm", *COST]}

    def pick(name, t, v):
        out[name][lab(t)] = kept.get(name, {}).get(lab(t), v)

    g, dgm = _last_mod(ctx)
    for f in ctx["factors"]:
        for t in range(k + 1, 31):
            s = min(t - k, FADE_YEARS) / FADE_YEARS
            pick(f["name"], t, g[f["name"]] + (f["long_run"] - g[f["name"]]) * s)
    for t in range(k + 1, 31):
        s = min(t - k, FADE_YEARS) / FADE_YEARS
        pick("dgm", t, dgm + (DGM_LONG_RUN - dgm) * s)
    costs = _mod_costs(ctx)
    for n in COST:
        for t in range(k + 1, 31):
            pick(n, t, costs[n][-1])
    out["wacc"] = kept.get("wacc", 0.08)
    out["tv_mult"] = kept.get("tv_mult", 10.0)
    return out
