# skills/model-summary/scripts/links.py
"""Every cell SUM links to, found by its label on the source tab, never by another skill's work files (they go
stale): DCF (the cap-table bridge), Valuation (verdict, house inputs, the primary multiple's block, blended R/R, the
R/R ladder, the 3-year IRR, the probability tree), Multiples (ranges, the forward table's Street EPS, the comp
sheet's subject 3M ADV), the Consensus tab's latest snapshot (every "<Metric> mean" by forecast year, mapped through
STREET_MAP; optional, Multiples' forward table is the EPS fallback) and MOD (rows by label within their section, FY
columns, the first four forecast quarters). A missing piece stops the build and names the skill to rerun. collect
reads formulas only; street_basis reads values (cached, else a recalculated copy) to match the Street's EPS basis.

collect(model) -> {"dcf", "val", "mult", "mod", "street"} of sheet-qualified refs ('Valuation!$B$39') and labels;
street_basis(L, model, work, override) then sets L["mod"]'s EPS and EBITDA rows."""
import os
import re

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter as L

import modrows
from modmap import ModMap

NEED = {"MOD": "model-historicals", "Px Data": "model-price-history", "DCF": "model-dcf",
        "Multiples": "model-multiples", "Valuation": "model-valuation"}
BIG = 10 ** 9
# SUM's estimates grid is F:N (4 actual years + 5 forecast years). More would run into the scenario block at P.
MAX_FORECAST_YEARS = 5


def stop(what, skill):
    raise SystemExit(f"model-summary: {what} not found. Rerun /{skill}, then /model-summary.")


def grid(ws):
    return {(r, c): v for r, row in enumerate(ws.iter_rows(values_only=True), 1)
            for c, v in enumerate(row, 1) if v is not None}


def labels(g, col=1):
    return sorted((r, str(v).strip()) for (r, c), v in g.items() if c == col and isinstance(v, str))


def first(rows, test, after=0, before=BIG):
    return next((r for r, t in rows if after < r < before and test(t)), None)


def ref(tab, col, row):
    t = f"'{tab}'" if " " in tab else tab
    return f"{t}!${col}${row}"


def b_label(rows, r):
    return next(t for rr, t in rows if rr == r)


def dcf(g):
    b = labels(g, 2)
    out = {}
    for key, prefix in (("cash", "Cash & equivalents"), ("st", "Short-term marketable securities"),
                        ("debt_cur", "Current debt"), ("debt_lt", "Long-term debt"), ("net_debt", "Net debt"),
                        ("shares", "Diluted shares, M"), ("price", "Price (last close")):
        r = first(b, lambda t: t.startswith(prefix))
        if r is None:
            stop(f"DCF row '{prefix}'", "model-dcf")
        out[key] = ref("DCF", "C", r)
        if key == "price":
            out["date"] = ref("DCF", "D", r)
        if key == "cash":
            m = re.search(r"\(([^)]*)\)\s*$", b_label(b, r))
            out["period"] = m.group(1).strip() if m else None
    return out


