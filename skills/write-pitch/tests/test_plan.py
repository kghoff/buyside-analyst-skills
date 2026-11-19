import copy, json, re, subprocess, sys, pathlib
import pytest
from conftest import FIX
import plan
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

def test_long_missing_hurdle_numbers():
    p = copy.deepcopy(BASE); del p["numbers"]["risk_ret"]
    out = plan.check(p, "Buy")
    assert "[R20] call is Long but numbers risk_ret are missing: the hurdle check can't run" in out

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
    p = copy.deepcopy(BASE); at(p, "quote")["quotes"] = ["q9"]
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

def at(p, kind):
    return next(s for s in p["slides"] if s["type"] == kind)

# why: a core type after slide 10 would be laid out as a support slide with no template
def test_core_type_after_slide_10(tmp_path):
    p = copy.deepcopy(BASE); p["slides"][14]["type"] = "thesis"
    rc, out = check(tmp_path, p); assert rc == 1 and "support layout" in out

def test_fewer_than_ten_slides(tmp_path):
    p = copy.deepcopy(BASE); p["slides"] = p["slides"][:7]
    rc, out = check(tmp_path, p); assert rc == 1 and "slide 8: expected the different slide" in out

def test_three_risks(tmp_path):
    p = copy.deepcopy(BASE); r = at(p, "risks")["risks"]; r.append(copy.deepcopy(r[0]))
    rc, out = check(tmp_path, p); assert rc == 1 and "exactly 2 risks, has 3" in out

# why: Short with the right verdict and an agreeing valuation Sell is the clean short path
def test_short_with_alpha_short_passes(tmp_path):
    p = copy.deepcopy(BASE); p["call"] = "Short"
    assert check(tmp_path, p, "--valuation-verdict", "sell", "--short-verdict", "Alpha Short")[0] == 0

def test_long_below_hurdles_with_override_passes():
    p = copy.deepcopy(BASE); p["numbers"]["base_ret"]["value"] = 0.10
    p["override"] = {"reason": "r", "evidence": "e"}
    assert plan.check(p, "Buy") == []

# why: every text kind is measured, not only takeaways
def test_budgets_on_sum_box_notes_and_cell():
    p = copy.deepcopy(BASE); p["sum_boxes"]["Trading Plan"] = "x" * 500
    at(p, "title")["notes"] = "x" * 1600; at(p, "table")["table"]["rows"][0][0] = "x" * 30
    out = "\n".join(plan.check(p, "Buy"))
    assert "sum_boxes Trading Plan" in out and "title) notes" in out and "table cell" in out

# why: a bare string would crash the builder that reads head and body
def test_string_thesis_point():
    p = copy.deepcopy(BASE); at(p, "thesis")["points"][0] = "just a string"
    assert any("thesis point 1 must be an object" in l for l in plan.check(p, "Buy"))

# why: thesis body is a box (420), risk sentences a bullet (170)
def test_budget_kinds():
    p = copy.deepcopy(BASE); at(p, "thesis")["points"][0]["body"] = "x" * 300
    assert plan.check(p, "Buy") == []
    at(p, "risks")["risks"][0]["mitigant"] = "x" * 200
    assert any("risk 1 mitigant" in l for l in plan.check(p, "Buy"))

# why: the pitch must not carry numbers the anchors never checked
def test_typed_number_flagged_but_years_pass():
    p = copy.deepcopy(BASE); at(p, "thesis")["points"][0]["body"] += " Up 15% by 2027E in Q3 26, 12x, 3.30."
    out = plan.check(p, "Buy")
    assert any("point 1 body: typed number '15%'" in l for l in out)
    assert any("'12x'" in l for l in out) and any("'3.30'" in l for l in out)
    assert not any("2027E" in l or "Q3" in l for l in out)

def test_quote_text_may_hold_numbers():
    p = copy.deepcopy(BASE); p["quotes"][0]["text"] = "We expect 15.5% growth."
    assert plan.check(p, "Buy") == []

