"""Step 1 - extract the three statements from every 10-K / 10-Q (markdown) and map each line to a model role.

usage: python3 extract.py --src <source folder> --work <work_dir> [--decisions decisions.json]

Writes <work>/periods.json      every period's mapped values (with filing labels, so nothing is anonymous)
       <work>/filings.json      raw parsed rows (all columns) per filing - used by diagnose.py
       <work>/extract_report.md tie-out of every filing to its own subtotals + every non-obvious mapping
Exit code 1 if any filing fails to tie to its own subtotals (fix that before building)."""
import argparse, glob, json, os, re, sys
from mdtables import find_tables, shares_from_release

TOL = 0.15  # $M; filings round to 0.1
NI_RE = r"net \(?(income|loss|earnings)\)?( \(?(loss|income)\)?)?( attributable to [a-z .,'&-]+)?"
NI_START = r"net \(?(income|earnings|loss)"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("’", "'")).strip().lower()


# ------------------------------------------------------------------ locate filings
def discover(src):
    """-> {("10-K", fy) | ("10-Q", fy, q) | ("Q4PR", fy): [md paths]} ; fy is 4-digit fiscal year from the file label"""
    found = {}
    man = os.path.join(src, "_manifest.json")
    paths = []
    if os.path.exists(man):
        m = json.load(open(man))
        for it in m.get("items", {}).values():
            for f in it.get("files", []):
                if f.endswith(".md"):
                    paths.append(os.path.join(src, f))
    paths += glob.glob(os.path.join(src, "**", "_md", "*.md"), recursive=True)
    for p in sorted(set(paths)):
        if not os.path.exists(p):
            continue
        b = os.path.basename(p)
        m = re.search(r"\b(\d{4}) 10-K\b", b)
        if m:
            found.setdefault(("10-K", int(m.group(1))), []).append(p); continue
        # /collect-documents names: "DXCM 2024 Q1 10-Q", "2024 Q4 DXCM release ..."; folders gathered before 2026-11: "Q1 24 ..."
        m = re.search(r"\b(?:Q([1-3]) (\d{2})|(\d{4}) Q([1-3])) 10-Q\b", b)
        if m:
            fy = 2000 + int(m.group(2)) if m.group(2) else int(m.group(3))
            found.setdefault(("10-Q", fy, int(m.group(1) or m.group(4))), []).append(p); continue
        m = re.search(r"\b(?:Q4 (\d{2})|(\d{4}) Q4) .*release", b, re.I)
        if m:
            found.setdefault(("Q4PR", 2000 + int(m.group(1)) if m.group(1) else int(m.group(2))), []).append(p)
    return found


# ------------------------------------------------------------------ mapping rules
# Each mapper returns {role: [[filing label, value, tag], ...]}; tag = "primary" | "fold" | "fallback".
# "fold" = a separately reported line deliberately folded into a broader model row (logged as a judgment call).
# "fallback" = the line didn't match any rule and was put in the section's catch-all row (logged; review it).

def apply_overrides(stmt, label, overrides):
    for o in overrides:
        if o.get("statement", stmt) == stmt and re.search(o["pattern"], label, re.I):
            return o["role"]
    return None


# ------------------------------------------------------------------ income statement
# Opex lines, in order (first match wins). Each one gets its own model row (house default: one row per common
# item); a line no rule knows goes to Other Operating Expense as a logged fallback.
OPEX_RULES = [
    (r"in-process research", "RD", "fold"), (r"research and development|research, development|^r&d", "RD", "primary"),
    (r"selling, general|^sg&a|selling, administrative|selling and administrative", "SGA", "primary"),
    (r"sales and marketing|selling and marketing|marketing and sales|^marketing|^selling|^sales$", "SM", "primary"),
    (r"general and administrative|general, and administrative|^administrative", "GA", "primary"),
    (r"amortization of (acquired |purchased |acquisition-related )?(intangible|developed technology)|^amortization", "AMORT", "primary"),
    (r"^depreciation", "ISDA", "primary"),
    (r"restructuring|severance|reorganization|exit costs", "RESTR", "primary"),
    (r"impairment|write-down|write-off|writedown", "IMPAIR", "primary"),
    (r"acquisition|integration|transaction|merger|separation|divestiture-related", "ACQEXP", "primary"),
    (r"litigation|legal settlement|legal (charges|costs|reserve)|settlement", "LITIG", "primary"),
    (r"(gain|loss).*(sale|disposal|divestiture)|(sale|disposal) of (assets|business|property)", "GAINOP", "primary"),
    (r"other operating|other (expense|income|charges|costs)|^other, net|^other$|special (charge|item)", "OTHOPEX", "primary"),
]
COST_RE = r"^(total )?costs? of |^cost of"
NONOP_RULES = [
    (r"^interest expense|interest expense, net|^interest and debt expense|^interest, net", "INTEXP"),
    (r"^interest income(?!.*other)|^investment income|^interest and investment income", "INTINC"),
    (r"extinguishment", "DEBTEXT"),
    (r"equity in (net )?(earnings|income|loss|losses)|equity method|equity income|(earnings|income) (from|of) (equity|unconsolidated|affiliates)", "EQAFF"),
    (r"(gain|loss).*(investment|securities|equity interests)|investment (gains|losses)|unrealized", "GAININV"),
]


def opex_role(l):
    for pat, role, tag in OPEX_RULES:
        if re.search(pat, l): return role, tag
    return None


def expense_first(l):
    """'other non-operating expense (income), net' -> True: a positive number is a cost"""
    pe = min([x for x in (l.find("expense"), l.find("loss"), l.find("charge")) if x >= 0], default=-1)
    pi = min([x for x in (l.find("income"), l.find("gain"), l.find("benefit")) if x >= 0], default=-1)
    return pe >= 0 and (pi < 0 or pe < pi)


def solve_signs(items, base, target, tol):
    """items [[lab, value, tag]] with default signs already applied: flip the fewest so base + sum == target"""
    from itertools import combinations
    n = len(items)
    if target is None or n == 0: return items
    hint = [(-1 if expense_first(norm(a)) else 1 if re.search(r"income|gain|benefit", norm(a)) else 0) for a, _, _ in items]
    for t in (TOL, tol):                          # an exact tie first; a rounding-sized one only if nothing ties exactly
        for k in range(0, min(n, 4) + 1):
            ok = []
            for flip in combinations(range(n), k):
                vals = [-v if i in flip else v for i, (_, v, _) in enumerate(items)]
                if abs(base + sum(vals) - target) <= t:     # several ways to tie: the one that agrees with the labels
                    ok.append((sum(1 for h, v in zip(hint, vals) if h and v and (v > 0) == (h > 0)), vals))
            if ok:
                vals = max(ok, key=lambda o: o[0])[1]
                return [[a, v, tg] for (a, _, tg), v in zip(items, vals)]
    return items


