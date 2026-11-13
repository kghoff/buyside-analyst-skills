"""Turn peers.json + every source into W/industry.json: one value per company, line and calendar year, each with
how it is written (link / typed / est) and its note. build.py and compute.py read only industry.json.

usage: python3 assemble.py --work W --model M.xlsx
Sources: subject = MOD links; "model" = the peer's own research model (typed, note names the cell); "xbrl" = the
XBRL engine (typed, note names the tags). Segment peers: the parent's consolidated lines go in `parent`; the
segment's own lines are the checked segment figures (W/segments.json), and every other input line is estimated as
parent x (segment revenue / parent revenue) that year (house default). Foreign filers: a company's
"fx" {fy: USD per unit} multiplies every value (typed by the agent, with its source in "fx_source").
A company's "overrides" {line: {fiscal year: {"v": $M as reported, "note": source}}} replace consolidated values
(an XBRL figure that is wrong) before calendar mapping; they are typed with that note."""
import argparse
import json
import os

import fiscal
import lines
import lo
import sources

N_YEARS = 10
CORE = ("revenue", "oi", "pretax", "net_income", "cfo", "capex", "total_assets")   # every filer reports these


def _mod(path, work, tag):
    m = sources.mod_read(path)
    if m["missing_cache"]:
        calc = lo.recalc(path, os.path.join(work, "_recalc", tag))
        m = sources.mod_read(path, calc)
    return m


def _consolidated(c, F, work):
    """{line: {fy: (value, note, formula)}} for the whole company."""
    T = c["ticker"].upper()
    out = {k: {} for k in lines.INPUTS}
    if c["source"] in ("mod", "model"):
        path = c.get("model") if c["source"] == "model" else c["_subject_model"]
        m = _mod(os.path.expanduser(path), work, T)
        for k in lines.INPUTS:
            for fy, v in m["values"][k].items():
                if v is not None:
                    out[k][fy] = (v, f"{os.path.basename(path)} {m['formula'][k][fy]} ({' + '.join(m['labels'][k])})",
                                  m["formula"][k][fy])
        return out, sorted(m["fy_cols"])
    d = json.load(open(F[T]["xbrl"]))
    vals, tags = lines.from_xbrl(d)
    for k in lines.INPUTS:
        for fy, v in vals[k].items():
            if v is not None:
                out[k][fy] = (v, f"SEC XBRL {tags[k][fy]}, FY{fy} 10-K", None)
    return out, sorted(int(y) for y in d["annual"]["income"])


def _sanity(T, cons, cal, years):
    """Warnings for consolidated figures that are probably an XBRL mistake (check them against the 10-K)."""
    out, rev, cogs = [], {fy: x[0] for fy, x in cons["revenue"].items()}, {fy: x[0] for fy, x in cons["cogs"].items()}
    for fy in sorted(rev):
        if cal.get(fy) not in years:
            continue
        if rev[fy] and fy in cogs and (rev[fy] + cogs[fy]) / rev[fy] < -1:
            out.append(f"{T} FY{fy}: gross margin {(rev[fy] + cogs[fy]) / rev[fy]:.0%} is below -100%; "
                       "check against the 10-K")
        p = rev.get(fy - 1)
        if p and rev[fy] and p > 0 and rev[fy] > 0 and not 1 / 3 <= rev[fy] / p <= 3:
            out.append(f"{T} FY{fy}: revenue {rev[fy]:,.1f} vs {p:,.1f} the year before (more than 3x); "
                       "check against the 10-K")
    return out


