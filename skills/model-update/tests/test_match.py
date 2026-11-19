import openpyxl

import modmap
import release
import match
import make_fixture as mf


def _run(model, variant="normal", grid=None):
    rel = release.parse_text(mf.release_md(variant), "rel.md")
    return match.match(rel, modmap.ModMap(model), grid or mf.values(), "Q3 26E")


def _by_label(res, bucket):
    return {e["label"]: e for e in res[bucket]}


def test_lines_land_on_rows_by_their_year_ago_value_not_their_label(model):
    """'Total operating expenses' is labelled differently from the model's 'Operating expenses' but carries its value."""
    m = _by_label(_run(model), "matched")
    assert m["Total operating expenses"]["row"] == 8
    assert m["Revenue"]["row"] == 4 and m["Revenue"]["cur"] == 140.0


def test_label_breaks_a_tie_between_two_rows_with_the_same_value(model):
    """Total assets and total liabilities + equity are both 84 at year-end; each must go to its own row."""
    m = _by_label(_run(model), "matched")
    assert m["Total assets"]["row"] == 17
    assert m["Total liabilities and stockholders' equity"]["row"] == 20


def test_table_kind_keeps_the_gaap_line_of_a_reconciliation_off_the_income_statement(model):
    m = _by_label(_run(model), "matched")
    assert m["Gross profit"]["row"] == 7 and m["GAAP gross profit"]["row"] == 24


def test_zero_never_matches_by_value_only_by_exact_label(model):
    """A zero would match every empty-ish row; a wrong match puts a number on the wrong line."""
    res = _run(model)
    assert _by_label(res, "matched")["Restructuring"]["row"] == 10
    assert _by_label(res, "matched")["Restructuring"]["by"] == "label"


def test_ytd_cash_flow_becomes_the_discrete_quarter(model):
    m = _by_label(_run(model), "matched")
    cfo = m["Net cash provided by operating activities"]
    assert cfo["row"] == 22 and cfo["cur"] == 22.0 and cfo["ytd"] is True


def test_balance_sheet_matches_prior_year_end(model):
    m = _by_label(_run(model), "matched")
    assert m["Cash and cash equivalents"]["row"] == 14 and m["Cash and cash equivalents"]["basis"] == "Q4 25"


def test_a_line_with_no_model_row_goes_to_the_agent(model):
    res = _run(model)
    assert [e["label"] for e in res["leftover"]] == ["Other income, net"]


def test_recast_maps_by_label_and_lists_the_difference_never_writes_it(model):
    """History changes only with the user's yes: the recast is a diff, the current value still enters."""
    res = _run(model, "recast")
    m = _by_label(res, "matched")
    assert m["Revenue"]["row"] == 4 and m["Revenue"]["by"] == "recast"
    d = {x["ref"]: x for x in res["diffs"]}
    assert d["F4"]["model"] == 120 and d["F4"]["new"] == 121.0 and d["F6"]["new"] == 49.0


def test_condensed_line_equal_to_two_rows_is_combined_and_its_parts_wait(model):
    res = _run(model, "combined")
    c = res["combined"][0]
    assert c["rows"] == [15, 16] and c["cur"] == 23.0


def test_thousands_release_matches_a_millions_model(model):
    m = _by_label(_run(model, "thousands"), "matched")
    assert m["Revenue"]["row"] == 4 and abs(m["Revenue"]["cur"] - 140.0) < 1e-9


def test_one_row_claimed_by_two_lines_is_ambiguous(model):
    """Two different lines (different current values) on one row: either could be wrong, so the agent decides."""
    rel = release.parse_text(mf.release_md(), "rel.md")
    rev = next(l for l in rel["lines"] if l["label"] == "Revenue")
    dup = dict(rev, id="rel.md:999", label="Net sales", line=999, values=[141.0] + rev["values"][1:])
    rel["lines"].append(dup)
    res = match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E")
    assert {e["label"] for e in res["ambiguous"]} >= {"Revenue", "Net sales"}
    assert all(e["row"] != 4 for e in res["matched"])


# --- review fixes -------------------------------------------------------------------------------------------------

def _amort28():
    """Values of a second amortization row 28 (the net-income block's add-back), equal to row 25's."""
    cols = [("Q1 25", "D"), ("Q2 25", "E"), ("Q3 25", "F"), ("Q4 25", "G"), ("Q1 26", "J"), ("Q2 26", "K")]
    return mf.values() | {f"{c}28": mf.DATA[p]["amort"] for p, c in cols}