def valuation(g):
    a = labels(g)
    V = lambda col, r: ref("Valuation", col, r)       # noqa: E731

    def row(test, what, after=0, before=BIG):
        r = first(a, test, after, before)
        if r is None:
            stop(f"Valuation row '{what}'", "model-valuation")
        return r

    out = {"action": V("B", row(lambda t: t.startswith("Overall verdict"), "Overall verdict")),
           "hurdle": V("B", row(lambda t: t == "IRR hurdle", "IRR hurdle")),
           "buy_rr": V("B", row(lambda t: t == "Buy at R/R", "Buy at R/R")),
           "blended_rr": V("B", row(lambda t: t == "Blended reward / risk", "Blended reward / risk"))}
    s1 = row(lambda t: t.startswith("1. Which multiples"), "1. Which multiples and why")
    e1 = row(lambda t: t == "Weights sum", "Weights sum", s1)
    kind = next((t for r, t in a if s1 < r < e1 and g.get((r, 2)) == "primary"), None)
    if kind is None:
        stop("Valuation's primary multiple", "model-valuation")
    out["kind"] = kind
    pr = first(a, lambda t: t.startswith("Position (long/short)"))
    out["position"] = {"ref": V("B", pr), "value": g.get((pr, 2))} if pr else None

    hdr = row(lambda t: t == f"{kind} (primary)", f"{kind} (primary)")
    blk, r = {}, hdr + 1
    while isinstance(g.get((r, 1)), str) and g[(r, 1)].startswith(kind):
        blk[g[(r, 1)].strip()[len(kind):].lstrip(": ").strip()] = r
        r += 1

    def pick(test, what):
        k = next((k for k in blk if test(k)), None)
        if k is None:
            stop(f"Valuation row '{kind}: {what}'", "model-valuation")
        return k
    keys = {"ntm1": pick(lambda k: k.startswith("NTM+1 "), "NTM+1 ..."),
            "reward_mult": pick(lambda k: k.startswith("reward multiple"), "reward multiple"),
            "reward_price": pick(lambda k: k == "reward price", "reward price"),
            "risk_metric": pick(lambda k: k.startswith("risk ") and k not in ("risk multiple", "risk price", "risk %"),
                                "risk <metric>"),
            "risk_mult": pick(lambda k: k == "risk multiple", "risk multiple"),
            "risk_price": pick(lambda k: k == "risk price", "risk price")}
    out["primary"] = {n: {"ref": V("B", blk[k]), "label": f"{kind}: {k}", "row": blk[k]} for n, k in keys.items()}

    h4c = row(lambda t: t.startswith("4c. Reward / risk ladder"), "4c. Reward / risk ladder")
    lad, r = [], h4c + 1
    while isinstance(g.get((r, 1)), (int, float)):
        lad.append({"move": V("A", r), "entry": V("B", r), "reward": V("C", r), "risk": V("D", r), "rr": V("E", r)})
        r += 1
    if not lad:
        stop("rungs under '4c. Reward / risk ladder'", "model-valuation")
    out["ladder"] = lad

    h5 = row(lambda t: t.startswith("5. ") and "IRR" in t, "5. N-year IRR")
    e5 = first(a, lambda t: t.startswith("6. "), h5) or BIG
    irr = {"metric3": row(lambda t: bool(re.match(r"^IRR: .+ in \d+ years \(", t)), "IRR: <metric> in N years", h5, e5),
           "years": row(lambda t: t == "IRR: years", "IRR: years", h5, e5),
           "mult3": row(lambda t: t.endswith("-year horizon"), "<multiple> at the N-year horizon", h5, e5),
           "price3": row(lambda t: t.startswith("IRR: price in"), "IRR: price in N years", h5, e5),
           "irr": row(lambda t: t == "IRR", "IRR", h5, e5)}
    lab = dict(a)
    out["irr"] = {k: {"ref": V("B", r), "label": lab[r]} for k, r in irr.items()}

    h7 = row(lambda t: t.startswith("7. Probability tree"), "7. Probability tree")
    ev = row(lambda t: t == "Probability-weighted", "Probability-weighted", h7)
    rp, kp = out["primary"]["reward_price"]["row"], out["primary"]["risk_price"]["row"]
    tree = []
    for r, name in a:
        if h7 < r < ev:
            f = str(g.get((r, 2), "")).replace("$", "")
            case = "reward" if f == f"=B{rp}" else ("risk" if f == f"=B{kp}" else None)
            tree.append({"name": name, "target": V("B", r), "ret": V("C", r), "prob": V("D", r), "case": case})
    out["tree"] = tree
    out["tree_ev"] = {"target": V("B", ev), "ret": V("C", ev), "prob": V("D", ev)}
    return out