def map_is(rows, ov, tol=TOL):
    out, state, chk, sub = {}, "REV", {}, None
    add = lambda role, lab, v, tag="primary": out.setdefault(role, []).append([lab, v, tag])
    rev_parts, cost_parts, opex, nonop, post, nonop_raw = [], [], [], [], [], []
    for lab, vals in rows:
        l = norm(lab)
        if not l: continue                             # an unlabeled subtotal
        if not vals:                                   # a heading: 'Cost of sales:' / 'Operating expenses:'
            if re.search(COST_RE, l): sub = "COST"
            elif re.search(r"revenue|sales", l) and state == "REV": sub = "REV"
            elif re.search(r"operating expenses|costs and expenses|expenses", l): sub = "OPEX"
            continue
        x = vals[0]
        r = apply_overrides("IS", lab, ov)
        if r:
            add(r, lab, -x if r in OPEX_ROLES + ["COGS"] else x, "override"); continue
        if l.startswith("shares used") or l.startswith("weighted average") or "shares outstanding" in l or "weighted-average" in l:
            if "basic and diluted" in l:
                chk.setdefault("SB", x); chk.setdefault("SD", x)
            elif "basic" in l: chk.setdefault("SB", x)
            elif "dilut" in l: chk.setdefault("SD", x)
            continue
        if "per share" in l or "per common share" in l or "per ordinary share" in l or l.startswith("basic") or l.startswith("diluted"):
            if "dividend" not in l and "continuing" not in l and "discontinued" not in l:
                if "basic and diluted" in l: chk.setdefault("EPSB", x); chk.setdefault("EPSD", x)
                elif "dilut" in l: chk.setdefault("EPSD", x)
                elif "basic" in l: chk.setdefault("EPSB", x)
            continue
        if l.startswith("gross profit") or l.startswith("gross margin"):
            chk["GP"] = x; state = "OPEX"; continue
        if re.match(r"total operating (costs?|expenses)|total costs? and expenses|total expenses", l):      # ABT: 'Total Operating Cost and Expenses'
            chk["TOPEX"] = x; state = "OPEX"; continue
        if "before income taxes" in l or "before provision for income taxes" in l or "before taxes" in l or "before tax" in l or "pretax" in l or "pre-tax" in l:
            chk["PRETAX"] = x; state = "TAX"; continue
        if re.match(r"(operating (income|loss|profit|earnings))|(income \(loss\) from operations)|(loss from operations)|(income from operations)|((loss|income) from operations)", l):
            chk["OI"] = x; state = "NONOP"; continue
        if state in ("REV", "COST", "OPEX"):
            if sub == "COST" and not re.search(COST_RE, l) and not opex_role(l) or re.search(COST_RE, l):
                state = "COST" if state == "REV" else state
                if l.startswith("total cost") or l in ("cost of sales", "cost of revenue", "cost of revenues", "cost of goods sold", "cost of products sold"):
                    chk["COGS_TOTAL"] = x
                else: cost_parts.append([lab, x])
                continue
            o = opex_role(l)
            if state == "REV" and (not o or o[0] in ("OTHOPEX", "GAINOP")) and sub != "OPEX":   # 'Other' revenue
                if l.startswith("total") or l in ("revenue", "revenues", "net revenue", "net revenues", "net sales", "total net sales", "sales"):
                    chk["REV_TOTAL"] = x
                else: rev_parts.append([lab, x])
                continue
            state = "OPEX"
            role, tag = o or ("OTHOPEX", "fallback")
            opex.append([role, lab, -x, tag])            # costs are positive in a cost list; solve_signs fixes the rest
            continue
        if state == "NONOP":
            if l.startswith("total other") or l.startswith("total non-operating") or l.startswith("other income (expense), net:"):
                continue
            if re.fullmatch(NI_RE, l):               # no pre-tax line (e.g. a company paying no tax)
                chk["NI"] = x; state = "DONE"
                if len(vals) >= 4: chk["NI_YTD"] = vals[2]
                continue
            raw = [(norm(a).split(" ")[0], v) for _, a, v, _ in nonop_raw]
            first = l.split(" ")[0]
            if re.search(r"\bnet\b|total", l) and any(abs(abs(sum(v for _, v in raw[-k:])) - abs(x)) <= TOL and
                                                     any(w == first for w, _ in raw[-k:]) for k in range(2, min(4, len(raw)) + 1)):
                continue                             # 'Interest expense, net' under interest income + interest expense
            nonop_raw.append([None, lab, x, None])
            role = next((rl for pat, rl in NONOP_RULES if re.search(pat, l)), "OTHINC")
            if role == "OTHINC" and opex_role(l) and opex_role(l)[0] in ("RESTR", "IMPAIR", "LITIG", "ACQEXP"):
                tag = "fold"
            else: tag = "primary"
            nonop.append([role, lab, -x if expense_first(l) else x, tag])
            continue
        if state == "TAX":
            if "tax" in l:
                chk["TAX_RAW"] = x; chk["TAX_LABEL"] = l; state = "POST"
            continue
        if state in ("POST", "DONE"):
            if "noncontrolling" in l or "minority" in l:
                if "including" in l and re.match(NI_START, l): chk.setdefault("NI", x); state = "DONE"
                elif state == "DONE": chk["NCI_RAW"] = [lab, x]
                continue
            if "preferred" in l and "dividend" in l or "preferred stock" in l:
                chk["PREF_RAW"] = [lab, x]; continue
            if re.search(r"available to common|attributable to common|to common (stock|share)holders", l):
                chk["NI_COMMON"] = x; continue
            if re.match(NI_START, l) and "attributable" in l:
                if "NI" in chk: chk["NI_PARENT"] = x
                else: chk["NI"] = x; chk["NI_PARENT"] = x
                state = "DONE"; continue
            if re.fullmatch(NI_RE, l):
                if "NI" not in chk:
                    chk["NI"] = x
                    if len(vals) >= 4: chk["NI_YTD"] = vals[2]
                state = "DONE"; continue
            if state == "POST":
                if re.search(r"continuing operations", l) and "discontinued" not in l: chk["CONT"] = x; continue
                if "discontinued" in l:
                    parts = [p[2] for p in post if p[0] == "DISCOPS"]
                    if len(parts) >= 2 and abs(sum(parts) - x) <= tol: continue      # the parts' own subtotal (ABT 2016-19)
                    post.append(["DISCOPS", lab, x, "primary"]); continue
                if re.search(NONOP_RULES[3][0], l): post.append(["EQAFF_AT", lab, -x if expense_first(l) else x, "primary"]); continue
                post.append(["DISCOPS" if "discontinued" in l else "EQAFF_AT", lab, x, "fallback"])
    # revenue / cost: prefer the reported total; if there is none, sum the parts
    if "REV_TOTAL" in chk: add("REV", "Total revenue", chk["REV_TOTAL"])
    else:
        for lab, x in rev_parts: add("REV", lab, x, "fold" if len(rev_parts) > 1 else "primary")
    if "COGS_TOTAL" in chk: add("COGS", "Cost of sales", -chk["COGS_TOTAL"])
    else:
        for lab, x in cost_parts: add("COGS", lab, -x, "fold" if len(cost_parts) > 1 else "primary")
    rev, cogs = tot(out, "REV"), tot(out, "COGS")
    # signs from the company's own subtotals, never from labels alone
    oi = chk.get("OI")
    opx = solve_signs([[lab, v, t] for _, lab, v, t in opex], rev + cogs, oi, tol)
    for (role, _, _, _), (lab, v, t) in zip(opex, opx): add(role, lab, v, t)
    pre = chk.get("PRETAX")
    if pre is None and "TAX_RAW" not in chk: pre = chk.get("NI")
    nop = solve_signs([[lab, v, t] for _, lab, v, t in nonop], oi or 0, pre, tol)
    for (role, _, _, _), (lab, v, t) in zip(nonop, nop): add(role, lab, v, t)
    ni = chk.get("NI")
    if pre is not None and ni is not None:
        psum = sum(v for _, _, v, _ in post)
        tax_exp = round(pre + psum - ni, 3)              # expense positive
        if post and "TAX_RAW" in chk and abs(abs(chk["TAX_RAW"]) - abs(tax_exp)) > tol:
            pst = solve_signs([[lab, v, t] for _, lab, v, t in post], pre - abs(chk["TAX_RAW"]), ni, tol)
            post = [[r, lab, v, t] for (r, _, _, _), (lab, v, t) in zip(post, pst)]
            tax_exp = round(pre + sum(v for _, _, v, _ in post) - ni, 3)
        for role, lab, v, t in post: add(role, lab, v, t)
        raw = chk.get("TAX_RAW", 0.0)
        if abs(abs(raw) - abs(tax_exp)) > tol and "TAX_RAW" in chk:
            chk["TAX_MISMATCH"] = [raw, tax_exp]
        out["TAX"] = [["Income tax (expense) benefit", -tax_exp, "primary"]]
    # what belongs to minority holders / preferred: sign so that NI + NCI + PREF = NI to common
    target = chk.get("NI_COMMON", chk.get("NI_PARENT"))
    for key, role in (("NCI_RAW", "NCI_IS"), ("PREF_RAW", "PREFDIV")):
        if key not in chk: continue
        lab, x = chk[key]
        add(role, lab, -abs(x) if x > 0 or "less" in norm(lab) else x)
    if target is not None and ni is not None and (out.get("NCI_IS") or out.get("PREFDIV")):
        got = ni + tot(out, "NCI_IS", "PREFDIV")
        if abs(got - target) > tol:
            for role in ("NCI_IS", "PREFDIV"):
                if out.get(role) and abs(ni + tot(out, "NCI_IS", "PREFDIV") - 2 * tot(out, role) - target) <= tol:
                    out[role] = [[a, -v, t] for a, v, t in out[role]]
    chk["PRETAX_USED"] = pre
    return out, chk


