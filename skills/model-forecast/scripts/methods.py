"""One plan entry -> the cells it writes in the forecast columns: {ref: (kind, value, color)}.
kind 'f' = formula (no '='), 'n' = typed number; color 'blue' (typed input), 'green' (link), 'black' (formula).
See the plan's methods table (docs/superpowers/plans/2026-11-09-model-forecast.md)."""
import re

TOKEN = re.compile(r"\{(?:(prev|pyq|fy|q1|q2|q3|q4):)?([^{}]+)\}")


def value_for(values, q, fy, key=""):
    """A quarter's value: its own key, else its year, else the latest earlier year (carried forward).
    Nothing at or before the period is an error: a later year's value is never borrowed."""
    if q in values:
        return values[q]
    years = sorted(k for k in values if re.match(r"\d{4}E$", k))
    earlier = [y for y in years if y <= fy]
    if not earlier:
        raise ValueError(f"{key}: no value for {q}")
    return values[earlier[-1]]


def prior_fy(m, fy):
    """The fiscal-year column before `fy` ('2027E' -> '2026E', '2026E' -> '2025')."""
    y = f"{int(fy[:4]) - 1}"
    return y + "E" if y + "E" in m.labels else y


def _ref(m, key, p, mode=None):
    if mode == "prev":
        p = m.prev(p) if m.is_q(p) else prior_fy(m, p)
    elif mode == "fy":                                   # a quarter reads its fiscal year's (annual) driver
        p = m.fy_of(p) if m.is_q(p) else p
    elif mode in ("q1", "q2", "q3", "q4"):              # that quarter of the same fiscal year (e.g. nine-month sums)
        p = m.quarters_of(m.fy_of(p) if m.is_q(p) else p)[int(mode[1]) - 1]
    elif mode == "pyq":
        p = m.pyq(p)
    return f"{m.col(p)}{m.row(key)}"


def days_in(m, p):
    return 91.25 if m.is_q(p) else 365


def expand(m, template, p):
    """Replace the row tokens of a template at period p ({KEY}, {prev:KEY}, {pyq:KEY}, {days})."""
    def sub(t):
        if t.group(1) is None and t.group(2).strip() == "days":
            return str(days_in(m, p))
        return _ref(m, t.group(2).strip(), p, t.group(1))
    return TOKEN.sub(sub, template)


def quarter_formula(m, e, q, fy):
    key, meth = e["key"], e["method"]
    r = m.row(key)
    col = m.col(q)
    if meth == "growth":
        rr = m.analysis(key, "% yoy")
        return f"{_ref(m, key, q, 'pyq')}*(1+{col}{rr})", {f"{col}{rr}": value_for(e["rates"], q, fy, key)}
    if meth == "pct_of":
        rr = m.analysis(key, e.get("rate_row", "% of sales"))
        sign = "-" if e.get("sign", 1) < 0 else ""
        return f"{sign}{col}{m.row(e['of'])}*{col}{rr}", {f"{col}{rr}": value_for(e["rates"], q, fy, key)}
    if meth == "days":
        rr = m.row(e["rate_row"])
        return f"{col}{rr}/{days_in(m, q)}*{col}{m.row(e['of'])}", {f"{col}{rr}": value_for(e["rates"], q, fy, key)}
    if meth == "flat":
        return f"{_ref(m, key, q, 'prev')}", {}
    if meth == "schedule":
        return None, {f"{col}{r}": value_for(e["values"], q, fy, key)}
    if meth == "formula":
        return expand(m, e["template"], q), {}
    raise ValueError(f"unknown method {meth} for {key}")


