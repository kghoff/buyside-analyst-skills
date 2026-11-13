"""KPI step 1 - leads for finding every company-specific metric a buy-side modeler tracks (RPO, ARPU, subscribers,
organic growth, backlog, same-store sales, installed base, procedure volumes...). Discovery is Claude's judgment;
this narrows what to read. Nothing here decides what the metrics are.

usage: python3 kpi_scan.py --src <source folder> --model <model.xlsx> --work <work_dir>

Writes <work>/kpi_leads.md and <work>/kpi_docs.json:
  1. reading list: newest 10-K (with the line where MD&A / key metrics start), newest releases, decks, calls, events
  2. definition passages: where the company says what it measures ("key metrics", "we define", "we use ... to evaluate")
  3. recurring table rows with numbers in 3+ periods that are not already a MOD row or a reconciliation line
  4. a cross-industry KPI lexicon: how many periods mention each term next to a number, with an example line"""
import argparse, json, os, re
import openpyxl
from mdtable import table_rows
from ng_extract import discover, clean
from xlmodel import norm

# broad on purpose: Claude drops what doesn't apply. (name, regex)
LEXICON = [
    ("remaining performance obligations / RPO", r"remaining performance obligations?|\bc?rpo\b"),
    ("annual recurring revenue / ARR", r"annual(ized)? recurring revenue|\barr\b"),
    ("net revenue / dollar retention", r"net (revenue|dollar|expansion) retention|\bn[dr]r\b|dollar.based net"),
    ("gross retention / churn", r"gross retention|\bchurn\b"),
    ("customers / accounts", r"\b(paying )?customers?\b.{0,40}\b(over|more than|exceed|grew|total)|customer count|number of customers"),
    ("large customers (> $X)", r"customers? (with|contributing|spending).{0,30}(\$|million|thousand)"),
    ("billings / bookings", r"\bbillings\b|\bbookings\b|\bcalculated billings\b"),
    ("backlog / book-to-bill / orders", r"\bbacklog\b|book.to.bill|\borders?\b.{0,20}(grew|increased|declined|of \$)|order intake"),
    ("subscribers / members / users", r"\b(paid |paying )?(subscribers?|memberships?|paid subscriptions)\b|\b(monthly|daily|weekly) active (users|uniques)\b|\b[dmw]au\b|members (grew|increased|totaled|reached)"),
    ("ARPU / ARPM / ARPA", r"\barp[aum]{1,2}\b|average revenue per"),
    ("installed base / users of a device", r"installed base|\busers? (base|worldwide|globally)\b|\bpatients? on\b"),
    ("procedures / utilization / volumes", r"procedure volumes?|procedures (grew|increased|declined|performed)|utilization (rate|grew|increased|declined)|\bvolumes? (grew|increased|declined)"),
    ("organic / constant-currency growth", r"organic(ally)? (revenue )?(growth|grew|increase)|constant.currency|currency.neutral|ex.fx|excluding (foreign )?currency"),
    ("same-store / comparable sales", r"same.store sales|comparable (store )?sales|like.for.like"),
    ("traffic / transactions / ticket", r"\btraffic\b|average (ticket|check|order value)|\baov\b|transactions? (grew|increased|count)"),
    ("store / unit / location count", r"(stores|restaurants|locations|units|clubs|branches) (open|opened|at (quarter|year).end)|net (new )?(store|unit) (openings|growth)"),
    ("GMV / TPV / take rate", r"gross merchandise|\bgmv\b|total payment volume|\btpv\b|take rate"),
    ("units shipped / ASP", r"units? shipped|shipments|average selling price|\basps?\b"),
    ("gross / net adds", r"(gross|net) (adds|additions)\b"),
    ("pipeline / design wins", r"design wins?|\bpipeline\b.{0,20}\$"),
    ("RevPAR / ADR / occupancy", r"revpar|\badr\b|average daily rate|occupancy"),
    ("ASMs / RASM / CASM / load factor", r"available seat miles|\b[rc]asm\b|load factor"),
    ("NIM / deposits / loans / AUM / flows", r"net interest margin|total deposits|loans held for investment|assets under (management|administration)|\bau[ma]\b|net (in)?flows"),
    ("premiums / combined ratio / loss ratio", r"(net|gross) (premiums )?written|combined ratio|loss ratio|policies in force"),
    ("production / reserves / realized price", r"\bboe(/d)?\b|barrels per day|\bmmcfe?\b|proved reserves|realized (oil |gas )?price"),
    ("same-store NOI / FFO / leasing", r"same.(store|property) noi|\baffo\b|\bffo\b|leasing spreads|percent leased"),
    ("headcount / employees / sales reps", r"headcount|(full.time )?employees (at|as of|totaled|of approximately)|approximately [\d,]+ (full.time )?employees|sales (reps|representatives) (grew|of)"),
    ("segment / geography growth", r"(international|u\.s\.|us|domestic|emea|apac|china) (revenue|sales) (grew|increased|declined|growth)"),
    ("mix / penetration / attach", r"\bmix\b.{0,30}%|penetration|attach rate"),
    ("gross margin guidance-type ratios", r"(gross|operating) margin (expansion|of approximately|guidance)"),
]