def test_required_keys_and_supports():
    p = copy.deepcopy(BASE); del p["numbers"]["nobrainer_price"]
    p["slides"][12]["supports"] = "thesis.1"
    out = "\n".join(plan.check(p, "Buy"))
    assert "missing required keys nobrainer_price" in out and "none supports thesis.3" in out

def test_script_must_have_12_paragraphs():
    p = copy.deepcopy(BASE); p["pitch_sheet"]["script_3min"].pop()
    assert any("exactly 12 paragraphs" in l for l in plan.check(p, "Buy"))

# why: the lines go back to the agent, so a bad plan must produce lines, never a traceback
MALFORMED = [
    [], "text", 5, None,
    {"slides": "x", "numbers": [], "pitch_sheet": 3, "sum_boxes": [], "starting_verdicts": 7, "override": "x", "call": []},
    {"call": "Long", "numbers": {"irr_3y": 5, "base_ret": [], "risk_ret": "x"}, "slides": [1, None, []],
     "quotes": [3, None, {"id": []}], "pitch_sheet": {"know_cold": [[], {}], "hard_questions": [1], "napkin": "s"}},
    {"call": "Long", "starting_verdicts": {"valuation": [], "short": {}}, "override": [], "slides": [{"type": "thesis", "points": 4}],
     "sum_boxes": {"Buy price": 5, "Mgmt contact": None}, "numbers": {"price": {"value": 1, "shown": 3}}},
    {"slides": [{"type": "quote", "section": "support", "quotes": [[]], "supports": []},
                {"type": "two_column", "left": 5, "right": [], "table": 5, "cases": 4, "three_rs": 3}],
     "numbers": {"a": 1}},
]

def test_malformed_plans_never_traceback(tmp_path):
    for bad in MALFORMED:
        f = tmp_path / "bad.json"; f.write_text(json.dumps(bad))
        r = subprocess.run([sys.executable, str(P), "--plan", str(f)], capture_output=True, text=True)
        assert r.returncode == 1 and "Traceback" not in r.stderr, (bad, r.stderr)

def test_invalid_json_file(tmp_path):
    f = tmp_path / "bad.json"; f.write_text("{nope")
    r = subprocess.run([sys.executable, str(P), "--plan", str(f)], capture_output=True, text=True)
    assert r.returncode == 1 and "Traceback" not in r.stderr

def test_no_numbers_reported_once():
    p = copy.deepcopy(BASE); del p["numbers"]
    out = plan.check(p, "Buy")
    assert sum("numbers: missing" in l for l in out) == 1 and not any("is not defined in numbers" in l for l in out)

# why: the support section is the proof behind the core deck; too few is a thin pitch, too many a book report
def test_support_slide_count():
    p = copy.deepcopy(BASE)
    sup = [s for s in p["slides"] if s.get("section") == "support"]
    assert len(sup) == 10       # the fixture sits on the lower bound
    p["slides"].remove(next(s for s in sup if s["supports"] == "thesis.1"))
    assert any("[R12] support slides: needs 10 to 25" in l for l in plan.check(p, "Buy"))
    p = copy.deepcopy(BASE); p["slides"] += [copy.deepcopy(sup[0]) for _ in range(16)]
    assert any("has 26" in l for l in plan.check(p, "Buy"))

# why: the deck builder reads q and a from each checklist row, and a 15-question list must fit one slide
def test_checklist_shape():
    p = copy.deepcopy(BASE); c = at(p, "checklist")
    c["items"][0] = {"q": "Cheap?", "a": ""}
    c["items"][1] = {"q": "Cheap?", "a": "Yes, on every multiple we track"}
    out = "\n".join(plan.check(p, "Buy"))
    assert "item 1 needs a non-empty a" in out and "item 2 a: 31 characters" in out
    c["items"] = c["items"][:2]
    assert any("needs 3 to 15 items, has 2" in l for l in plan.check(p, "Buy"))