def _with_rows(model, rows):
    """The fixture workbook plus rows {row: (section or None, label)} with a number in every actual column."""
    wb = openpyxl.load_workbook(model)
    ws = wb["MOD"]
    for r, (a, b) in rows.items():
        if a:
            ws[f"A{r}"] = a
        ws[f"B{r}"], ws[f"C{r}"] = b, "$m"
        for c in "DEFGJK":
            ws[f"{c}{r}"] = 1
    wb.save(model)
    return model


def _md(rows, header="|  | Three Months Ended September 30, |\n| --- | --- |\n|  | 2026 |  | 2025 |", title="Reconciliation of GAAP to Non-GAAP"):
    return f"## {title}\n\n(In millions)\n\n{header}\n" + "\n".join(f"| {l} | {a} |  | {b} |" for l, a, b in rows) + "\n"


def test_costs_the_model_stores_negative_get_the_models_sign(tmp_path):
    """The house model keeps '(-) Cost of sales' negative while releases print it positive: the match must hold and
    the typed value must be negative, or gross profit = revenue + cost of sales doubles instead of netting."""
    path = mf.model(str(tmp_path / "neg.xlsx"), neg_cost=True)
    rel = release.parse_text(mf.release_md(), "rel.md")
    res = match.match(rel, modmap.ModMap(path), mf.values(neg_cost=True), "Q3 26E")
    cos = _by_label(res, "matched")["Cost of sales"]
    assert cos["row"] == 6 and cos["by"] == "value" and cos["sign"] == -1 and cos["cur"] == -52.0
    assert res["diffs"] == []


def test_a_recast_of_a_negative_row_is_compared_with_the_sign_applied(tmp_path):
    """Release 49 vs model -48 is a recast of 1, not of 97; and the current value still enters negative."""
    path = mf.model(str(tmp_path / "neg.xlsx"), neg_cost=True)
    rel = release.parse_text(mf.release_md("recast"), "rel.md")
    res = match.match(rel, modmap.ModMap(path), mf.values(neg_cost=True), "Q3 26E")
    d = {x["ref"]: x for x in res["diffs"]}
    assert d["F6"]["model"] == -48 and d["F6"]["new"] == -49.0
    assert _by_label(res, "matched")["Cost of sales"]["cur"] == -52.0


def test_a_statement_line_never_falls_back_to_another_section(model):
    """'Other income' 3 / 2 equals the non-GAAP amortization row by chance; a statement line stays on its statement."""
    md = _md([("Revenue", "140.0", "120.0"), ("Net income", "30.0", "24.0"), ("Other income, net", "3.0", "2.0")],
             title="Statements of Operations")
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert [e["label"] for e in res["leftover"]] == ["Other income, net"]


def test_a_reconciliation_line_falls_back_only_to_key_metrics_and_only_with_a_shared_word(model):
    """A value equal by chance with no word in common is not evidence; and a KPI table's own claim on its row wins."""
    md = _md([("GAAP gross profit", "88.0", "72.0"), ("Units shipped", "1,500", "1,200"), ("Widgets", "9.0", "1,200")])
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert _by_label(res, "matched")["Units shipped"]["row"] == 27
    assert "Widgets" in _by_label(res, "leftover")
    both = md + "\n" + _md([("Units", "1,500", "1,200")], title="Key metrics")
    res = match.match(release.parse_text(both, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert _by_label(res, "matched")["Units"]["row"] == 27 and "Units shipped" in _by_label(res, "leftover")


def test_no_recast_onto_a_row_without_a_prior_value(model):
    """A label match is only a recast when the model has a number to differ from; else nothing proves the row."""
    g = {k: v for k, v in mf.values().items() if k != "F4"}
    res = match.match(release.parse_text(mf.release_md("recast"), "rel.md"), modmap.ModMap(model), g, "Q3 26E")
    assert "Revenue" in _by_label(res, "leftover") and all(e["row"] != 4 for e in res["matched"])
    assert all(d["label"] != "Revenue" for d in res["diffs"])


def test_no_recast_onto_a_layout_group_row(model):
    """A header row named like the line ('Distributor' above its US / International rows) never takes a number."""
    wb = openpyxl.load_workbook(model)
    wb["MOD"]["B28"] = "Distributor"                 # label only: no unit, no numbers
    wb.save(model)
    md = _md([("Units", "1,500", "1,200"), ("Distributor", "9.0", "8.0")], title="Key metrics")
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert "Distributor" in _by_label(res, "leftover") and res["diffs"] == []


def test_segment_columns_are_reported_not_guessed(model):
    """US / International / Total x 2026 / 2025: values[1] is International this year, not last year's total."""
    hdr = "|  | Three Months Ended September 30, |\n| --- | --- |\n| 2026 |  | 2025 |\n| (In millions) | US |  | Intl |  | Total |  | US |  | Intl |  | Total |"
    md = f"(In millions)\n\n{hdr}\n| Revenue | 100.0 |  | 40.0 |  | 140.0 |  | 85.0 |  | 35.0 |  | 120.0 |\n"
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert [e["label"] for e in res["no_layout"]] == ["Revenue"] and res["matched"] == []


def test_a_line_with_one_value_is_listed_not_dropped(model):
    md = _md([("Revenue", "140.0", "120.0")], title="Key metrics") + "| Backlog | 55.0 |\n"
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert [e["label"] for e in res["no_prior"]] == ["Backlog"]


def test_a_repeated_adjustment_pairs_in_order_with_the_models_numbered_rows(model):
    """Amortization is added back in the gross-profit block and again in the net-income block; MOD keys the second
    '#2'. Same prior in both, so the k-th printed one goes to the k-th row instead of both going to the agent."""
    _with_rows(model, {28: ("NON-GAAP METRICS", "Amortization of intangibles")})
    g = _amort28()
    md = _md([("GAAP gross profit", "88.0", "72.0"), ("Amortization of intangible assets (1)", "3.0", "2.0"),
              ("Net income", "30.0", "24.0"), ("Amortization of intangible assets (1)", "4.0", "2.0")])
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), g, "Q3 26E")
    am = sorted((e["row"], e["cur"]) for e in res["matched"] if e["label"].startswith("Amortization"))
    assert am == [(25, 3.0), (28, 4.0)] and res["ambiguous"] == []


