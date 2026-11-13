"""The condensed lines Industry P&L shows for every company, and where each comes from.

Sign convention = the MOD tab: costs and cash outflows are negative, so every subtotal is a plain sum
(Gross Profit = Revenue + COGS, EBITDA = Operating Income + D&A, FCF = CFO + CapEx).
MOD patterns: each line has alternative groups; a group is a list of label regexes whose rows are summed
(a leading "?" makes one optional); the first group that matches wins. Never row numbers: the user inserts rows."""

LINES = [  # key, column-B label, statement
    ("revenue", "Revenue", "IS"),
    ("cogs", "(-) Cost of Sales", "IS"),
    ("gross_profit", "Gross Profit", "IS"),
    ("rd", "(-) R&D", "IS"),
    ("sga", "(-) SG&A", "IS"),
    ("oi", "Operating Income", "IS"),
    ("da", "D&A (from cash flow)", "IS"),
    ("ebitda", "EBITDA", "IS"),
    ("pretax", "Pre-Tax Income", "IS"),
    ("tax", "(-) Income Taxes", "IS"),
    ("net_income", "Net Income", "IS"),
    ("cash", "Cash & Short-term Securities", "BS"),
    ("receivables", "Accounts Receivable", "BS"),
    ("inventory", "Inventory", "BS"),
    ("ppe", "Net PP&E", "BS"),
    ("gwi", "Goodwill & Intangibles", "BS"),
    ("total_assets", "Total Assets", "BS"),
    ("payables", "Accounts Payable & Accrued", "BS"),
    ("debt", "Total Debt", "BS"),
    ("equity", "Total Equity", "BS"),
    ("cfo", "Operating Cash Flow", "CF"),
    ("capex", "(-) CapEx", "CF"),
    ("fcf", "Free Cash Flow", "CF"),
    ("buybacks", "(+/-) Stock Issuance / Repurchase", "CF"),
    ("dividends", "(-) Dividends", "CF"),
]
KEYS = [k for k, _, _ in LINES]
LABEL = {k: lab for k, lab, _ in LINES}
STMT = {k: s for k, _, s in LINES}
STMT_TITLE = {"IS": "Income statement", "BS": "Balance sheet", "CF": "Cash flow"}
CALC = {"gross_profit": ("revenue", "cogs"), "ebitda": ("oi", "da"), "fcf": ("cfo", "capex")}
INPUTS = [k for k in KEYS if k not in CALC]
SEGMENT_LINES = ("revenue", "cogs", "rd", "sga", "oi", "da", "capex", "total_assets")
NEGATIVE = {"cogs", "rd", "sga", "capex"}   # segment notes print these positive; stored negative

