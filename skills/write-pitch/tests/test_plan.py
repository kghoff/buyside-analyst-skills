import copy, json, subprocess, sys, pathlib
from conftest import FIX
P = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "plan.py"
BASE = json.loads((FIX / "plan_example.json").read_text())

def check(tmp, plan, *extra):
    f = tmp / "p.json"; f.write_text(json.dumps(plan))
    r = subprocess.run([sys.executable, str(P), "--plan", str(f), *extra], capture_output=True, text=True)
    return r.returncode, r.stdout

def test_example_passes(tmp_path):
    assert check(tmp_path, BASE, "--valuation-verdict", "Buy")[0] == 0

def test_missing_core_slide(tmp_path):
    p = copy.deepcopy(BASE); del p["slides"][6]
    rc, out = check(tmp_path, p); assert rc == 1 and "valuation" in out

def test_four_thesis_points(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][3]["points"].append(p["slides"][3]["points"][0])
    rc, out = check(tmp_path, p); assert rc == 1 and "3 thesis points" in out

def test_over_budget_takeaway(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][1]["takeaway"] = "x" * 400
    rc, out = check(tmp_path, p); assert rc == 1 and "takeaway" in out

def test_unknown_placeholder(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][3]["points"][0]["body"] += " {nope}"
    rc, out = check(tmp_path, p); assert rc == 1 and "{nope}" in out

def test_override_required_when_call_differs(tmp_path):
    p = copy.deepcopy(BASE); p["call"] = "Watch"; p["override"] = None
    rc, out = check(tmp_path, p, "--valuation-verdict", "Buy"); assert rc == 1 and "override" in out

def test_short_needs_alpha_short(tmp_path):
    p = copy.deepcopy(BASE); p["call"] = "Short"; p["override"] = {"reason": "x", "evidence": "y"}
    rc, out = check(tmp_path, p, "--short-verdict", "watchlist"); assert rc == 1 and "alpha short" in out

# why: the PM reads the deck, so a deck without Bear hides the downside
def test_risk_reward_needs_bear(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][8]["cases"] = p["slides"][8]["cases"][:2]
    rc, out = check(tmp_path, p); assert rc == 1 and "bear" in out.lower()

# why: a support slide with no section would never be placed in the deck
def test_support_needs_section(tmp_path):
    p = copy.deepcopy(BASE); del p["slides"][10]["section"]
    rc, out = check(tmp_path, p); assert rc == 1 and "section" in out

# why: a long that misses both the IRR and R/R hurdles is not a buy unless the analyst argues it
def test_long_below_both_hurdles(tmp_path):
    p = copy.deepcopy(BASE); p["numbers"]["base_ret"]["value"] = 0.10
    rc, out = check(tmp_path, p, "--valuation-verdict", "Buy"); assert rc == 1 and "hurdle" in out
    p["call"] = "Watch"; p["override"] = {"reason": "r", "evidence": "e"}
    assert check(tmp_path, p, "--valuation-verdict", "Buy")[0] == 0

def test_long_missing_hurdle_numbers(tmp_path):
    p = copy.deepcopy(BASE); del p["numbers"]["risk_ret"]; p["slides"][1]["takeaway"] = "x"
    p["slides"][8]["takeaway"] = "x"; p["slides"][8]["cases"][1]["ret"] = "x"; p["slides"][8]["cases"][2]["ret"] = "x"
    p["slides"][2]["bullets"] = ["x"]
    rc, out = check(tmp_path, p, "--valuation-verdict", "Buy"); assert rc == 1 and "hurdle check can't run" in out

def test_know_cold_key_missing(tmp_path):
    p = copy.deepcopy(BASE); p["pitch_sheet"]["know_cold"].append("ghost")
    rc, out = check(tmp_path, p); assert rc == 1 and "ghost" in out

# why: the template box holds what is shown, so "{price}" (7 chars) must count as "$72.40" not as its key
def test_budget_after_substitution(tmp_path):
    p = copy.deepcopy(BASE)
    p["numbers"]["price"]["shown"] = "y" * 200
    p["slides"][1]["takeaway"] = "{price}"
    rc, out = check(tmp_path, p); assert rc == 1 and "takeaway" in out and "200" in out

def test_unknown_quote_id(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][12]["quotes"] = ["q9"]
    rc, out = check(tmp_path, p); assert rc == 1 and "q9" in out

def test_number_needs_anchor(tmp_path):
    p = copy.deepcopy(BASE); del p["numbers"]["price"]["anchor"]
    rc, out = check(tmp_path, p); assert rc == 1 and "price" in out and "anchor" in out

def test_empty_notes(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][0]["notes"] = ""
    rc, out = check(tmp_path, p); assert rc == 1 and "notes" in out

def test_two_risks_with_prob(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][4]["risks"][0]["prob"] = 1.5
    rc, out = check(tmp_path, p); assert rc == 1 and "prob" in out

def test_unknown_sum_box(tmp_path):
    p = copy.deepcopy(BASE); p["sum_boxes"]["Mystery"] = "x"
    rc, out = check(tmp_path, p); assert rc == 1 and "Mystery" in out

def test_hard_questions_count(tmp_path):
    p = copy.deepcopy(BASE); p["pitch_sheet"]["hard_questions"] = p["pitch_sheet"]["hard_questions"][:2]
    rc, out = check(tmp_path, p); assert rc == 1 and "hard_questions" in out