# why: the Valuation tab's own hurdle is the user's; the house 20% / 2:1 is only the fallback
def test_hurdles_from_valuation_tab(tmp_path):
    p = copy.deepcopy(BASE)     # IRR 18.3%, R/R 2.1: clears the house 2:1
    assert check(tmp_path, p, "--valuation-verdict", "Buy")[0] == 0
    rc, out = check(tmp_path, p, "--valuation-verdict", "Buy", "--buy-rr", "2.5")
    assert rc == 1 and "[R20]" in out and "under 2.5" in out
    assert check(tmp_path, p, "--valuation-verdict", "Buy", "--buy-rr", "2.5", "--irr-hurdle", "0.15")[0] == 0
    assert plan.check(p, "Buy", hurdles={"buy_rr": None}) == []      # a missing tab input falls back

# why: "pound the table" on a set-up under the pound hurdle is the equivocal-payoff mistake
def test_pound_needs_pound_rr(tmp_path):
    p = copy.deepcopy(BASE); p["action"] = "Pound the table"
    rc, out = check(tmp_path, p, "--valuation-verdict", "Buy"); assert rc == 1 and "[R21]" in out
    assert check(tmp_path, p, "--valuation-verdict", "Buy", "--pound-rr", "2")[0] == 0

# why: "Wait for {buy_price}" in action is filled by the builder, so its key must exist
def test_action_placeholder_checked():
    p = copy.deepcopy(BASE); p["action"] = "Wait for {entry}"
    assert any("[R13] action: {entry} is not defined" in l for l in plan.check(p, "Buy"))

# why: the short block and the Watch lead print on slide 9 like any other text
def test_risk_reward_short_and_lead_budgeted():
    p = copy.deepcopy(BASE); rr = at(p, "risk_reward")
    rr["short"] = {"type": "Alpha short", "borrow": "x" * 200}
    rr["lead"] = "Buy below {buy_price}, up 25%"
    out = "\n".join(plan.check(p, "Buy"))
    assert "short borrow: 200 characters" in out and "lead: typed number '25%'" in out

# why: every line goes back to the agent, and the schema's rule list must be the list the code checks
def test_every_problem_line_has_a_rule_id():
    for bad in MALFORMED + [copy.deepcopy(BASE)]:
        for line in plan.check(bad, "Sell", "watchlist"):
            assert re.match(r"\[R\d+\] ", line), line


# why: plan.py is the gate before the build; each of these passed it once and then crashed build_md or build_sheet
# (a KeyError mid-run, after the analyst's rounds were spent), so each must come back to the analyst as a problem
def _breakers():
    def mut(f):
        p = copy.deepcopy(BASE); f(p); return p
    rr = lambda p: at(p, "risk_reward")  # noqa: E731
    return {
        "slide without title": mut(lambda p: p["slides"][0].pop("title")),
        "slide without takeaway": mut(lambda p: p["slides"][12].pop("takeaway")),
        "case without eps": mut(lambda p: rr(p)["cases"][0].pop("eps")),
        "case without prob": mut(lambda p: rr(p)["cases"][1].pop("prob")),
        "case without pe": mut(lambda p: rr(p)["cases"][2].pop("pe")),
        "case without ret": mut(lambda p: rr(p)["cases"][0].pop("ret")),
        "three_rs without roll": mut(lambda p: rr(p)["three_rs"].pop("roll")),
        "three_rs without rerating": mut(lambda p: rr(p)["three_rs"].pop("rerating")),
        "event without date": mut(lambda p: at(p, "setup").update(events=[{"label": "Q4 print"}])),
        "event without label": mut(lambda p: at(p, "setup").update(events=[{"date": "2026-02-03"}])),
        "hard question as a string": mut(lambda p: p["pitch_sheet"]["hard_questions"].__setitem__(0, "Why now?")),
        "override reason key not in numbers": mut(lambda p: p.update(override={"reason": "{ghost}", "evidence": "e"})),
        "override evidence key not in numbers": mut(lambda p: p.update(override={"reason": "r", "evidence": "{gh}"})),
        "no action": mut(lambda p: p.pop("action")),
        "quote without file": mut(lambda p: p["quotes"][0].pop("file")),
        "slide quotes as a string": mut(lambda p: at(p, "quote").update(quotes="q1")),
        "table rows not lists": mut(lambda p: at(p, "table")["table"].update(rows=["Revenue"])),
        "items on a non-checklist slide": mut(lambda p: at(p, "table").update(items={"q": "x"})),
        "price box not a single key": mut(lambda p: p["sum_boxes"].update({"Buy price": "about {buy_price}"})),
        "lead as a number": mut(lambda p: rr(p).update(lead=5)),
    }