MOD = {
    "revenue": [[r"^Revenue:?$"], [r"^Total Revenues?:?$"], [r"^Net Revenues?:?$"], [r"^Net Sales:?$"]],
    "cogs": [[r"^\(-\) Cost of (Sales|Revenues?|Goods Sold)"]],
    "rd": [[r"^\(-\) R&D$"], [r"^\(-\) Research"]],
    "sga": [[r"^\(-\) SG&A$"], [r"^\(-\) Selling, General"]],
    "oi": [[r"^Operating Income$"], [r"^Operating Income \(Loss\)$"], [r"^Income \(Loss\) from Operations$"],
           [r"^Income from Operations$"]],
    "da": [[r"^\(\+\) Depreciation (&|and) Amortization"]],
    "pretax": [[r"^Pre-Tax Income:?$"], [r"^Income Before (Income )?Taxes"], [r"^EBIT:?$"]],
    "tax": [[r"^\(-\) Income Taxes$"], [r"^\(-\) (Provision for )?Income Tax"]],
    "net_income": [[r"^Net Income$"], [r"^Net Income:$"]],
    "cash": [[r"^Cash & Equivalents$", r"?^Short-term (marketable securities|investments)$"]],
    "receivables": [[r"^Accounts Receivable"]],
    "inventory": [[r"^Inventor(y|ies)$"]],
    "ppe": [[r"^Net PP&E$"], [r"^PP&E, net$"]],
    "gwi": [[r"^Goodwill & Intangibles$"], [r"^Goodwill$", r"?^(Other )?Intangible"]],
    "total_assets": [[r"^TOTAL ASSETS:?$"]],
    "payables": [[r"^Accounts Payable", r"?^Accrued payroll", r"?^Accrued Expenses"]],
    "debt": [[r"?^Current (Portion of )?.*(Debt|Notes)", r"?^(LT|Long-Term) .*(Debt|Notes)"]],
    "equity": [[r"^Total Stockholders.? Equity:?$"], [r"^Total (Shareholders|Stockholders).? Equity"]],
    "cfo": [[r"^Net Cash Provided by Operating Activities:?$"], [r"^Net Cash (from|Provided by|Used in) Operating"]],
    "capex": [[r"^\(-\) CapEx"]],
    "buybacks": [[r"^\(\+/-\) Stock Issuance / Repurchase$"],
                 [r"?^\(\+\) Stock Issuance", r"?^\(-\) Share Repurchases"]],
    "dividends": [[r"^\(-\) Dividends"]],
}

# line -> [(statement, engine field, mode)], summed, dollars -> $M. mode: "+" as is, "neg" flip the sign,
# "-abs" always negative (the engine reports these costs / outflows positive).
XBRL = {
    "revenue": [("income", "revenues", "+")],
    "cogs": [("income", "cost_of_revenue", "-abs")],
    "rd": [("income", "research_and_development", "-abs")],
    "sga": [("income", "sga", "-abs")],
    "oi": [("income", "operating_income_loss", "+")],
    "da": [("cashFlow", "depreciation_amortization", "+")],
    "pretax": [("income", "income_before_tax", "+")],
    "tax": [("income", "income_tax", "neg")],
    "net_income": [("income", "net_income_loss", "+")],
    "cash": [("balance", "cash", "+"), ("balance", "short_term_investments", "+")],
    "receivables": [("balance", "accounts_receivable", "+")],
    "inventory": [("balance", "inventory", "+")],
    "ppe": [("balance", "property_plant_equipment", "+")],
    "gwi": [("balance", "goodwill", "+"), ("balance", "intangible_assets", "+")],
    "total_assets": [("balance", "assets", "+")],
    "payables": [("balance", "payables_and_accrued", "+")],
    "debt": [("balance", "total_debt", "+")],
    "equity": [("balance", "total_equity", "+")],
    "cfo": [("cashFlow", "net_cash_flow_from_operating_activities", "+")],
    "capex": [("cashFlow", "capital_expenditures", "-abs")],
    "buybacks": [("cashFlow", "proceeds_from_stock_issuance", "+"), ("cashFlow", "share_repurchases", "-abs")],
    "dividends": [("cashFlow", "dividends_paid", "-abs")],
}


def _apply(mode, v):
    return -abs(v) if mode == "-abs" else (-v if mode == "neg" else v)


def from_xbrl(d):
    """edgar-xbrl-financials JSON -> ({line: {fy: $M or None}}, {line: {fy: "Tag + Tag"}})."""
    A, P = d["annual"], d.get("provenance", {})
    years = sorted(int(y) for y in A.get("income", {}))
    vals, tags = {}, {}
    for k, parts in XBRL.items():
        vals[k], tags[k] = {}, {}
        for y in years:
            got, tg = [], []
            for st, f, mode in parts:
                v = A.get(st, {}).get(str(y), {}).get(f)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    got.append(_apply(mode, v) / 1e6)
                    tg.append(((P.get(st, {}).get(str(y), {}) or {}).get(f) or {}).get("tag") or f)
            vals[k][y] = round(sum(got), 6) if got else None
            tags[k][y] = " + ".join(tg)
    return vals, tags