OPEX_ROLES = ["RD", "SGA", "SM", "GA", "AMORT", "RESTR", "IMPAIR", "ACQEXP", "LITIG", "GAINOP", "OTHOPEX", "ISDA"]
NONOP_ROLES = ["OTHINC", "GAININV", "DEBTEXT", "EQAFF", "INTINC", "INTEXP"]
POST_ROLES = ["EQAFF_AT", "DISCOPS"]


# ------------------------------------------------------------------ balance sheet
def map_bs(rows, ov):
    out, chk, sect, sub = {}, {}, "CA", None
    add = lambda role, lab, v, tag="primary": out.setdefault(role, []).append([lab, v, tag])
    for n, (lab, vals) in enumerate(rows):
        l = norm(lab); x = vals[0] if vals else None
        if not l:                                      # unlabeled: total assets when liabilities follow (ABT), else a subtotal
            nxt = [norm(a) for a, _ in rows[n + 1:] if norm(a)][:3]       # a repeated 'December 31' header may sit between
            if x is not None and "TA" not in chk and any(t.startswith("liabilities") for t in nxt): chk["TA"] = x; sect = "CL"
            continue
        if x is None: sub = l                          # a heading such as 'Inventories:' or 'Property and equipment, at cost:'
        elif l.startswith("total") or l.startswith("net "): sub = None   # the heading's block ends at its total / net line
        if l.startswith("total current assets"): chk["TCA"] = x; sect = "NCA"; continue
        if l.startswith("total assets"): chk["TA"] = x; sect = "CL"; continue
        if l.startswith("total current liabilities"): chk["TCL"] = x; sect = "NCL"; continue
        if l.startswith("total liabilities and") or l.startswith("total liabilities, ") or l.startswith("total liabilities & "): chk["TLE"] = x; continue
        if l.startswith("total liabilities"): chk["TL"] = x; sect = "MEZZ"; continue
        if re.match(r"total (stockholders|shareholders)'? ?(equity|deficit|investment)|total .* (stockholders|shareholders)'? ?(equity|deficit|investment)", l):
            chk.setdefault("EQ", x); sect = "POSTEQ"; continue
        if l.startswith("total equity") or l.startswith("total deficit"): chk["EQ_TOTAL"] = x; continue
        if l.startswith("total") and x is not None and sect in ("CA", "NCA", "CL", "NCL"): continue   # a sub-total (e.g. "Total debt")
        if x is None:
            if re.search(r"(stockholders|shareholders)'? ?(equity|deficit|investment)", l) and sect in ("NCL", "MEZZ"): sect = "EQ"
            continue
        r = apply_overrides("BS", lab, ov)
        if r: add(r, lab, x, "override"); continue
        if sub and sub.startswith("inventor") and sect == "CA": add("INV", lab, x); continue          # finished goods, materials...
        if sub and "property" in sub and sect == "NCA" and not l.startswith("less"): continue    # gross parts of net PP&E
        if sect == "CA":
            if l.startswith("cash and cash equivalents") or l.startswith("cash, cash equivalents") or l in ("cash", "cash and equivalents"): add("CASH", lab, x)
            elif re.match(r"short-term (marketable|investments)|marketable securities|^investments$|^short-term investments|^investments,? current", l): add("STSEC", lab, x)
            elif "receivable" in l and "tax" not in l: add("AR", lab, x)
            elif l.startswith("inventor") or l.startswith("merchandise inventor"): add("INV", lab, x)
            elif l.startswith("prepaid"): add("PRE", lab, x)
            elif l.startswith("other current assets") or l.startswith("other current"): add("OCA", lab, x)
            elif re.search(r"tax|held for sale|restricted cash|deferred|contract assets|derivative", l): add("OCA", lab, x, "fold")
            else: add("OCA", lab, x, "fallback")
        elif sect == "NCA":
            if ("property" in l and "equipment" in l) or l.startswith("property, plant") or "pp&e" in l: add("PPE", lab, x)
            elif "finance lease" in l: add("PPE", lab, x, "fold")
            elif "right-of-use" in l or "operating lease" in l: add("ROU", lab, x)
            elif l.startswith("goodwill"): add("GWI", lab, x)
            elif "and other assets" in l: add("OTHA", lab, x, "fallback")     # 'Intangibles and other assets' (combined)
            elif "intangible" in l or "accumulated amortization" in l: add("GWI", lab, x)
            elif "accumulated depreciation" in l: add("PPE", lab, x)
            elif l.startswith("deferred tax") or l.startswith("deferred income tax") or l in ("tax assets", "income tax assets"): add("DTA", lab, x)
            elif re.search(r"investment|marketable securities|equity method|affiliates", l): add("LTINV", lab, x)
            elif "held for sale" in l: add("OTHA", lab, x, "fold")
            elif l.startswith("other assets") or l.startswith("other long-term assets") or l.startswith("other non-current assets") or l.startswith("other noncurrent assets"): add("OTHA", lab, x)
            else: add("OTHA", lab, x, "fallback")
        elif sect == "CL":
            if l.startswith("accounts payable") or l.startswith("trade payable") or l.startswith("trade accounts payable"): add("AP", lab, x)
            elif l.startswith("accrued payroll") or "compensation" in l or "employee" in l or "salaries" in l: add("PAY", lab, x)
            elif re.search(r"income tax|taxes payable|accrued taxes", l): add("TAXPAY", lab, x)
            elif any(k in l for k in ("debt", "borrowing", "convertible", "notes payable", "senior notes", "commercial paper", "credit facility")): add("CURDEBT", lab, x)
            elif "finance lease" in l: add("CURDEBT", lab, x, "fold")
            elif "operating lease" in l: add("OPLLC", lab, x)
            elif re.search(r"deferred revenue|contract liabilit|unearned revenue|customer deposits|deferred income", l): add("CLOTH", lab, x)
            elif l.startswith("accrued") or l.startswith("other accrued"): add("ACCR", lab, x)
            elif l.startswith("other current liabilities") or l.startswith("other current"): add("OCL", lab, x)
            elif "held for sale" in l: add("OCL", lab, x, "fold")
            else: add("OCL", lab, x, "fallback")
        elif sect == "NCL":
            if re.search(r"income tax|tax liabilit|deferred tax|deferred income tax", l): add("DTL", lab, x)
            elif "finance lease" in l: add("LTDEBT", lab, x, "fold")
            elif any(k in l for k in ("debt", "borrowing", "convertible", "senior notes", "notes payable")): add("LTDEBT", lab, x)
            elif "operating lease" in l: add("OPLLLT", lab, x)
            elif re.search(r"deferred revenue|contract liabilit|unearned revenue", l): add("DEFREVLT", lab, x)
            elif re.search(r"pension|retirement|postretirement|post-retirement", l): add("PENSION", lab, x)
            elif l.startswith("other"): add("OTHLTL", lab, x)
            elif "held for sale" in l: add("OTHLTL", lab, x, "fold")
            elif l.startswith("commitments") or "stockholders" in l or "shareholders" in l: pass
            else: add("OTHLTL", lab, x, "fallback")
        elif sect == "MEZZ":                           # between total liabilities and equity: temporary equity
            if l.startswith("commitments"): continue
            add("MEZZ", lab, x)
        elif sect == "POSTEQ":
            if "noncontrolling" in l or "minority" in l: add("NCTL", lab, x)
    # gross / accumulated depreciation / net shown separately: the net line is the balance (the others are detail)
    for role in ("PPE", "GWI"):
        items = out.get(role, [])
        nets = [i for i in items if re.search(r"\bnet\b", norm(i[0]))]
        detail = [i for i in items if re.search(r"accumulated|^less|gross", norm(i[0]))]
        if nets and detail:
            out[role] = [i for i in items if i not in detail and (i in nets or not re.match(r"property|plant|equipment", norm(i[0])))]
    if "EQ" not in chk and "EQ_TOTAL" in chk: chk["EQ"] = chk["EQ_TOTAL"] - tot(out, "NCTL")
    if "EQ_TOTAL" in chk and chk.get("EQ") is not None and not out.get("NCTL") and abs(chk["EQ_TOTAL"] - chk["EQ"]) > TOL:
        add("NCTL", "Noncontrolling interests (total equity - shareholders' equity)", round(chk["EQ_TOTAL"] - chk["EQ"], 3), "fold")
    out["EQ"] = [["Total stockholders' equity", chk.get("EQ"), "primary"]]
    return out, chk