DEFINE = re.compile(r"key (operating|performance|business|financial) (metrics|indicators|measures)|we define |is defined as |"
                    r"we (use|track|monitor|believe) .{0,80}(metrics?|measures?|indicators?)|operating metrics", re.I)
NUM = re.compile(r"\d[\d,]*\.?\d*\s*(%|percent|million|billion|thousand|bps|basis points|x\b)?", re.I)


def has_number(line):
    for m in NUM.finditer(line):
        t = m.group(0).strip(); v = t.split()[0].rstrip("%").replace(",", "")
        try: x = float(v)
        except ValueError: continue
        if m.group(1) or "." in v or (x >= 10 and not re.fullmatch(r"(19|20)\d\d", v)): return True
    return False


def doc_date(path):
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", os.path.basename(path))
    return m.group(0) if m else None


def newest_key(d):
    p = d["period"]
    if p: return (2000 + int(p[3:]), 5 if p.startswith("FY") else int(p[1]), doc_date(d["path"]) or "")
    dd = doc_date(d["path"]) or "0000-00-00"
    return (int(dd[:4]), int(dd[5:7]) / 3, dd)


def model_labels(path):
    wb = openpyxl.load_workbook(path, read_only=True); ws = wb["MOD"] if "MOD" in wb.sheetnames else wb.worksheets[0]
    out = set()
    for row in ws.iter_rows(min_col=2, max_col=2):
        v = norm(row[0].value)
        if v: out.add(re.sub(r"^\(?[-+/ ]*\)?\s*", "", v).strip(": "))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--model", required=True); ap.add_argument("--work", required=True)
    a = ap.parse_args(); os.makedirs(a.work, exist_ok=True)
    docs, _ = discover(a.src)
    for d in docs: d["date"] = doc_date(d["path"]); d["rel"] = os.path.relpath(d["path"], a.src)
    json.dump(docs, open(os.path.join(a.work, "kpi_docs.json"), "w"), indent=1)
    texts = {d["path"]: open(d["path"], encoding="utf-8", errors="ignore").read() for d in docs}
    newest = lambda t, n: sorted([d for d in docs if d["type"] == t], key=newest_key, reverse=True)[:n]
    when = lambda d: d["period"] or d["date"] or "undated"

    # 1. reading list
    reading = []
    for d in newest("10-K", 1):
        L = texts[d["path"]].split("\n")
        marks = [(i + 1, l.strip()[:90]) for i, l in enumerate(L) if re.search(r"^#*\s*item\s*7\b|management.s discussion|key (operating|performance|business) (metrics|indicators)", l, re.I)]
        reading.append((d, "business, MD&A and any key-metrics section" + (": lines " + ", ".join(str(n) for n, _ in marks[:6]) if marks else "")))
    for t, n, why in [("release", 4, "headline metrics and tables"), ("deck", 4, "KPI slides"), ("call", 4, "metrics management keeps citing"),
                      ("event", 2, "long-term targets, metrics defined for investors"), ("recast", 2, "re-segmented history")]:
        reading += [(d, why) for d in newest(t, n)]

    # 2. definition passages (newest first, unique text)
    defs, seen = [], set()
    for d in sorted(docs, key=newest_key, reverse=True):
        for i, l in enumerate(texts[d["path"]].split("\n")):
            if DEFINE.search(l):
                k = re.sub(r"\W+", " ", l.lower())[:160]
                if k in seen: continue
                seen.add(k); defs.append((d, i + 1, l.strip()))
    # 3. recurring table rows outside the model and the reconciliations
    known = model_labels(a.model); in_model = sorted(known)
    cpath = os.path.join(a.work, "candidates.json")
    if os.path.exists(cpath):
        for c in json.load(open(cpath))["candidates"]:
            for lab in [c.get("start_label"), c.get("end_label"), c.get("label")] + [x[0] for x in c.get("items", [])]:
                if lab: known.add(norm(lab))
    # statement lines (balance sheet, cash flow, notes) recur in most 10-Qs; KPI tables live in releases / decks / events
    tenq = [d for d in docs if d["type"] == "10-Q"]; inq = {}
    for d in tenq:
        for k in {norm(clean(lab)).strip(": ") for _, lab, v in table_rows(texts[d["path"]]) if v}: inq[k] = inq.get(k, 0) + 1
    known |= {k for k, n in inq.items() if n >= max(2, len(tenq) // 4)}
    rows = {}
    for d in docs:
        if d["type"] not in ("release", "deck", "event", "recast"): continue
        for ln, lab, v in table_rows(texts[d["path"]]):
            if not v: continue
            k = norm(clean(lab)).strip(": ")
            if not k or len(k) < 3 or k in known or re.sub(r"^\(?[-+/ ]*\)?\s*", "", k) in known: continue
            rows.setdefault(k, {"periods": set(), "types": set(), "ex": None})
            r = rows[k]; r["periods"].add(when(d)); r["types"].add(d["type"])
            if r["ex"] is None or newest_key(d) > newest_key(r["ex"][0]): r["ex"] = (d, ln, v[:4])
    rec = sorted(((k, r) for k, r in rows.items() if len(r["periods"]) >= 3), key=lambda kv: -len(kv[1]["periods"]))
    # 4. lexicon
    lex = []
    for name, pat in LEXICON:
        rx = re.compile(pat, re.I); pers, types, ex = set(), set(), None
        for d in docs:
            for i, l in enumerate(texts[d["path"]].split("\n")):
                m = rx.search(l)
                if not m: continue
                win = l[max(0, m.start() - 160): m.end() + 160]            # the number has to be near the term
                if not has_number(win): continue
                pers.add(when(d)); types.add(d["type"])
                if ex is None or newest_key(d) > newest_key(ex[0]): ex = (d, i + 1, win.strip())
        if pers: lex.append((name, pers, types, ex))
    lex.sort(key=lambda x: -len(x[1]))

    def ref(d, ln): return f"`{d['rel']}` line {ln}"
    with open(os.path.join(a.work, "kpi_leads.md"), "w") as f:
        f.write(f"# KPI leads\n\nSource folder: {a.src} ({len(docs)} Markdown files). These are leads, not answers: read the documents.\n\n")
        f.write("## 0. Already in the model (MOD column B; don't duplicate these)\n\n" + "; ".join(in_model) + "\n\n")
        f.write("## 1. Reading list (newest first)\n\n" + "\n".join(f"- [{d['type']} {when(d)}] `{d['rel']}`: {why}" for d, why in reading) + "\n\n")
        f.write(f"## 2. Where the company defines what it measures ({len(defs)} passages; newest 60)\n\n")
        f.write("\n".join(f"- {ref(d, ln)} [{when(d)}]: {l[:400]}" for d, ln, l in defs[:60]) + "\n\n")
        f.write(f"## 3. Recurring table rows not in the model or the reconciliations ({len(rec)} with 3+ periods; top 120)\n\n")
        f.write("| row label | periods | document types | newest example |\n|---|---|---|---|\n")
        f.write("".join(f"| {k} | {len(r['periods'])} | {', '.join(sorted(r['types']))} | {ref(r['ex'][0], r['ex'][1])}: {r['ex'][2]} |\n" for k, r in rec[:120]) + "\n")
        f.write("## 4. KPI lexicon hits (term next to a number)\n\n| term | periods | document types | newest example |\n|---|---|---|---|\n")
        f.write("".join(f"| {n} | {len(p)} | {', '.join(sorted(t))} | {ref(e[0], e[1])}: {e[2][:300].replace('|', '/')} |\n" for n, p, t, e in lex) + "\n")
    print(f"kpi leads: {len(reading)} documents to read, {len(defs)} definition passages, {len(rec)} recurring table rows, {len(lex)} lexicon terms with hits")


if __name__ == "__main__":
    main()
