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
