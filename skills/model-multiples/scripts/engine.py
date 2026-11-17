"""Assembles the numbers the Multiples tab must show (spec §3.3). build.py writes the same thing as formulas;
verify.py checks the recalculated tab against these values."""
import bisect

import importer
import multiples as M
import peers as P

KEYS = ("pe", "ev_ebitda", "ev_gp", "ev_rev", "fcf_yield", "rel_sp", "rel_peer")
WINDOWS = (52, 260, 520)          # 1, 5 and 10 years of weekly rows


def _asof(dates, day, strict):
    i = (bisect.bisect_left if strict else bisect.bisect_right)(dates, day)
    return i - 1 if i else None


def peer_pe(peer, day):
    px = P.close_on(peer["closes"], day)
    k = _asof([t["known"] for t in peer["ttm"]], day, strict=False)
    eps = peer["ttm"][k]["ttm"] if k is not None else None
    return px, M.ratio(px, eps)


def free_weekly(quarters, weeks, sp, peers):
    """One row per week. quarters: subject.quarters(); weeks: subject.weekly(); sp: sp500 rows; peers:
    {T: {"closes": [(date, close)], "ttm": peers.ttm(...)}}."""
    qd = [q["date"] for q in quarters]
    sd = [s["date"] for s in sp]
    out = []
    for d, price, pxrow, pxcol in weeks:
        k = _asof(qd, d, strict=True)                    # known the day after release (MATCH(date-1, dates, 1))
        q = quarters[k] if k is not None else None
        v = (lambda key: q[key][0] if q else None)
        row = {"date": d, "price": price, "pxrow": pxrow, "pxcol": pxcol, "q": k,
               **{key: v(key) for key in ("rev", "gp", "ebitda", "eps", "eps_gaap", "fcf", "shares", "net_debt")}}
        row.update(M.six(price, row["shares"], row["net_debt"], row["rev"], row["gp"], row["ebitda"], row["eps"],
                         row["fcf"]))
        # The relative rows are GAAP vs GAAP: multpl's S&P P/E and the peers' XBRL EPS are reported earnings.
        row["pe_gaap"] = M.ratio(price, row["eps_gaap"])
        j = _asof(sd, d, strict=False)
        row["sp_pe"] = sp[j]["pe"] if j is not None else None
        row["rel_sp"] = row["pe_gaap"] - row["sp_pe"] if row["pe_gaap"] is not None and row["sp_pe"] is not None else None
        pp = {t: peer_pe(p, d) for t, p in peers.items()}
        row["peer_px"] = {t: x[0] for t, x in pp.items()}
        row["peer_pe"] = {t: x[1] for t, x in pp.items()}
        row["peer_med"] = M.median_or_none(row["peer_pe"].values())
        row["rel_peer"] = (row["pe_gaap"] - row["peer_med"] if row["pe_gaap"] is not None and row["peer_med"] is not None
                           else None)
        out.append(row)
    return out


def paid_weekly(rows, peer_rows):
    """rows: importer.load() for the subject; peer_rows: {T: importer.load()}. Same keys as free_weekly.
    Note: "eps" here is NTM consensus, where free_weekly's is TTM as reported. The tab labels the basis. The relative
    rows stay NTM vs NTM: one vendor's consensus is consistent across subject, peers and the S&P."""
    pdates = {t: [x["date"] for x in pr] for t, pr in peer_rows.items()}
    out = []
    for r in rows:
        m = importer.multiples(r)
        row = {**r, **m, "eps": r.get("eps_ntm")}
        row["sp_pe"] = r.get("sp500_pe")
        row["rel_sp"] = row["pe"] - row["sp_pe"] if row["pe"] is not None and row["sp_pe"] is not None else None
        row["peer_px"], row["peer_eps"], row["peer_pe"] = {}, {}, {}
        for t, pr in peer_rows.items():
            k = _asof(pdates[t], r["date"], strict=False)
            x = pr[k] if k is not None else {}
            row["peer_px"][t], row["peer_eps"][t] = x.get("price"), x.get("eps_ntm")
            row["peer_pe"][t] = M.ratio(x.get("price"), x.get("eps_ntm"))
        row["peer_med"] = M.median_or_none(row["peer_pe"].values())
        row["rel_peer"] = row["pe"] - row["peer_med"] if row["pe"] is not None and row["peer_med"] is not None else None
        out.append(row)
    return out


def ranges(rows, windows=WINDOWS, keys=KEYS):
    """keys: KEYS, plus "fcf_yield_ntm" on the paid path (an export's NTM FCF; the free path has no forward history)."""
    return {k: {n: M.window_stats([r.get(k) for r in rows], n) for n in windows} for k in keys}


def reverse(rows, rg):
    """Price today / the window's min, median and max P/E: the earnings power the market is implying."""
    price = rows[-1]["price"]
    return {n: ({s: M.reverse_pe(price, rg["pe"][n][s]) for s in ("min", "median", "max")} if rg["pe"][n] else None)
            for n in rg["pe"]}