def multiples(g, kind):
    a = labels(g)
    M = lambda col, r: ref("Multiples", col, r)       # noqa: E731
    hdr = first(a, lambda t: t == "Metric")
    if hdr is None:
        stop("the Multiples ranges table ('Metric' header)", "model-multiples")
    fwd = first(a, lambda t: t.startswith("FORWARD"))
    stop_at = fwd if fwd else hdr + 20
    heads = {str(v).strip(): c for (r, c), v in g.items() if r == hdr and isinstance(v, str)}
    ranges = {}
    for key, test in (("abs", lambda t: t == kind), ("sp", lambda t: "S&P 500" in t),
                      ("peer", lambda t: "core-peer median" in t)):
        r = first(a, test, hdr, stop_at)
        if r is None:
            ranges[key] = None
            continue
        cells = {h: M(L(heads[h]), r) for h in heads if h != "Metric"}
        ranges[key] = {"label": dict(a)[r], "today": cells.get("Today"),
                       **{f"{y} {s}": cells.get(f"{y} {s}") for y in ("1 year", "5 years", "10 years")
                          for s in ("min", "median", "max")}}
    street = {}
    srow = first(a, lambda t: t.startswith("Street EPS"), fwd or 0) if fwd else None
    if srow:
        for (r, c), v in g.items():
            if r == fwd + 1 and c > 1 and isinstance(g.get((srow, c)), (int, float)):
                street[str(v).strip()] = M(L(c), srow)
    adv = None
    th = first(a, lambda t: t == "Ticker")
    if th:
        ac = next((c for (r, c), v in g.items() if r == th and isinstance(v, str) and v.startswith("3M ADV")), None)
        sr = next((r for (r, c), v in g.items() if c == 2 and r > th and v == "Subject"), None)
        if ac and sr and isinstance(g.get((sr, ac)), (int, float)):
            adv = M(L(ac), sr)
    return {"ranges": ranges, "street": street, "adv": adv}


# The Street metrics SUM compares, by the Consensus tab's "<Metric> mean" header: (SUM key, kind, name on SUM).
# A level's delta is ours / Street - 1; a margin's is (ours - Street) x 10000 bps, our margin being the metric over
# revenue. EPS and EBITDA are on the basis street_basis matches. A new model-consensus metric needs only a line here.
STREET_MAP = {"EPS": ("eps", "level", "EPS"), "Rev": ("rev", "level", "revenue"), "EBITDA": ("ebitda", "level", "EBITDA"),
              "Gross margin": ("gm", "margin", "gross margin"), "EBITDA margin": ("ebitda_m", "margin", "EBITDA margin"),
              "Operating margin": ("om", "margin", "operating margin")}
MEAN = re.compile(r"^(.+?) mean(?: \(.*\))?$")


def consensus(g, years):
    """The Consensus tab's latest snapshot as links: {"metrics": {key: {year: {"ref", "n"}}}, "unmapped": [header],
    "snapshot": date}. Every "<Metric> mean" header is read (with its "# <Metric>" count); a STREET_MAP metric becomes
    its key, any other is listed in "unmapped". Only forecast years that are SUM years ("FY 26" or "FY 2026" -> "2026E"),
    only where the mean is a number. None when the tab has no snapshot block or no snapshots (Consensus is optional)."""
    a = labels(g)
    top = first(a, lambda t: t.startswith("5. CONSENSUS SNAPSHOTS"))
    if top is None:
        return None
    heads = {str(v).strip(): c for (r, c), v in g.items() if r == top + 1 and isinstance(v, str)}
    cs, cp = heads.get("Snapshot"), heads.get("Period")
    means = {MEAN.match(h)[1]: c for h, c in heads.items() if MEAN.match(h)}
    if not (cs and cp and means):
        return None
    rows, r = [], top + 2
    while g.get((r, cs)) is not None:
        rows.append((r, str(g[(r, cs)])[:10], str(g.get((r, cp), "")).strip()))
        r += 1
    if not rows:
        return None
    latest = max(d for _, d, _ in rows)
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)         # noqa: E731
    mapped = {k: c for k, c in means.items() if k in STREET_MAP}
    out = {"metrics": {STREET_MAP[k][0]: {} for k in mapped}, "snapshot": latest,
           "unmapped": sorted(f"{k} mean" for k in means if k not in STREET_MAP)}
    for r, d, p in rows:
        m = re.fullmatch(r"(?i)FY\s*(\d{4}|\d{2})", p)
        if d != latest or not m:
            continue
        y = f"{int(m[1]) + (2000 if len(m[1]) == 2 else 0)}E"
        if y not in years:
            continue
        for k, cm in mapped.items():
            if num(g.get((r, cm))):
                cn = heads.get(f"# {k}")
                n = g.get((r, cn)) if cn else None
                out["metrics"][STREET_MAP[k][0]][y] = {"ref": ref("Consensus", L(cm), r), "n": int(n) if num(n) else None}
    out["metrics"] = {k: v for k, v in out["metrics"].items() if v}
    return out