# ------------------------------------------------------------------ cash flow
def map_cf(rows, ov):
    out, chk, sect = {}, {}, "OPNC"
    add = lambda role, lab, v, tag="primary": out.setdefault(role, []).append([lab, v, tag])
    for lab, vals in rows:
        l = norm(lab); x = vals[0] if vals else None
        if not l: continue                             # an unlabeled subtotal
        if l.startswith("changes in operating assets") or l.startswith("changes in assets and liabilities") or l.startswith("change in operating assets") \
                or l.startswith("changes in operating capital") or l.startswith("changes in working capital"):
            sect = "OPWC"; continue
        if l.startswith("net cash") and "operating" in l or l.startswith("cash provided by operating") or l.startswith("cash generated by operating") \
                or l.startswith("cash flows from operating activities") and x is not None:
            chk["CFO"] = x; sect = "INV"; continue
        if l.startswith("net cash") and "investing" in l or l.startswith("cash used in investing") or l.startswith("cash (used in) provided by investing"):
            chk["CFI"] = x; sect = "FIN"; continue
        if l.startswith("net cash") and "financing" in l or l.startswith("cash used in financing") or l.startswith("cash provided by financing"):
            chk["CFF"] = x; sect = "POST"; continue
        if x is None:
            continue
        if sect == "POST":
            if l.startswith("effect of exchange") or "exchange rate" in l: chk["FX"] = x
            elif "beginning of" in l: chk.setdefault("BEG", x)
            elif "end of" in l or "ending of" in l: chk.setdefault("END", x)
            elif l == "restricted cash" or l.startswith("restricted cash"): chk.setdefault("RC", x)
            continue
        r = apply_overrides("CF", lab, ov)
        if r: add(r, lab, x, "override"); continue
        if sect == "OPNC" and re.match(r"(trade |accounts )?receivables?$|inventor(y|ies)$|prepaid|(trade )?accounts payable", l):
            sect = "OPWC"                              # working-capital lines with no heading of their own (ABT)
        if sect == "OPNC":
            if "NI_CF" not in out and re.fullmatch(NI_RE + r"( including noncontrolling interests?)?", l): add("NI_CF", lab, x)
            elif "debt issuance" in l or "debt discount" in l or "non-cash interest" in l or "accretion of debt" in l: add("NCI", lab, x)
            elif l.startswith("depreciation") or l.startswith("amortization"): add("DA", lab, x)
            elif "share-based" in l or "stock-based" in l or "stock compensation" in l or "equity-based compensation" in l: add("SBC", lab, x)
            elif "deferred tax" in l or "deferred income tax" in l or "valuation allowance" in l: add("DT", lab, x)
            elif "equity investment" in l or "equity method" in l or "equity in (earnings" in l or re.search(r"equity in (net )?(earnings|income|loss)", l): add("EQI", lab, x)
            elif re.search(r"impairment|write-down|write-off|writedown", l): add("IMPAIR_CF", lab, x)
            elif re.search(r"(gain|loss).*(sale|disposal|divestiture)", l): add("GAIN_CF", lab, x)
            elif re.search(r"(gain|loss).*investment|investment (gain|loss)|unrealized", l): add("EQI", lab, x, "fold")
            elif re.search(r"provision for (doubtful|credit|bad debt)|allowance for|extinguishment|acquisition-related|inventory reserve", l):
                add("OTHNC", lab, x, "fold")
            elif "other" in l: add("OTHNC", lab, x)
            else: add("OTHNC", lab, x, "fallback")
        elif sect == "OPWC":
            if "receivable" in l and "tax" not in l: add("W_AR", lab, x)
            elif l.startswith("inventor") or "merchandise inventor" in l: add("W_INV", lab, x)
            elif "right-of-use" in l or "lease liabilit" in l or "operating lease" in l: add("W_ROU", lab, x)
            elif l.startswith("prepaid"): add("W_PRE", lab, x)
            elif l.startswith("accounts payable") or l.startswith("trade payable") or l.startswith("trade accounts payable"): add("W_AP", lab, x)
            elif l.startswith("accrued payroll") or "compensation" in l or "employee" in l: add("W_PAY", lab, x)
            elif re.search(r"income tax|taxes payable", l): add("W_TAX", lab, x)
            elif re.search(r"deferred revenue|contract liabilit|unearned revenue|deferred rent|^other liabilities", l): add("W_OTH", lab, x)
            elif re.search(r"other (operating )?assets and liabilities|^other, net|^other$|other assets and liabilities", l): add("W_OTHAL", lab, x)
            elif l.startswith("accrued"): add("W_AP", lab, x, "fold")
            elif any(k in l for k in ("liabilit", "payable")): add("W_OTH", lab, x, "fallback")
            else: add("W_OTHAL", lab, x, "fallback")
        elif sect == "INV":
            if l.startswith("purchase") and ("securities" in l or "investments" in l) and "equity" not in l: add("PURSEC", lab, x)
            elif re.search(r"capitalized software|internal-use software|software development costs|capitalized internal", l): add("CAPSW", lab, x)
            elif l.startswith("proceeds") and re.search(r"sale of (property|business|assets|equipment)|divest|disposal|business disposition", l) or "divestiture" in l: add("DIVEST", lab, x)
            elif (l.startswith("proceeds") or l.startswith("sales and maturities") or l.startswith("maturities") or l.startswith("sales of")) and ("securities" in l or "investments" in l): add("SALESEC", lab, x)
            elif ("property" in l and "equipment" in l) or "capital expenditure" in l or l.startswith("purchases of property") or l.startswith("additions to property"): add("CAPEX", lab, x)
            elif l.startswith("acquisition") or "business combination" in l or "net of cash acquired" in l or "acquisitions" in l: add("ACQ", lab, x)
            elif "other" in l: add("OTHINV", lab, x)
            else: add("OTHINV", lab, x, "fallback")
        elif sect == "FIN":
            if "dividend" in l and not ("noncontrolling" in l or "minority" in l): add("DIV", lab, x)
            elif "net share settlement" in l or "withholding" in l and "tax" in l: add("STOCK", lab, x, "fold")
            elif "finance lease" in l: add("DEBT", lab, x, "fold")
            elif any(k in l for k in ("debt", "borrowing", "convertible", "note hedge", "warrant", "capped call", "credit facility", "senior notes", "commercial paper", "current debt obligations", "notes payable", " notes")): add("DEBT", lab, x)
            elif re.search(r"repurchase|treasury|buyback|buy-back|^purchases? of (common|ordinary) (shares|stock)", l): add("BUYBACK", lab, x)
            elif re.search(r"common stock|ordinary shares|issuance of (common|ordinary|shares)|stock option|employee stock|stock plans|exercise", l): add("STOCK", lab, x)
            elif "contingent consideration" in l or "noncontrolling" in l or "minority" in l: add("OTHFIN", lab, x, "fold")
            elif "other" in l: add("OTHFIN", lab, x)
            else: add("OTHFIN", lab, x, "fallback")
    return out, chk


