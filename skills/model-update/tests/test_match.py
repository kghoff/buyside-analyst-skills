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
    rel = release.parse_text(mf.release_md(), "rel.md")
    dup = dict(next(l for l in rel["lines"] if l["label"] == "Revenue"), id="rel.md:999", label="Net sales", line=999)
    rel["lines"].append(dup)
    res = match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E")
    assert {e["label"] for e in res["ambiguous"]} >= {"Revenue", "Net sales"}
    assert all(e["row"] != 4 for e in res["matched"])