def cells_for(m, e):
    out = {}
    key, r = e["key"], m.row(e["key"])
    if e["method"] == "seasonal":
        return seasonal_cells(m, e)
    if e["method"] == "annual":
        return annual_cells(m, e)
    year_spread = set()                  # flow schedule years given as one yearly figure
    if e["method"] == "schedule" and e["kind"] == "flow":
        for fy in m.forecast_years():
            fq = [q for q in m.quarters_of(fy) if q.endswith("E")]
            if not all(q in e["values"] for q in fq):
                year_spread.add(fy)
                c = m.col(fy)
                out[f"{c}{r}"] = ("n", value_for(e["values"], fy, fy, key), "blue")
                actual = "".join(f"-{m.col(q)}{r}" for q in m.quarters_of(fy) if not q.endswith("E"))
                for q in fq:
                    out[f"{m.col(q)}{r}"] = ("f", f"({c}{r}{actual})/{len(fq)}" if actual else f"{c}{r}/{len(fq)}", "black")
    for q in m.forecast_quarters():
        fy = m.fy_of(q)
        if fy in year_spread:
            continue
        f, typed = quarter_formula(m, e, q, fy)
        if f is not None:
            out[f"{m.col(q)}{r}"] = ("f", f, "black")
        for ref, v in typed.items():
            out[ref] = ("n", v, "blue")
    for fy in m.forecast_years():
        qs = m.quarters_of(fy)
        if e.get("fy_template"):
            out[f"{m.col(fy)}{r}"] = ("f", expand(m, e["fy_template"], fy), "black")
            continue
        if fy in year_spread:
            continue
        if e["kind"] == "flow":
            out[f"{m.col(fy)}{r}"] = ("f", f"SUM({m.col(qs[0])}{r}:{m.col(qs[-1])}{r})", "black")
        elif e["kind"] == "balance":
            out[f"{m.col(fy)}{r}"] = ("f", f"{m.col(qs[-1])}{r}", "black")
        elif e.get("history_template"):          # a rate run quarter by quarter: the year shows its actual ratio
            out[f"{m.col(fy)}{r}"] = ("f", expand(m, e["history_template"], fy), "black")
    if e.get("history_template"):                # the evidence beside it: the ratio in the last history years
        hist = [p for p in m.order if re.fullmatch(r"\d{4}", p)][-int(e.get("history_years", 5)):]
        for fy in hist:
            out[f"{m.col(fy)}{r}"] = ("f", expand(m, e["history_template"], fy), "black")
    return out


def annual_cells(m, e):
    """A driver row that is a yearly figure: FY columns only, quarters left alone.
    `values` by year are typed (blue); a `template` is a black formula at each FY column ({prev:KEY} = prior FY)."""
    out, r = {}, m.row(e["key"])
    for fy, v in e.get("history_values", {}).items():   # a sourced starting point on a row the plan adds
        out[f"{m.col(fy)}{r}"] = ("n", v, "blue")
    if e.get("history_template"):                        # the evidence: the actual historical ratio, beside the input
        hist = [p for p in m.order if re.fullmatch(r"\d{4}", p)][-int(e.get("history_years", 5)):]
        for fy in hist:
            out[f"{m.col(fy)}{r}"] = ("f", expand(m, e["history_template"], fy), "black")
    years = m.forecast_years()
    for fy in years:
        ref = f"{m.col(fy)}{r}"
        if e.get("templates"):                           # a formula per year (the latest one at or before carries on)
            got = [y for y in sorted(e["templates"]) if y <= fy]
            if got and e["templates"][got[-1]] is not None:  # a null year stops the row (a one-year derivation)
                out[ref] = ("f", expand(m, e["templates"][got[-1]], fy), "black")
        elif e.get("template"):
            out[ref] = ("f", expand(m, e["template"], fy), "black")
        elif any(y <= fy for y in e["values"]):          # an input may start after the first forecast year
            out[ref] = ("n", value_for(e["values"], fy, fy, e["key"]), "blue")
    return out


def seasonal_cells(m, e):
    """FY = prior FY x (1 + typed annual growth in the FY '% yoy' cell), or, with `fy_template`, a formula on the
    key-driver rows (the driver build); quarters = FY x share; in a year with actual quarters, the forecast quarters
    share what is left by their relative shares."""
    out, key = {}, e["key"]
    r, sea = m.row(key), m.analysis(key, "seasonality")
    for fy in m.forecast_years():
        prior = prior_fy(m, fy)
        c = m.col(fy)
        if e.get("fy_template"):
            out[f"{c}{r}"] = ("f", expand(m, e["fy_template"], fy), "black")
            try:                                     # growth falls out of the drivers: show it
                yoy = m.analysis(key, "% yoy")
                out[f"{c}{yoy}"] = ("f", f'IFERROR({c}{r}/{m.col(prior)}{r}-1,"n.a.")', "black")
            except KeyError:
                pass
        else:
            yoy = m.analysis(key, "% yoy")
            out[f"{c}{yoy}"] = ("n", value_for(e["annual_growth"], fy, fy, key), "blue")
            out[f"{c}{r}"] = ("f", f"{m.col(prior)}{r}*(1+{c}{yoy})", "black")
        qs = m.quarters_of(fy)
        actual = [q for q in qs if not q.endswith("E")]
        fc = [q for q in qs if q.endswith("E")]
        for q in fc:
            out[f"{m.col(q)}{sea}"] = ("n", e["shares"][q.split()[0]], "blue")
        left = f"{c}{r}" + "".join(f"-{m.col(q)}{r}" for q in actual)
        tot = "+".join(f"{m.col(q)}{sea}" for q in fc)
        for q in fc:
            share = f"{m.col(q)}{sea}" if not actual else f"{m.col(q)}{sea}/({tot})"
            out[f"{m.col(q)}{r}"] = ("f", f"({left})*{share}" if actual else f"{c}{r}*{share}", "black")
    return out