def tot(out, *roles):
    return sum(v for r in roles for _, v, _ in out.get(r, []) if v is not None)


IS_SUM = ["REV", "COGS"] + OPEX_ROLES
CA, NCA = ["CASH", "STSEC", "AR", "INV", "PRE", "OCA"], ["PPE", "ROU", "GWI", "LTINV", "DTA", "OTHA"]
CL, NCL = ["AP", "PAY", "ACCR", "TAXPAY", "CURDEBT", "OPLLC", "CLOTH", "OCL"], ["LTDEBT", "OPLLLT", "DEFREVLT", "DTL", "PENSION", "OTHLTL"]
CFO_R = ["NI_CF", "DA", "SBC", "NCI", "DT", "EQI", "IMPAIR_CF", "GAIN_CF", "OTHNC", "W_AR", "W_INV", "W_PRE", "W_ROU", "W_AP",
         "W_PAY", "W_OTH", "W_TAX", "W_OTHAL"]
CFI_R = ["PURSEC", "SALESEC", "CAPEX", "CAPSW", "ACQ", "DIVEST", "OTHINV"]
CFF_R = ["STOCK", "BUYBACK", "DIV", "DEBT", "OTHFIN"]


def unit_of(*tables):
    """the reporting precision: 1 when every number is whole (e.g. MDT, $ millions without decimals), 0.1, 0.01..."""
    vals = [v for t in tables for lab, vs in t for v in vs[:1] if isinstance(v, (int, float)) and "share" not in lab.lower()]
    for u in (1, 0.1, 0.01):
        if all(abs(v / u - round(v / u)) < 1e-6 for v in vals): return u
    return 0.001


