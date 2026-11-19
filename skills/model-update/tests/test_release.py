import release
import make_fixture as mf


def _lines(variant="normal"):
    return release.parse_text(mf.release_md(variant), "rel.md")


def _get(rel, label):
    return next(l for l in rel["lines"] if l["label"] == label)


def test_statement_kinds_are_told_apart_so_lines_search_the_right_section():
    rel = _lines()
    kinds = {_get(rel, x)["kind"] for x in ("Revenue",)} | {_get(rel, "Total assets")["kind"]}
    assert kinds == {"is", "bs"}
    assert _get(rel, "Net cash provided by operating activities")["kind"] == "cf"
    assert _get(rel, "GAAP gross profit")["kind"] == "recon"
    assert _get(rel, "Units (thousands)")["kind"] == "other"


def test_values_keep_dollar_signs_parentheses_and_dashes_straight():
    rel = _lines()
    assert _get(rel, "Revenue")["values"] == [140.0, 120.0, 380.0, 350.0]
    assert _get(rel, "Purchases of property and equipment")["values"] == [-21.0, -16.0]
    assert _get(rel, "Restructuring")["values"] == [0.0, 0.0, 0.0, 0.0]


def test_thousands_are_scaled_to_millions_but_per_share_is_not():
    """A release in thousands must land in a millions model as millions; EPS is never scaled."""
    rel = _lines("thousands")
    rev = _get(rel, "Revenue")
    assert rev["factor"] == 0.001 and rev["values"][0] * rev["factor"] == 140.0
    assert _get(rel, "Diluted net income per share")["factor"] == 1.0


def test_decimals_set_the_match_tolerance():
    rel = _lines()
    assert _get(rel, "Revenue")["decimals"] == 1 and _get(rel, "Diluted net income per share")["decimals"] == 2
    assert abs(release.tolerance(_get(rel, "Revenue")) - 0.05) < 1e-6


def test_cash_flow_table_is_marked_year_to_date():
    rel = _lines()
    t = rel["tables"][_get(rel, "Net cash provided by operating activities")["table"]]
    assert t["ytd"] is True and rel["tables"][_get(rel, "Revenue")["table"]]["ytd"] is False


def test_every_line_cites_its_file_and_line_number():
    rel = _lines()
    l = _get(rel, "Revenue")
    assert l["file"] == "rel.md" and mf.release_md().split("\n")[l["line"] - 1].startswith("| Revenue |")
