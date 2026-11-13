"""Step 2 - look for the things that must never be handled silently.

usage: python3 diagnose.py --src <source folder> --work <work_dir>

Reads <work>/filings.json (from extract.py) and the 10-K markdown, writes <work>/diagnostics.md with:
  A. SEGMENT CHANGES      -> STOP and ask the user (always)
  B. STOCK SPLITS         -> detected from restated share counts; suggests a decisions.json entry
  C. RESTATEMENTS         -> later filings showing different numbers for an already-reported period
  D. ACCOUNTING CHANGES   -> ASUs each 10-K says were adopted (read the note for any flagged in C)
  E. STATEMENT STRUCTURE  -> income-statement lines that appear / disappear between 10-Ks"""
import argparse, json, os, re
from extract import map_is, map_bs, map_cf, tot, discover, norm


def shifted(rows, k):
    return [(lab, v[k:]) for lab, v in rows]


def prev_key(key):
    if key.startswith("FY"):
        return {"IS": f"FY {int(key[3:]) - 1:02d}", "BS": f"FY {int(key[3:]) - 1:02d}", "CF": f"FY {int(key[3:]) - 1:02d}"}
    q, yy = key[:2], int(key[3:])
    return {"IS": f"{q} {yy - 1:02d}", "BS": f"FY {yy - 1:02d}", "CF": f"{q} {yy - 1:02d}"}


def summary(t, k=0):
    I, Ic = map_is(shifted(t["IS"], k), []); B, Bc = map_bs(shifted(t["BS"], k), []); C, Cc = map_cf(shifted(t["CF"], k), [])
    return {"IS": {"Revenue": tot(I, "REV"), "Cost of sales": tot(I, "COGS"), "Operating income": Ic.get("OI"),
                   "Net income": Ic.get("NI"), "Shares basic": Ic.get("SB"), "Shares diluted": Ic.get("SD")},
            "BS": {"Total assets": Bc.get("TA"), "Total liabilities": Bc.get("TL"), "Equity": tot(B, "EQ"), "Cash": tot(B, "CASH")},
            "CF": {"CFO": Cc.get("CFO"), "CFI": Cc.get("CFI"), "CFF": Cc.get("CFF")}}