def plug_rounding(out, roles, plug, reported, unit, what):
    """a company's own subtotal can differ from the sum of its rounded lines by a unit or two: put the difference in
    the block's catch-all row (tag 'rounding', logged) so the model's subtotal equals the reported one"""
    if reported is None: return
    d = round(reported - tot(out, *roles), 6)
    if TOL < abs(d) <= 3 * unit + 1e-9:
        out.setdefault(plug, []).append([f"Rounding to the reported {what}", d, "rounding"])


def tie_out(key, I, Ic, B, Bc, C, Cc):
    e = []
    if "GP" in Ic and abs(tot(I, "REV", "COGS") - Ic["GP"]) > TOL: e.append("gross profit")
    oi_m = tot(I, *IS_SUM)
    if "OI" not in Ic: e.append("no operating income line found")
    elif abs(oi_m - Ic["OI"]) > TOL: e.append(f"operating income model {oi_m:.1f} vs reported {Ic['OI']}")
    if Ic.get("PRETAX_USED") is None: e.append("no pre-tax / net income line found")
    elif abs(Ic.get("OI", 0) + tot(I, *NONOP_ROLES) - Ic["PRETAX_USED"]) > TOL: e.append("pre-tax income")
    if "NI" not in Ic: e.append("no net income line")
    if "TAX_MISMATCH" in Ic: e.append(f"tax line {Ic['TAX_MISMATCH'][0]} vs pretax-NI {Ic['TAX_MISMATCH'][1]}")
    for k in ("SB", "SD"):
        if k not in Ic: e.append(f"no share count ({k})")
    ca = tot(B, *CA)
    if abs(ca - (Bc.get("TCA") or 0)) > TOL: e.append(f"current assets {ca:.1f} vs {Bc.get('TCA')}")
    ta = ca + tot(B, *NCA)
    if abs(ta - (Bc.get("TA") or 0)) > TOL: e.append(f"total assets {ta:.1f} vs {Bc.get('TA')}")
    cl = tot(B, *CL)
    if Bc.get("TCL") is not None and abs(cl - Bc["TCL"]) > TOL: e.append(f"current liabilities {cl:.1f} vs {Bc.get('TCL')}")
    tl = cl + tot(B, *NCL)
    if Bc.get("TL") is not None and abs(tl - Bc["TL"]) > Cc.get("_RTOL", TOL): e.append(f"total liabilities {tl:.1f} vs {Bc.get('TL')}")
    if abs(tl + tot(B, "MEZZ", "EQ", "NCTL") - (Bc.get("TA") or 0)) > TOL: e.append("liabilities + equity != assets")
    cfo = tot(C, *CFO_R)
    if abs(cfo - (Cc.get("CFO") or 0)) > TOL: e.append(f"CFO {cfo:.1f} vs {Cc.get('CFO')}")
    if abs(tot(C, *CFI_R) - (Cc.get("CFI") or 0)) > TOL: e.append(f"CFI {tot(C, *CFI_R):.1f} vs {Cc.get('CFI')}")
    if abs(tot(C, *CFF_R) - (Cc.get("CFF") or 0)) > TOL: e.append(f"CFF {tot(C, *CFF_R):.1f} vs {Cc.get('CFF')}")
    if "BEG" in Cc and "END" in Cc:
        if abs(Cc["BEG"] + (Cc.get("CFO") or 0) + (Cc.get("CFI") or 0) + (Cc.get("CFF") or 0) + (Cc.get("FX") or 0) - Cc["END"]) > Cc.get("_RTOL", TOL):
            e.append("cash roll-forward")
    else: e.append("no beginning/ending cash")
    cash_bs = tot(B, "CASH") + (Cc.get("RC") or 0)
    if "END" in Cc and abs(cash_bs - Cc["END"]) > TOL:
        e.append(f"CF ending cash {Cc['END']} vs BS cash {tot(B,'CASH')} + restricted {Cc.get('RC') or 0}")
    ni_ref = Ic.get("NI_YTD") if key[:2] in ("Q2", "Q3") else Ic.get("NI")
    if ni_ref is not None and abs(tot(C, "NI_CF") - ni_ref) > TOL:
        e.append("CF net income != IS net income")
    return e


FINANCIAL = [   # (kind, statement, regex) - any hit in the latest 10-K: this template doesn't fit
    ("bank", "BS", r"^deposits$|total deposits|interest-bearing deposits"),
    ("bank", "IS", r"^net interest income|provision for (credit|loan) losses"),
    ("insurer", "IS", r"premiums earned|net premiums|policyholder benefits"),
    ("insurer", "BS", r"unpaid losses|future policy benefits|loss and loss adjustment expense reserves"),
    ("REIT", "BS", r"^investments? in real estate|rental propert|real estate, net|total real estate"),
]