def mod(model):
    """MOD's rows and columns for SUM. EPS and EBITDA are left to street_basis, which picks the basis."""
    mm = ModMap(model)
    R = modrows.find_rows(mm)
    actual = [p for p in mm.order if re.fullmatch(r"\d{4}", p)][-4:]
    years = actual + mm.forecast_years()[:MAX_FORECAST_YEARS]
    fq = mm.forecast_quarters()[:4]
    if len(fq) < 4:
        stop("four forecast quarters in MOD", "model-forecast")
    prev = {}
    for y in years:
        n = int(y[:4]) - 1
        prev[y] = next((p for p in (f"{n}E", str(n)) if p in mm.labels), None)
    col = {p: mm.col(p) for p in set(years) | {p for p in prev.values() if p}}
    refs = [f"MOD!${mm.col(q)}${R['fcf']}" for q in fq]
    return {"years": years, "n_actual": len(actual), "col": col, "prev": prev, "basis": None,
            "rows": {"rev": R["rev"], "gp": R.get("gp"), "oi": R["oi"], "eps": None, "ebitda": None, "fcf": R["fcf"],
                     "eps_gaap": R["eps_gaap"], "eps_ng": R.get("eps_ng"), "ebitda_gaap": [R["oi"], R["da"]],
                     "ebitda_ng": [R["ebitda_ng"]] if "ebitda_ng" in R else None},
            "ntm_fcf": f"IF(COUNT({','.join(refs)})=4,{'+'.join(refs)},NA())", "ntm_quarters": [fq[0], fq[-1]]}


def values(model, refs, work):
    """{ref: value} for sheet-qualified refs. Cached values first (read-only); if any is not a number, a COPY is
    recalculated with LibreOffice into work/basis_values, read, and deleted. The user's file is only ever read."""
    def read(path):
        want = {}
        for x in refs:
            m = re.match(r"^'?([^'!]+)'?!\$([A-Z]+)\$(\d+)$", x)
            want.setdefault(m[1], []).append((x, m[2], int(m[3])))
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            out = {}
            for tab, cells in want.items():
                for x, c, r in cells:
                    out[x] = next(wb[tab].iter_rows(min_row=r, max_row=r, min_col=column_index_from_string(c),
                                                    max_col=column_index_from_string(c), values_only=True))[0]
        finally:
            wb.close()
        return out
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)         # noqa: E731
    got = read(model)
    if all(num(v) for v in got.values()):
        return got, "cached values"
    import shutil
    import lo
    d = os.path.join(work, "basis_values")
    try:
        got = read(lo.recalc(model, d))
    finally:
        shutil.rmtree(d, ignore_errors=True)               # a recalculated copy of the model: never keep it
    return got, "recalculated copy"


BASES = {"auto": "auto", "gaap": "GAAP", "nongaap": "non-GAAP"}