@pytest.mark.parametrize("name", sorted(_breakers()))
def test_plans_the_builders_cannot_build_are_rejected(tmp_path, name):
    rc, out = check(tmp_path, _breakers()[name], "--valuation-verdict", "Buy")
    assert rc == 1 and re.match(r"\[R\d+\] ", out), (name, out)


# why: "plan OK" must mean "builds". Every single-field breakage of the example plan (deleted, null, a number, text,
# an empty list or object, an unknown {key}) that plan.py accepts must build the Markdown copy and the pitch sheet;
# build_deck.py reads the same fields with .get and fallbacks (a one-off sweep of it found nothing; its own tests
# cover the fallbacks). One slide of each type, so the sweep stays fast.
SWEEP_BASE = copy.deepcopy(BASE)
SWEEP_BASE["override"] = {"reason": "Catalyst at {price}.", "evidence": "Valuation!C5"}
at(SWEEP_BASE, "setup")["events"] = [{"date": "2026-02-03", "label": "Q4 print"}]
at(SWEEP_BASE, "risk_reward").update(short={"type": "Alpha short", "borrow": "General collateral"},
                                     lead="Buy below {buy_price}")
at(SWEEP_BASE, "text_chart").update(image={"png": "Filings_Charts_p1_r1c1.png"})
at(SWEEP_BASE, "two_column")["caption"] = "A caption"
SHEET_READS = ("ticker", "call", "action", "numbers", "pitch_20s", "pitch_sheet")    # all build_sheet reads


def _paths(x, pre=()):
    items = x.items() if isinstance(x, dict) else enumerate(x) if isinstance(x, list) else ()
    for k, v in items:
        yield pre + (k,)
        yield from _paths(v, pre + (k,))


def test_every_plan_plan_py_accepts_builds(tmp_path):
    import build_md, build_sheet
    first = {s["type"]: i for i, s in reversed(list(enumerate(SWEEP_BASE["slides"])))}.values()
    gone, accepted = object(), 0
    for path in _paths(SWEEP_BASE):
        if (path[0] == "slides" and len(path) > 1 and path[1] not in first) or (path[0] == "numbers" and len(path) > 2):
            continue
        for bad in (gone, None, 5, "x", [], {}, "{ghost}"):
            p = copy.deepcopy(SWEEP_BASE)
            parent = p
            for k in path[:-1]:
                parent = parent[k]
            if bad is gone:
                parent.pop(path[-1])
            else:
                parent[path[-1]] = bad
            if plan.check(p, "Buy"):
                continue
            accepted += 1
            try:
                build_md.build(p, "", str(tmp_path / "p.md"))
                if path[0] in SHEET_READS:
                    build_sheet.build(p, str(tmp_path / "s.docx"))
            except Exception as e:
                raise AssertionError(f"plan OK but the build failed: {path} = {bad!r}: {e!r}") from e
    assert accepted > 100            # the sweep really built plans, not just rejected everything
