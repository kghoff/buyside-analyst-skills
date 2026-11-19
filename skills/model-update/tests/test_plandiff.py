import plandiff

OLD = {"rows": [{"key": "A", "growth": 0.10}, {"key": "B", "pct": 0.4}], "layout": [1]}


def test_a_changed_key_without_a_reason_fails():
    """Targeted revision: everything the agent did not justify must carry over exactly."""
    new = {"rows": [{"key": "A", "growth": 0.12}, {"key": "B", "pct": 0.41}], "layout": [1]}
    probs = plandiff.check(OLD, new, [{"key": "A", "was": "10%", "now": "12%", "anchor": "rel.md:3",
                                       "reason": "guide raised", "thesis": "supports"}])
    assert probs == ["B changed with no entry in changes.json"]


def test_an_entry_for_an_unchanged_key_fails():
    probs = plandiff.check(OLD, OLD, [{"key": "A", "was": "1", "now": "2", "anchor": "x", "reason": "y", "thesis": "none"}])
    assert probs == ["changes.json lists A but the plan did not change it"]


def test_top_level_fields_count_as_keys():
    new = dict(OLD, guidance=[{"metric": "Revenue"}])
    assert plandiff.check(OLD, new, []) == ["guidance changed with no entry in changes.json"]


def test_a_roll_that_would_insert_or_move_mod_rows_is_refused_even_with_a_reason():
    """state.json names waiting cells by row; new rows, moves, layout or a new seasonality row would shift them and the
    10-Q rerun would fill the wrong cells. Structure is /model-forecast's job, so the roll never changes it."""
    ch = lambda k: [{"key": k, "was": "a", "now": "b", "anchor": "x", "reason": "y", "thesis": "none"}]
    probs = plandiff.check(OLD, dict(OLD, layout=[2]), ch("layout"))
    assert len(probs) == 1 and probs[0].startswith("layout changes the model's rows")
    new = {"rows": [{"key": "A", "method": "seasonal"}, {"key": "B", "pct": 0.4}], "layout": [1]}
    probs = plandiff.check(OLD, new, ch("A"))
    assert len(probs) == 1 and "seasonality row" in probs[0]


def test_thesis_must_be_one_of_three_and_undercuts_go_first_in_bold():
    new = {"rows": [{"key": "A", "growth": 0.08}, {"key": "B", "pct": 0.5}], "layout": [1]}
    ch = [{"key": "B", "was": "40%", "now": "50%", "anchor": "a", "reason": "r", "thesis": "none"},
          {"key": "A", "was": "10%", "now": "8%", "anchor": "a", "reason": "r", "thesis": "undercuts"}]
    assert plandiff.check(OLD, new, ch) == []
    page = plandiff.page(ch, "| h |", "| h2 |", "Revenue $520-530M")
    assert page.index("**A**") < page.index("| B |")
    assert plandiff.check(OLD, new, [dict(ch[0], thesis="maybe"), ch[1]]) == ["B: thesis must be none, supports or undercuts"]