ALLOC_RE = re.compile(r"net (earnings|income) allocated to common (shares|stock)[^$]{0,200}?\$\s?([\d.,]+) (billion|million)", re.I)


def allocated_to_common(text):
    """two-class EPS: the filing's own 'net earnings allocated to common shares' in $M, only when printed to the million
    ($13.351 billion, $468 million); a figure like '$1.3 billion' is too coarse to fix EPS to the cent -> None"""
    m = ALLOC_RE.search(re.sub(r"\s+", " ", text))
    if not m: return None
    num, unit = m.group(3).replace(",", ""), m.group(4).lower()
    if unit == "million": return float(num)
    return round(float(num) * 1000, 3) if re.fullmatch(r"\d+\.\d{3}", num) else None


def two_class(periods):
    """add the earnings allocated to participating securities (= allocated to common - net earnings, both printed) for
    every year whose 10-K and 10-Qs all print the allocation to the million. A year is all or nothing because the model's
    Q4 is FY - Q1 - Q2 - Q3. -> {yy: why skipped} for years with some but not all periods printed"""
    skipped = {}
    for yy in sorted({k[3:] for k in periods}):
        keys = [k for k in periods if k[3:] == yy]
        got = {k: periods[k]["IS_chk"].get("ALLOC_COMMON") for k in keys}
        if None in got.values() or f"FY {yy}" not in keys:
            skipped[yy] = "not printed to the million in " + ", ".join(sorted(k for k, v in got.items() if v is None) or ["(no 10-K yet)"])
            continue
        for k in keys:
            periods[k]["IS"]["PARTSEC"] = [["Net earnings allocated to common shares (EPS note)", got[k], "two-class"],
                                           ["Less: net earnings", -periods[k]["IS_chk"]["NI"], "two-class"]]
    if all(v.startswith("not printed to the million in") and len(v.split(", ")) == len([k for k in periods if k[3:] == y])
           for y, v in skipped.items()) and not any(p["IS"].get("PARTSEC") for p in periods.values()):
        return {}                                      # the company never prints it: not a two-class reporter
    return skipped