def street_basis(L, model, work, override="auto", warnings=None):
    """Choose the EPS basis the Street uses and point L["mod"]'s eps / ebitda rows at it. Evidence: the first forecast
    year with a Street EPS mean; the candidate (GAAP, non-GAAP if MOD has it) closest to it, by |ours / Street - 1|,
    wins. override ("auto", "GAAP", "non-GAAP", the yellow cell) forces a basis; invalid, or non-GAAP with no MOD row,
    warns and uses auto. No Street EPS: Px Data's P/E basis. Returns {"chosen", "source" (auto / override / px_data),
    "evidence", "auto" (what auto picks), "values_from" (cached values / recalculated copy / None)}."""
    w = warnings if warnings is not None else []
    md, St = L["mod"], L["street"]
    R = md["rows"]
    want = BASES.get(re.sub(r"[\s_-]", "", str(override or "auto")).lower())
    if want is None:
        w.append(f"Street EPS basis holds {override!r}; it takes auto, GAAP or non-GAAP, so auto decided.")
        want = "auto"
    if want == "non-GAAP" and not R["eps_ng"]:
        w.append("Street EPS basis says non-GAAP but MOD has no 'Non-GAAP EPS, Diluted' row (run /model-kpis), "
                 "so auto decided.")
        want = "auto"
    eps = St["metrics"].get("eps", {})
    y = next((y for y in md["years"] if y.endswith("E") and y in eps), None)
    auto, evidence, vfrom = None, None, None
    if y:
        cands = {"GAAP": R["eps_gaap"], **({"non-GAAP": R["eps_ng"]} if R["eps_ng"] else {})}
        refs = {k: f"MOD!${md['col'][y]}${r}" for k, r in cands.items()}
        v, vfrom = values(model, [eps[y]["ref"], *refs.values()], work)
        s, ours = v[eps[y]["ref"]], {k: v[x] for k, x in refs.items()}
        ok = {k: x for k, x in ours.items() if isinstance(x, (int, float)) and not isinstance(x, bool)}
        if isinstance(s, (int, float)) and ok:
            gap = lambda x: abs(x / s - 1) if s else abs(x)                          # noqa: E731
            auto = min(ok, key=lambda k: gap(ok[k]))
            src = f"Consensus {St['snapshot']}" if St["source"] == "consensus" else "Multiples forward table"
            mine = ", ".join(f"{k} {ok[k]:.2f}" if k in ok else f"{k} n/a" for k in ("non-GAAP", "GAAP") if k in ours)
            evidence = (f"Street FY{y[2:4]} EPS {s:.2f} ({src}); ours {mine}"
                        + ("" if R["eps_ng"] else " (MOD has no non-GAAP EPS row)") + f", so {auto}")
        else:
            w.append(f"Street FY{y[2:4]} EPS or our EPS that year is not a number even after recalculation, so the "
                     "basis falls back to Px Data's P/E.")
    if auto is None:
        px = "non-GAAP" if modrows.eps_basis(model) == "ng" else "GAAP"
        if px == "non-GAAP" and not R["eps_ng"] and want != "GAAP":
            stop("MOD's 'Non-GAAP EPS, Diluted' row (Px Data's P/E is non-GAAP)", "model-kpis")
        auto, evidence = px, f"no Street EPS to compare with, so Px Data's P/E basis: {px}"
        source = "px_data"
    else:
        source = "auto"
    chosen = auto
    if want != "auto":
        chosen, source = want, "override"
        if want != auto:
            w.append(f"Street EPS basis is set to {want}, but auto would pick {auto} ({evidence}). SUM compares "
                     f"{want} EPS with the Street as you asked.")
    ng = chosen == "non-GAAP"
    md["basis"] = "ng" if ng else "gaap"
    R["eps"] = R["eps_ng"] if ng else R["eps_gaap"]
    md["ebitda_adj"] = bool(ng and R["ebitda_ng"])
    R["ebitda"] = R["ebitda_ng"] if md["ebitda_adj"] else R["ebitda_gaap"]
    return {"chosen": chosen, "source": source, "evidence": evidence, "auto": auto, "values_from": vfrom}


def collect(model):
    wb = openpyxl.load_workbook(model, read_only=True)
    try:
        missing = [(t, k) for t, k in NEED.items() if t not in wb.sheetnames]
        if missing:
            lines = [f"/{k}" + (" (after /model-forecast)" if t == "DCF" else "") + f" for the {t} tab"
                     for t, k in missing]
            raise SystemExit("model-summary: tabs not found. Run " + "; ".join(lines) + ", in that order, "
                             "then /model-summary.")
        v = valuation(grid(wb["Valuation"]))
        out = {"dcf": dcf(grid(wb["DCF"])), "val": v, "mult": multiples(grid(wb["Multiples"]), v["kind"])}
        cg = grid(wb["Consensus"]) if "Consensus" in wb.sheetnames else None
    finally:
        wb.close()
    out["mod"] = mod(model)
    c = consensus(cg, out["mod"]["years"]) if cg else None
    if c and c["metrics"].get("eps"):
        out["street"] = {"metrics": c["metrics"], "unmapped": c["unmapped"], "source": "consensus",
                         "snapshot": c["snapshot"]}
    else:                                          # Multiples' forward table: EPS only, no revenue, no snapshot date
        eps = {y: {"ref": s, "n": None} for y, s in out["mult"]["street"].items()}
        out["street"] = {"metrics": {"eps": eps} if eps else {}, "unmapped": [], "source": "multiples",
                         "snapshot": None}
    return out