def assemble(P, model, work):
    F = json.load(open(os.path.join(work, "fetch.json")))
    seg = json.load(open(os.path.join(work, "segments.json"))) if os.path.exists(os.path.join(work, "segments.json")) else {}
    companies, warnings, years, gaps = [], [], None, {}
    first = (P.get("companies") or [{}])[0]
    if first.get("source") != "mod" or first.get("ticker", "").upper() != P.get("subject", "").upper():
        raise SystemExit(f"peers.json: the first company must be the subject {P.get('subject')} with \"source\": "
                         f"\"mod\" (its years set the 10-year window); found {first.get('ticker')} "
                         f"({first.get('source')}). Move the subject to the top and rerun.")
    for c in P["companies"]:
        c = dict(c)
        T = c["ticker"].upper()
        c["_subject_model"] = model
        sec = json.load(open(F[T]["sec"]))
        cons, fys = _consolidated(c, F, work)
        for k, by_fy in (c.get("overrides") or {}).items():
            for fy_s, o in by_fy.items():
                cons[k][int(fy_s)] = (o["v"], f"Override: {o['note']}", None)
        ends = fiscal.fy_ends(sec, fys)
        cal = {fy: fiscal.calendar_year(ends[fy]) for fy in fys}
        for a, b in zip(fys, fys[1:]):
            if cal[a] == cal[b]:
                warnings.append(f"{T}: FY{a} (ends {ends[a]}) and FY{b} (ends {ends[b]}) both count as {cal[b]}; "
                                f"FY{b} is used, FY{a} is dropped (fiscal year end changed?)")
        gaps[T] = {cal[fy]: [k for k in CORE if fy not in cons[k]] for fy in cons["revenue"]}
        fx = {int(k): v for k, v in (c.get("fx") or {}).items()}
        conv = lambda fy, v: v * fx[fy] if fx else v
        if c["source"] == "mod":
            years = sorted(cal[fy] for fy in fys)[-N_YEARS:]
        else:
            warnings += _sanity(T, cons, cal, years)
        fymap = {str(cal[fy]): fy for fy in fys}
        L, parent = {}, None
        if not c.get("segment"):
            for k in lines.INPUTS:
                L[k] = {}
                for fy, (v, note, f) in cons[k].items():
                    if c["source"] == "mod" and f:
                        L[k][str(cal[fy])] = {"v": v, "kind": "link", "f": f, "note": ""}
                    else:
                        L[k][str(cal[fy])] = {"v": conv(fy, v), "kind": "typed", "note": note}
        else:
            parent = {k: {str(cal[fy]): {"v": conv(fy, v), "kind": "typed", "note": note}
                          for fy, (v, note, f) in cons[k].items()} for k in lines.INPUTS}
            S = seg.get(T, {})
            srev = {}
            for k in lines.SEGMENT_LINES:
                for fy_s, e in S.get(k, {}).items():
                    fy = int(fy_s)
                    if fy not in cal:
                        continue
                    L.setdefault(k, {})[str(cal[fy])] = {
                        "v": conv(fy, e["value"]), "kind": "typed",
                        "note": f"{T} 10-K segment note: {os.path.basename(e['file'])} line {e['line_no']}: '{e['quote']}'"}
            srev = {y: x["v"] for y, x in L.get("revenue", {}).items()}
            for y, sv in srev.items():
                pv = parent["revenue"].get(y, {}).get("v")
                if not pv:
                    warnings.append(f"{T} {y}: segment revenue but no parent revenue; no estimates that year")
                    continue
                share = sv / pv
                if share > 1:
                    warnings.append(f"{T} {y}: segment revenue {sv:,.0f} is more than the parent's {pv:,.0f}")
                prev = srev.get(str(int(y) - 1))
                ppv = parent["revenue"].get(str(int(y) - 1), {}).get("v")
                if prev and ppv and abs(share - prev / ppv) > 0.15:
                    warnings.append(f"{T} {y}: segment share moved from {prev / ppv:.0%} to {share:.0%} "
                                    "(segment redefined?)")
                for k in lines.INPUTS:
                    if y in L.get(k, {}) or y not in parent[k]:
                        continue
                    L.setdefault(k, {})[y] = {"v": parent[k][y]["v"] * share, "kind": "est",
                                              "note": f"= {T} consolidated {lines.LABEL[k]} {parent[k][y]['v']:,.1f} x "
                                                      f"{c['segment']} share of revenue {share:.1%}"}
        fy_text = ("fiscal year = calendar year" if all(str(cal[fy]) == str(fy) for fy in fys)
                   else "fiscal years mapped: " + ", ".join(f"FY{fy} (ends {ends[fy]}) -> {cal[fy]}"
                                                            for fy in fys[-3:]) + " ...")
        src = {"mod": "linked to MOD", "model": f"from {os.path.basename(c.get('model', ''))}",
               "xbrl": "SEC XBRL"}[c["source"]]
        header = f"{c['name']} ({T})" + (f": {c['segment']} segment" if c.get("segment") else "") + \
                 f"; {src}; {fy_text}" + (f"; {c['caveat']}" if c.get("caveat") else "") + \
                 (f"; converted to USD ({c.get('fx_source', '')})" if fx else "")
        companies.append({"ticker": T, "name": c["name"], "role": "subject" if c["source"] == "mod" else "peer",
                          "source": c["source"], "segment": c.get("segment"), "header": header, "lines": L,
                          "parent": parent, "fy_map": fymap})
    for T, g in gaps.items():
        miss = {y: ks for y, ks in sorted(g.items()) if ks and y in years}
        if miss:
            warnings.append(f"{T}: input lines missing where revenue exists: " +
                            "; ".join(f"{y} {', '.join(ks)}" for y, ks in miss.items()))
    for co in companies:
        for part in (co["lines"], co["parent"] or {}):
            for k in part:
                part[k] = {y: x for y, x in part[k].items() if int(y) in years}
    return {"subject": P["subject"], "industry": P["industry"], "years": years, "companies": companies,
            "excluded": P.get("excluded", []), "warnings": warnings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--model", required=True)
    a = ap.parse_args()
    I = assemble(json.load(open(os.path.join(a.work, "peers.json"))), a.model, a.work)
    json.dump(I, open(os.path.join(a.work, "industry.json"), "w"), indent=1)
    est = {c["ticker"]: sum(1 for k in c["lines"] for x in c["lines"][k].values() if x["kind"] == "est")
           for c in I["companies"]}
    print(json.dumps({"years": [I["years"][0], I["years"][-1]], "estimated_cells": est, "warnings": I["warnings"]},
                     indent=1))


if __name__ == "__main__":
    main()