def order(key):
    return (int(key[3:]), 5 if key.startswith("FY") else int(key[1]))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--src", required=True); ap.add_argument("--work", required=True)
    a = ap.parse_args()
    raw = json.load(open(os.path.join(a.work, "filings.json")))
    orig = {k: summary(v["tables"]) for k, v in raw.items() if set(v["tables"]) == {"IS", "BS", "CF"}}
    restate, splits = [], []
    for key in sorted(raw, key=order):
        t = raw[key]["tables"]
        if set(t) != {"IS", "BS", "CF"}: continue
        try: comp = summary(t, 1)
        except Exception: continue
        pk = prev_key(key)
        for st in ("IS", "BS", "CF"):
            o = orig.get(pk[st], {}).get(st)
            if not o: continue
            for item, nv in comp[st].items():
                ov = o.get(item)
                if nv is None or ov is None: continue
                if item.startswith("Shares"):
                    if ov and nv / ov > 1.5 or ov and nv / ov < 0.67:
                        splits.append((key, pk[st], item, ov, nv, nv / ov))
                    continue
                if abs(nv - ov) > max(0.2, 0.005 * abs(ov)):
                    restate.append((pk[st], item, ov, nv, key))
    # segments: what each 10-K says about reportable segments
    files = discover(a.src)
    seg = []
    for k in sorted(x for x in files if x[0] == "10-K"):
        txt = open(files[k][0], encoding="utf-8", errors="ignore").read()
        hits = re.findall(r"[^.|]{0,120}\b(?:reportable|operating) segments?\b[^.|]{0,80}", txt, re.I)
        syn = {"single": "one", "1": "one", "2": "two", "3": "three", "4": "four"}
        nums = sorted({syn.get(m.lower(), m.lower()) for h in hits for m in re.findall(r"\b(one|single|two|three|four|five|six|seven|\d+)\s+(?:reportable\s+|operating\s+)?segments?\b", h, re.I)})
        seg.append((k[1], nums, (hits[0].strip()[:160] if hits else "(no segment language found)")))
    seg_change = len({tuple(n) for _, n, _ in seg if n}) > 1
    recasts = os.path.isdir(os.path.join(a.src, "Segment Recasts")) and any(
        f.endswith(".md") for _, _, fs in os.walk(os.path.join(a.src, "Segment Recasts")) for f in fs)
    # accounting standards each 10-K says were adopted
    asu = {}
    for k in sorted(x for x in files if x[0] == "10-K"):
        txt = open(files[k][0], encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r"[^.]{0,200}ASU (?:No\. )?(20\d\d-\d\d)[^.]{0,200}", txt):
            s = m.group(0)
            if re.search(r"\bwe adopted|\bour adoption|upon (the )?adoption|adopted (ASU|the|this|on|as of|in|effective|using)|adoption of ASU[^.]{0,60}\b(on|as of|in the|effective)\b", s, re.I) \
                    and not re.search(r"not yet|will adopt|evaluating|considering|is effective for|early adoption is permitted|may adopt", s, re.I):
                asu.setdefault(m.group(1), {}).setdefault(k[1], re.sub(r"\s+", " ", s.strip())[:220])
    # income-statement structure changes between 10-Ks
    labels = {}
    for key, v in raw.items():
        if key.startswith("FY") and "IS" in v["tables"]:
            labels[int(key[3:])] = {norm(l) for l, vals in v["tables"]["IS"] if vals and "per share" not in norm(l) and not norm(l).startswith("shares")}
    struct = []
    ys = sorted(labels)
    for y0, y1 in zip(ys, ys[1:]):
        add, rem = labels[y1] - labels[y0], labels[y0] - labels[y1]
        if add or rem: struct.append((y1, sorted(add), sorted(rem)))

    with open(os.path.join(a.work, "diagnostics.md"), "w") as f:
        f.write("# Diagnostics\n\n## A. Segments (any change = STOP and ask the user)\n\n")
        f.write(f"**{'POSSIBLE SEGMENT CHANGE - STOP AND ASK' if seg_change or recasts else 'No change detected'}**"
                + (" (Segment Recasts folder has files)" if recasts else "") + "\n\n| 10-K | segment counts mentioned | first mention |\n|---|---|---|\n")
        for y, n, h in seg: f.write(f"| {y} | {', '.join(n) or '-'} | {h} |\n")
        f.write("\n## B. Stock splits (share counts restated in later filings)\n\n")
        if not splits: f.write("None detected.\n")
        else:
            first = min(splits, key=lambda s: order(s[0]))
            f.write("| Restated in | Period | Item | Originally | Restated | Ratio |\n|---|---|---|---|---|---|\n")
            for s in sorted(splits, key=lambda s: order(s[0]))[:12]:
                f.write(f"| {s[0]} | {s[1]} | {s[2]} | {s[3]} | {s[4]} | {s[5]:.2f}x |\n")
            prior = sorted([k for k in raw if order(k) < order(first[0])], key=order)
            through = [k for k in prior if not k.startswith("FY")][-1] if prior else "?"
            f.write(f"\nFirst filing with split-adjusted comparatives: **{first[0]}** (ratio {first[5]:.2f}x). Every period whose own filing came "
                    f"before it needs its share counts multiplied. Suggested decisions.json entry:\n\n"
                    f"```json\n\"share_splits\": [{{\"through_period\": \"{through}\", \"factor\": {round(first[5])}, \"note\": \"<n>-for-1 split; pre-split share counts multiplied so EPS is comparable\"}}]\n```\n")
        f.write("\n## C. Restatements / reclassifications (a later filing shows different numbers for a period)\n\n")
        if not restate: f.write("None detected.\n")
        else:
            f.write("Default policy: keep each period **as originally filed** (internally consistent quarters). Decide case by case and log it.\n\n"
                    "| Period | Item | As originally filed | In later filing | Later filing |\n|---|---|---|---|---|\n")
            for r in restate: f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |\n")
        f.write("\n## D. Accounting standards each 10-K says were adopted\n\nRead the 'Recently adopted' note for any ASU that lines up with a restatement in C.\n\n| ASU | 10-K years mentioning adoption | snippet |\n|---|---|---|\n")
        for k, v in sorted(asu.items()):
            y0 = min(v); f.write(f"| {k} | {', '.join(map(str, sorted(v)))} | {v[y0]} |\n")
        f.write("\n## E. Income-statement line changes between 10-Ks\n\n")
        for y, add, rem in struct: f.write(f"- **{y}**: added {add or '-'}; removed {rem or '-'}\n")
    print(f"segment change: {seg_change or recasts} | splits flagged: {len(splits)} | restated items: {len(restate)} | ASUs: {len(asu)} | IS structure changes: {len(struct)}")


if __name__ == "__main__":
    main()