def test_three_repeats_on_two_rows_with_different_values_go_to_the_agent(model):
    """Which occurrence has no row is unknowable when they print different numbers: no guess."""
    _with_rows(model, {28: ("NON-GAAP METRICS", "Amortization of intangibles")})
    g = _amort28()
    rows = [("Amortization of intangible assets (1)", v, "2.0") for v in ("3.0", "4.0", "5.0")]
    res = match.match(release.parse_text(_md(rows), "r.md"), modmap.ModMap(model), g, "Q3 26E")
    assert len(res["ambiguous"]) == 3 and not any(e["row"] in (25, 28) for e in res["matched"])


def test_the_same_line_printed_twice_enters_once(model):
    """Non-GAAP diluted shares are printed in the EPS block and again in the share reconciliation: same numbers, so
    the first enters and the repeat goes to the agent to skip."""
    md = _md([("Units", "1,500", "1,200"), ("Units", "1,500", "1,200")], title="Key metrics")
    res = match.match(release.parse_text(md, "r.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    assert [e["row"] for e in res["matched"]] == [27] and res["ambiguous"][0]["duplicate_of"] == "r.md:8"


def _cf_rows(ws):
    """Row 28 'Restricted cash' (a balance kept in the cash-flow section) and row 29 '(+/-) Other financing' (the sum
    of two printed lines), both with history in D..G, J, K."""
    ws["A28"], ws["B28"], ws["C28"] = "CASH FLOW STATEMENT", "Restricted cash", "$m"
    ws["B29"], ws["C29"] = "(+/-) Other financing", "$m"
    for c, rc, of in zip("DEFGJK", (1.0, 1.1, 1.2, 1.3, 1.4, 1.5), (1, 2, 3, 4, 2, 3)):
        ws[f"{c}28"], ws[f"{c}29"] = rc, of
    ws["L28"], ws["L29"] = "=K28", "=K29"


def _cf_model(tmp_path):
    p = mf.model(str(tmp_path / "m.xlsx"))
    wb = openpyxl.load_workbook(p)
    _cf_rows(wb["MOD"])
    wb.save(p)
    g = mf.values()
    for c, rc, of in zip("DEFGJK", (1.0, 1.1, 1.2, 1.3, 1.4, 1.5), (1, 2, 3, 4, 2, 3)):
        g[f"{c}28"], g[f"{c}29"] = rc, of
    return p, g


def _cf_release(extra):
    t = mf.release_md("normal")
    anchor = next(x for x in t.split("\n") if x.startswith("| Purchases of property"))
    return t.replace(anchor, anchor + "\n" + "\n".join(extra))


CF_EXTRA = ["| Proceeds from stock issuance | 15.0 |  |  | 10.0 |  |",
            "| Taxes paid on vested awards | (5.0 | ) |  | (4.0 | ) |",
            "| Reconciliation of cash, cash equivalents and restricted cash, end of period: |  |  |",
            "| Restricted cash | 0.9 |  |  | 1.2 |  |"]


def test_restricted_cash_in_a_cash_flow_table_is_a_balance_not_a_ytd_flow(tmp_path):
    """Read as a nine-month flow, restricted cash 0.1 became '=0.1-<earlier quarters>'. A balance is compared with
    the year-ago quarter end and typed as printed."""
    p, g = _cf_model(tmp_path)
    res = match.match(release.parse_text(_cf_release(CF_EXTRA), "rel.md"), modmap.ModMap(p), g, "Q3 26E")
    e = _by_label(res, "matched")["Restricted cash"]
    assert e["row"] == 28 and e["cur"] == 0.9 and e["ytd"] is False and e["basis"] == "Q3 25"


def test_a_row_that_is_the_sum_of_two_printed_lines_is_matched_once_with_both_cited(tmp_path):
    """The user's '(+/-) Other' adds two 10-Q lines; mapping only one types half the row. Their priors (10 - 4)
    equal the row's year-to-date prior (1 + 2 + 3): one entry, cur = the sum less earlier quarters."""
    p, g = _cf_model(tmp_path)
    res = match.match(release.parse_text(_cf_release(CF_EXTRA), "rel.md"), modmap.ModMap(p), g, "Q3 26E")
    e = next(x for x in res["matched"] if x["row"] == 29)
    assert e["by"] == "sum" and e["cur"] == 5.0 and [x["lineno"] for x in e["lines"]] == [e["lineno"], e["lineno"] + 1]
    assert not {l["label"] for l in res["leftover"]} & {"Proceeds from stock issuance", "Taxes paid on vested awards"}
    import actuals
    out, st = str(tmp_path / "o.xlsx"), str(tmp_path / "s.json")
    actuals.build(p, "Q3 26E", res, out, st, grid=mf.preprint())
    c = openpyxl.load_workbook(out)["MOD"]["L29"]
    assert c.value == "=10-K29-J29" and f"rel.md lines {e['lineno']} + {e['lineno'] + 1}" in c.comment.text


def test_a_sum_with_two_possible_sets_of_lines_goes_to_the_agent(tmp_path):
    """{10, -4} and {2, 4} both add up to the row's 6: guessing would type the wrong pair half the time."""
    p, g = _cf_model(tmp_path)
    extra = CF_EXTRA[:2] + ["| Other financing A | 1.0 |  |  | 2.0 |  |", "| Other financing B | 1.0 |  |  | 4.0 |  |"]
    res = match.match(release.parse_text(_cf_release(extra), "rel.md"), modmap.ModMap(p), g, "Q3 26E")
    assert all(x["row"] != 29 for x in res["matched"])
    assert {"Proceeds from stock issuance", "Other financing A"} <= {l["label"] for l in res["leftover"]}


def test_a_change_in_a_balance_sheet_line_above_the_cash_balances_stays_a_flow(model):
    """'Prepaid expenses' in the operating section is the CHANGE in prepaid expenses (a year-to-date flow); read as a
    balance because the balance sheet has that row, the real model's 'Inventory' change was typed wrong. Only in the
    tail below the cash balances does a balance-sheet name mean a balance."""
    extra = ["| Prepaid expenses | (1.0 | ) |  | (2.0 | ) |"] + CF_EXTRA[2:] + ["| Prepaid expenses | 7.0 |  |  | 6.0 |  |"]
    lines = [l for l in release.parse_text(_cf_release(extra), "rel.md")["lines"] if l["label"] == "Prepaid expenses" and l["kind"] == "cf"]
    m = modmap.ModMap(model)
    assert [match._as_balance(m, l) for l in lines] == [False, True]


def test_one_line_never_fills_a_row_the_model_builds_from_two_printed_numbers_this_year(tmp_path):
    """The real '(+/-) Other' was one line last year and two this year ('=(-37.6-3.8)-BR590'); the new line printed
    '—' last year, so priors cannot see it and the old line alone matched: the quarter came out 35.7 instead of -3.5.
    When this year's house form adds two printed numbers, a single line goes to the agent instead."""
    p, g = _cf_model(tmp_path)
    one = ["| Other financing activities | 9.0 |  |  | 6.0 |  |"]
    rel = release.parse_text(_cf_release(one), "rel.md")
    assert next(e for e in match.match(rel, modmap.ModMap(p), g, "Q3 26E", match.formulas(p))["matched"]
                if e["row"] == 29)["label"] == "Other financing activities"
    wb = openpyxl.load_workbook(p)
    wb["MOD"]["K29"] = "=(4+1)-J29"
    wb.save(p)
    res = match.match(rel, modmap.ModMap(p), g, "Q3 26E", match.formulas(p))
    assert all(e["row"] != 29 for e in res["matched"])
    assert "Other financing activities" in {l["label"] for l in res["leftover"]}