def financial_kind(t):
    hits = {}
    for kind, st, pat in FINANCIAL:
        if any(re.search(pat, norm(lab)) for lab, _ in t.get(st, [])): hits[kind] = hits.get(kind, 0) + 1
    return next((k for k, n in hits.items() if n >= 1 and (k != "bank" or n >= 2)), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--decisions", default=None)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    dec = json.load(open(a.decisions)) if a.decisions and os.path.exists(a.decisions) else {}
    ov = dec.get("label_overrides", [])
    files = discover(a.src)
    periods, raw, report, fails, report_units = {}, {}, [], 0, []
    keyof = lambda k: (f"FY {k[1] % 100:02d}" if k[0] == "10-K" else f"Q{k[2]} {k[1] % 100:02d}")
    tenks = sorted(x for x in files if x[0] == "10-K")
    if tenks:                                   # banks, insurers and REITs don't fit this template (house default)
        kind = financial_kind(find_tables(open(files[tenks[-1]][0], encoding="utf-8", errors="ignore").read()))
        if kind:
            print(f"STOP: this looks like a {kind} ({os.path.basename(files[tenks[-1]][0])}). /model-historicals covers commercial "
                  "and industrial companies; a {kind}'s statements need a different template.".replace("{kind}", kind))
            sys.exit(3)
    for k in sorted(x for x in files if x[0] in ("10-K", "10-Q")):
        path = files[k][0]
        text = open(path, encoding="utf-8", errors="ignore").read()
        t = find_tables(text)
        key = keyof(k)
        raw[key] = {"file": os.path.basename(path), "tables": t}
        units = t.pop("_units", {})
        if set(t) != {"IS", "BS", "CF"}:
            fails += 1; report.append(f"| {key} | {os.path.basename(path)} | **could not find statements: missing {sorted({'IS','BS','CF'} - set(t))}** |"); continue
        unit = max(unit_of(t["IS"]), unit_of(t["BS"]), unit_of(t["CF"])); rtol = 3 * unit + TOL
        I, Ic = map_is(t["IS"], ov, rtol); B, Bc = map_bs(t["BS"], ov); C, Cc = map_cf(t["CF"], ov)
        Ic["ALLOC_COMMON"] = allocated_to_common(text)
        Cc["_RTOL"] = rtol
        plug_rounding(I, IS_SUM, "OTHOPEX", Ic.get("OI"), unit, "operating income")
        if Ic.get("OI") is not None:
            plug_rounding(I, IS_SUM + NONOP_ROLES, "OTHINC", Ic.get("PRETAX_USED"), unit, "pre-tax income")
        plug_rounding(B, CA, "OCA", Bc.get("TCA"), unit, "current assets")
        plug_rounding(B, CA + NCA, "OTHA", Bc.get("TA"), unit, "total assets")
        plug_rounding(B, CL, "OCL", Bc.get("TCL"), unit, "current liabilities")
        plug_rounding(B, CL + NCL, "OTHLTL", Bc.get("TL") if Bc.get("TL") is not None else
                      (Bc.get("TA") or 0) - tot(B, "MEZZ", "EQ", "NCTL"), unit, "total liabilities")
        plug_rounding(B, CL + NCL + ["MEZZ", "EQ", "NCTL"], "OTHLTL", Bc.get("TA"), unit, "total assets (the filing's own totals differ)")
        plug_rounding(C, CFO_R, "OTHNC", Cc.get("CFO"), unit, "operating cash flow")
        plug_rounding(C, CFI_R, "OTHINV", Cc.get("CFI"), unit, "investing cash flow")
        plug_rounding(C, CFF_R, "OTHFIN", Cc.get("CFF"), unit, "financing cash flow")
        if "BEG" in Cc and "END" in Cc:            # the filing's own roll-forward can be a unit off: absorb it in FX
            d = round(Cc["END"] - (Cc["BEG"] + sum(Cc.get(k) or 0 for k in ("CFO", "CFI", "CFF", "FX"))), 6)
            if TOL < abs(d) <= 3 * unit + 1e-9:
                Cc["FX"] = round((Cc.get("FX") or 0) + d, 6)
                C["FX_ROUND"] = [["Cash roll-forward rounding, put in Exchange Rate Effects", d, "rounding"]]
        e = tie_out(key, I, Ic, B, Bc, C, Cc)
        if any(u != "millions" for u in units.values()): report_units.append(f"{key}: {units} (scaled to $ millions)")
        periods[key] = {"source": os.path.basename(path), "units": units, "IS": I, "IS_chk": Ic, "BS": B, "BS_chk": Bc, "CF": C, "CF_chk": Cc}
        if e: fails += 1
        report.append(f"| {key} | {os.path.basename(path)} | {'OK' if not e else '**' + '; '.join(e) + '**'} |")
    # the model's cash flow starts from the income statement's quarterly net income; when those quarters add up to a
    # unit or two less than the cash flow's year-to-date net income (each filing rounds on its own), put the
    # difference in Other non-cash so year-to-date operating cash flow still ties
    for key, p in periods.items():
        if key[:2] not in ("Q2", "Q3"): continue
        yy, n = key[3:], int(key[1])
        qs = [periods.get(f"Q{i} {yy}", {}).get("IS_chk", {}).get("NI") for i in range(1, n + 1)]
        ytd = tot(p["CF"], "NI_CF")
        if None in qs or not p["CF"].get("NI_CF"): continue
        d = round(ytd - sum(qs), 6)
        if TOL < abs(d) <= p["CF_chk"].get("_RTOL", TOL):
            p["CF"].setdefault("OTHNC", []).append(["Rounding: quarterly net income vs year-to-date cash-flow net income", d, "rounding"])
    two_class_skipped = two_class(periods)
    # Q4 share counts from Q4 press releases (3-month column); fall back to next year's release prior-year column
    q4 = {}
    for k, paths in files.items():
        if k[0] != "Q4PR": continue
        for p in sorted(paths, key=lambda s: -os.path.getsize(s)):
            sb, sd, ni = shares_from_release(open(p, encoding="utf-8", errors="ignore").read())
            if sb and sd:
                q4[k[1]] = {"SB": sb, "SD": sd, "NI": ni, "file": os.path.basename(p)}; break
    q4out = {}
    for fy in sorted({int("20" + k[3:]) for k in periods if k.startswith("FY")}):
        if fy in q4:
            r = q4[fy]; q4out[f"Q4 {fy % 100:02d}"] = {"SB": r["SB"][0], "SD": r["SD"][0], "NI": r["NI"][0] if r["NI"] else None, "source": r["file"], "source_period": f"Q4 {fy % 100:02d}"}
        elif fy + 1 in q4 and len(q4[fy + 1]["SB"]) > 1:
            r = q4[fy + 1]; q4out[f"Q4 {fy % 100:02d}"] = {"SB": r["SB"][1], "SD": r["SD"][1], "NI": r["NI"][1] if r["NI"] and len(r["NI"]) > 1 else None,
                                                     "source": r["file"] + " (prior-year column)", "source_period": f"Q4 {(fy + 1) % 100:02d}", "fallback": True}
        else:
            # last resort: weighted-average shares for the year ~= the average of its four quarters, so
            # Q4 ~= 4 x FY - (Q1 + Q2 + Q3). Approximate (unequal quarters, anti-dilution in loss quarters); logged.
            yy = f"{fy % 100:02d}"
            q = [periods.get(f"Q{i} {yy}", {}).get("IS_chk", {}) for i in (1, 2, 3)]
            f = periods.get(f"FY {yy}", {}).get("IS_chk", {})
            if all(x.get("SB") and x.get("SD") for x in q + [f]):
                q4out[f"Q4 {yy}"] = {"SB": round(4 * f["SB"] - sum(x["SB"] for x in q), 1), "SD": round(4 * f["SD"] - sum(x["SD"] for x in q), 1),
                                     "NI": None, "source": f"derived: 4 x FY {yy} - (Q1 + Q2 + Q3) (no Q4 release with share counts)",
                                     "source_period": f"Q4 {yy}", "fallback": True, "derived": True}
            else:
                q4out[f"Q4 {yy}"] = {"missing": True}
    for k, v in q4out.items():          # press releases sometimes report shares in thousands
        fy = periods.get("FY " + k[3:], {}).get("IS_chk", {})
        if not v.get("missing") and fy.get("SB") and v["SB"] / fy["SB"] > 300:
            v["SB"] /= 1000; v["SD"] /= 1000; v["source"] += " (shares scaled from thousands)"
    json.dump({"periods": periods, "q4": q4out}, open(os.path.join(a.work, "periods.json"), "w"), indent=1)
    json.dump(raw, open(os.path.join(a.work, "filings.json"), "w"))
    # mapping log: every fold / fallback / override, grouped by filing label
    calls = {}
    for key, p in periods.items():
        for st in ("IS", "BS", "CF"):
            for role, items in p[st].items():
                for lab, v, tag in items:
                    if tag != "primary":
                        calls.setdefault((st, lab, role, tag), []).append(key)
    with open(os.path.join(a.work, "extract_report.md"), "w") as f:
        f.write("# Extraction report\n\n## Tie-out of each filing to its own subtotals\n\n| Period | File | Result |\n|---|---|---|\n")
        f.write("\n".join(report) + "\n\n## Units\n\n" + ("\n".join("- " + u for u in report_units) or "All statements reported in $ millions.") + "\n\n## Q4 share counts (press releases)\n\n")
        for k, v in q4out.items():
            f.write(f"- {k}: " + ("**MISSING - no Q4 release with share counts**" if v.get("missing") else f"basic {v['SB']}, diluted {v['SD']} from {v['source']}") + "\n")
        filled = sorted({k[3:] for k, p in periods.items() if p["IS"].get("PARTSEC")})
        if filled or two_class_skipped:
            f.write("\n## Two-class EPS (earnings allocated to participating securities)\n\n"
                    f"- filled: {', '.join('20' + y for y in filled) or 'none'}\n")
            for yy, why in two_class_skipped.items(): f.write(f"- **20{yy} left at zero** (EPS = net income / shares): {why}\n")
        f.write("\n## Non-obvious mappings (each one is a judgment call to report)\n\n| Stmt | Filing line | Model role | Why | Periods |\n|---|---|---|---|---|\n")
        for (st, lab, role, tag), ks in sorted(calls.items()):
            f.write(f"| {st} | {lab} | {role} | {tag} | {', '.join(ks[:6])}{' ...' if len(ks) > 6 else ''} ({len(ks)}) |\n")
    print(f"filings: {len(report)}  failing tie-out: {fails}  non-obvious mappings: {len(calls)}  q4 share sets: {sum(1 for v in q4out.values() if not v.get('missing'))}/{len(q4out)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
