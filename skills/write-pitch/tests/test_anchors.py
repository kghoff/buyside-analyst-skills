# skills/write-pitch/tests/test_anchors.py
import copy
import json
import pathlib
import subprocess
import sys

from conftest import FIX

A = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "anchors.py"
BASE = json.loads((FIX / "plan_example.json").read_text())


def run(tmp, plan, values, research=None, json_out=None):
    f = tmp / "p.json"
    f.write_text(json.dumps(plan))
    cmd = [sys.executable, str(A), "--plan", str(f), "--values", str(values),
           "--research", str(research or FIX / "research")]
    if json_out:
        cmd += ["--json", str(json_out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout


def with_number(key, value, shown, anchor):
    p = copy.deepcopy(BASE)
    p["numbers"][key] = {"value": value, "shown": shown, "anchor": anchor}
    return p


def test_example_ok(tmp_path, model_values):
    rc, out = run(tmp_path, BASE, model_values)
    assert rc == 0 and "anchors OK" in out


def test_wrong_cell(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["price"]["value"] = 80.0
    p["numbers"]["price"]["shown"] = "$80.00"
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "[A1] price" in out


def test_quote_not_on_line(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["quotes"][0]["line"] += 1
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "[A4] q1" in out


def test_calc_mismatch(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["irr_3y"]["value"] = 0.2
    p["numbers"]["irr_3y"]["shown"] = "20.0%"
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "[A3] irr_3y" in out


def test_repeat_shown_differently(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["price_again"] = dict(p["numbers"]["price"], shown="$72.4")
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "[A5] price_again" in out


def test_repeat_same_shown_ok(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["price_again"] = dict(p["numbers"]["price"])
    assert run(tmp_path, p, model_values)[0] == 0


def test_shown_inconsistent_with_value(tmp_path, model_values):
    # the slide would print $74.20 while the cell and value say 72.40: the audience would see a wrong number
    p = copy.deepcopy(BASE)
    p["numbers"]["price"]["shown"] = "$74.20"
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "price" in out and "$74.20" in out


def test_percent_value_must_be_fraction(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["base_ret"]["value"] = 31
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "base_ret" in out


def test_rounding_follows_shown(tmp_path, model_values):
    # the cell holds 12.5: value 12.52 shown "12.5" is within the half-unit of the shown digit; 12.6 / "12.6" is not
    assert run(tmp_path, with_number("d", 12.52, "12.5", "'Short Check'!B5"), model_values)[0] == 0
    assert run(tmp_path, with_number("d", 12.6, "12.6", "'Short Check'!B5"), model_values)[0] == 1


def test_quoted_tab_with_space(tmp_path, model_values):
    ok = with_number("dtc", 12.5, "12.5", "'Short Check'!B5")
    assert run(tmp_path, ok, model_values)[0] == 0
    ok["numbers"]["dtc"]["anchor"] = "Short Check!B5"
    assert run(tmp_path, ok, model_values)[0] == 0


def test_missing_tab_empty_and_text_cells(tmp_path, model_values):
    for anchor in ("Nope!A1", "Valuation!Z99", "'Short Check'!B6"):
        rc, out = run(tmp_path, with_number("x", 1.0, "1.0", anchor), model_values)
        assert rc == 1 and "[A1] x" in out, anchor


def test_line_number_must_not_match_longer_number(tmp_path, model_values):
    r = tmp_path / "res"
    r.mkdir()
    (r / "a.md").write_text("Revenue grew 150 units.\nRevenue grew 15 units and 1,500 more.\n")
    bad = with_number("n", 15.0, "15", "a.md:1")
    rc, out = run(tmp_path, bad, model_values, research=r)
    assert rc == 1 and "[A2] n" in out
    assert "[A2] n" not in run(tmp_path, with_number("n", 15.0, "15", "a.md:2"), model_values, research=r)[1]


def test_plus_sign_and_symbols_dropped_on_line(tmp_path, model_values):
    r = tmp_path / "res"
    r.mkdir()
    (r / "a.md").write_text("Margin up 31% and sales were $1,204 million.\nLoss of (18%).\n")
    for shown, v, ln in (("+31%", 0.31, 1), ("$1,204m", 1204.0, 1), ("(18%)", -0.18, 2)):
        rc, out = run(tmp_path, with_number("n", v, shown, f"a.md:{ln}"), model_values, research=r)
        assert "[A2] n" not in out, (shown, out)


def test_file_anchor_outside_root_or_missing(tmp_path, model_values):
    for anchor in ("../x.md:1", "nope.md:1", "Earnings Calls/_md/2026 Q3 XYZ call.md:9999"):
        rc, out = run(tmp_path, with_number("n", 15.0, "15", anchor), model_values)
        assert rc == 1 and "[A2] n" in out, anchor


def test_calc_disallowed_syntax_is_a_problem_not_run(tmp_path, model_values):
    marker = tmp_path / "pwned"
    for expr in ("__import__('os').system('touch %s')" % marker, "price.real", "price**9999999", "[1]",
                 "open('x')", "nosuchkey*2"):
        rc, out = run(tmp_path, with_number("c", 1.0, "1.0", "calc: " + expr), model_values)
        assert rc == 1 and "[A3] c" in out, expr
    assert not marker.exists()


def test_calc_cycle_is_a_problem(tmp_path, model_values):
    p = with_number("a", 1.0, "1.0", "calc: b+1")
    p["numbers"]["b"] = {"value": 0.0, "shown": "0.0", "anchor": "calc: a-1"}
    rc, out = run(tmp_path, p, model_values)
    assert rc == 1 and "[A3]" in out and "cycle" in out


def test_calc_functions_allowed(tmp_path, model_values):
    p = with_number("c", 120.0, "$120", "calc: max(price, target_3y) + min(1,2) - 1 + abs(0-0)")
    assert run(tmp_path, p, model_values)[0] == 0


def test_json_output_lists_failures_with_rule_ids(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["price"]["value"] = 80.0
    p["numbers"]["price"]["shown"] = "$80.00"
    p["quotes"][0]["line"] += 1
    out_json = tmp_path / "out.json"
    rc, out = run(tmp_path, p, model_values, json_out=out_json)
    items = json.loads(out_json.read_text())
    assert rc == 1
    assert {"key": "price", "rule": "A1"}.items() <= next(i for i in items if i.get("key") == "price").items()
    q = next(i for i in items if i.get("quote") == "q1")
    assert q["rule"] == "A4" and q["problem"]
    assert all(i["problem"] for i in items)


def test_every_problem_line_starts_with_rule_id(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["price"]["value"] = 80.0
    p["quotes"][0]["line"] += 1
    p["numbers"]["x"] = {"value": 1.0, "shown": "1", "anchor": "calc: 1/0"}
    rc, out = run(tmp_path, p, model_values)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert rc == 1 and len(lines) >= 3 and all(ln.startswith("[A") for ln in lines)


def test_quote_normalises_quotes_dashes_and_space(tmp_path, model_values):
    r = tmp_path / "res"
    r.mkdir()
    (r / "a.md").write_text("He said “we’re  growing – fast” today.\n")
    p = copy.deepcopy(BASE)
    p["quotes"] = [{"id": "q9", "text": "\"we're growing - fast\"", "file": "a.md", "line": 1}]
    p["numbers"] = {k: v for k, v in p["numbers"].items() if k != "guide_growth"}
    assert run(tmp_path, p, model_values, research=r)[0] == 0
    p["quotes"][0]["text"] = "We're growing"       # case-sensitive
    assert run(tmp_path, p, model_values, research=r)[0] == 1


def test_calc_wrong_arity_is_a_problem(tmp_path, model_values):
    for expr in ("max(2)", "abs(1,2)", "min()", "abs()"):
        rc, out = run(tmp_path, with_number("c", 1.0, "1.0", "calc: " + expr), model_values)
        assert rc == 1 and "[A3] c" in out and "Traceback" not in out, expr


def test_bad_quotes_are_problems_not_crashes(tmp_path, model_values):
    for q in ("just a string", None, {"id": "e", "text": "  ", "file": "Earnings Calls/_md/2026 Q3 XYZ call.md", "line": 214},
              {"id": "b", "text": "We expect", "file": "Earnings Calls/_md/2026 Q3 XYZ call.md", "line": True},
              {"id": "z", "text": "We expect", "file": "Earnings Calls/_md/2026 Q3 XYZ call.md", "line": 0}):
        p = copy.deepcopy(BASE)
        p["quotes"].append(q)
        rc, out = run(tmp_path, p, model_values)
        assert rc == 1 and "[A4]" in out, q


def test_digit_inside_q3_is_not_a_match(tmp_path, model_values):
    r = tmp_path / "res"
    r.mkdir()
    (r / "a.md").write_text("Q3 results were fine.\nGrowth was 28x or 3rd place, up 3.\n")
    def hit(v, shown, ln):
        return "[A2] n" in run(tmp_path, with_number("n", v, shown, f"a.md:{ln}"), model_values, research=r)[1]
    assert hit(3.0, "3", 1)
    assert not hit(3.0, "3", 2)
    assert not hit(28.0, "28x", 2)


def test_formula_without_value_says_not_recalculated(tmp_path, model_values):
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Valuation"
    wb["Valuation"]["H2"] = "=1+1"
    f = tmp_path / "raw.xlsx"
    wb.save(f)
    rc, out = run(tmp_path, with_number("x", 2.0, "2", "Valuation!H2"), f)
    assert rc == 1 and "holds a formula but no value" in out and "recalculated" in out


def test_dependent_calc_names_the_failed_key(tmp_path, model_values):
    p = copy.deepcopy(BASE)
    p["numbers"]["price"]["value"] = 80.0
    p["numbers"]["price"]["shown"] = "$80.00"
    rc, out = run(tmp_path, p, model_values)
    line = next(ln for ln in out.splitlines() if ln.startswith("[A3] irr_3y"))
    assert "depends on price, which failed [A1]" in line


def test_percent_points_cell_passes_and_fraction_hint(tmp_path, model_values):
    # Short Check!B5 holds 12.5, a cell in percentage points: value 0.125 shown 12.5% passes
    assert run(tmp_path, with_number("d", 0.125, "12.5%", "'Short Check'!B5"), model_values)[0] == 0
    rc, out = run(tmp_path, with_number("d", 31.0, "31%", "Valuation!F20"), model_values)
    assert rc == 1 and "fractions" in out


def test_negative_forms(tmp_path, model_values):
    r = tmp_path / "res"
    r.mkdir()
    (r / "a.md").write_text("Loss of $(3.10) and down 15%.\n")
    for shown, v in (("$(3.10)", -3.10), ("\u201315%", -0.15), ("\u221215%", -0.15), ("-15%", -0.15)):
        rc, out = run(tmp_path, with_number("n", v, shown, "a.md:1"), model_values, research=r)
        assert "[A2] n" not in out, (shown, out)
    rc, out = run(tmp_path, with_number("n", 0.15, "\u201315%", "a.md:1"), model_values, research=r)
    assert "[A2] n" in out


def test_units_hint(tmp_path, model_values):
    rc, out = run(tmp_path, with_number("n", 1.25, "$1.25bn", "SUM!H8"), model_values)
    assert rc == 1 and "other units" in out and "$1,250m" in out


def test_lowercase_ref_and_windows_path(tmp_path, model_values):
    assert run(tmp_path, with_number("n", 72.4, "$72.40", "valuation!c5"), model_values)[0] == 0
    rc, out = run(tmp_path, with_number("n", 15.0, "15", "Earnings Calls\\_md\\2026 Q3 XYZ call.md:214"),
                  model_values)
    assert rc == 1 and "forward slashes" in out
