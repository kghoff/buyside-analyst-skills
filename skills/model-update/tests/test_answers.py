import os

import match
import modmap
import release
import make_fixture as mf


def _res(model, research):
    path = os.path.join(research, "Press Releases", "_md", "2026 Q3 TEST release 2026-10-29.md")
    rel = release.parse_files([path], research)
    return match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E"), modmap.ModMap(model)


def _apply(res, answers, m, research, grid=None):
    return match.apply_answers(res, answers, m, research, grid or mf.values(), "Q3 26E")


def _ans(res, **kw):
    e = res["leftover"][0]
    return [{"line": e["line"], "anchor": f"{e['file']}:{e['lineno']}", "reason": "no such row in MOD", **kw}]


def test_new_line_is_reported_never_typed(model, research):
    """Adding a row would shift every reference in the workbook; that is model-historicals' job."""
    res, m = _res(model, research)
    out, probs = _apply(res, _ans(res, action="new_line"), m, research)
    assert probs == [] and out["new_lines"][0]["label"] == "Other income, net"
    assert all(e["label"] != "Other income, net" for e in out["matched"])


def test_an_anchor_that_is_not_the_lines_own_is_refused(model, research):
    res, m = _res(model, research)
    a = _ans(res, action="skip")
    a[0]["anchor"] = a[0]["anchor"].rsplit(":", 1)[0] + ":1"
    _, probs = _apply(res, a, m, research)
    assert probs and "not the line's own" in probs[0]


def test_every_open_line_needs_an_answer(model, research):
    res, m = _res(model, research)
    _, probs = _apply(res, [], m, research)
    assert probs == [f"{res['leftover'][0]['line']}: not answered"]


def _free_row_10(res):
    """Restructuring (row 10) matched by label; free it so the agent has an empty row to map onto."""
    res["matched"] = [e for e in res["matched"] if e["row"] != 10]
    return res


def test_agent_map_uses_the_scaled_value(model, research):
    res, m = _res(model, research)
    out, probs = _apply(_free_row_10(res), _ans(res, action="map", key="INCOME STATEMENT | Restructuring"), m, research)
    hit = next(e for e in out["matched"] if e["by"] == "agent")
    assert probs == [] and hit["cur"] == 2.0 and hit["row"] == 10


def test_an_agent_mapped_line_whose_prior_differs_from_the_model_is_a_diff(model, research):
    """Spec: the agent's map is checked like a recast; last year's 1.5 against the model's 0 is listed, not hidden."""
    res, m = _res(model, research)
    out, _ = _apply(_free_row_10(res), _ans(res, action="map", key="INCOME STATEMENT | Restructuring"), m, research)
    assert [(d["ref"], d["model"], d["new"]) for d in out["diffs"]] == [("F10", 0, 1.5)]


def test_agent_map_onto_a_row_that_already_has_a_value_is_refused(model, research):
    """Revenue is matched: a second number for the same cell would overwrite it."""
    res, m = _res(model, research)
    out, probs = _apply(res, _ans(res, action="map", key="INCOME STATEMENT | Revenue"), m, research)
    assert probs and "already has a value" in probs[0] and out is res


def test_two_answers_on_one_row_are_refused(model, research):
    res, m = _res(model, research)
    res = _free_row_10(res)
    extra = dict(res["leftover"][0], line="rel.md:900", label="Other income again")
    res["leftover"].append(extra)
    a = _ans(res, action="map", key="INCOME STATEMENT | Restructuring")
    a.append(dict(a[0], line="rel.md:900"))
    _, probs = _apply(res, a, m, research)
    assert probs == [f"rel.md:900: INCOME STATEMENT | Restructuring already has a value ({a[0]['line']})"]


def test_agent_map_gets_the_models_sign_and_the_discrete_cash_flow_quarter(model, research):
    """The agent names the row; code still does the arithmetic: YTD less earlier quarters, sign as the model keeps it."""
    res, m = _res(model, research)
    cfo = next(e for e in res["matched"] if e["row"] == 22)
    res["matched"].remove(cfo)
    rel = release.parse_files([os.path.join(research, "Press Releases", "_md", "2026 Q3 TEST release 2026-10-29.md")], research)
    line = next(l for l in rel["lines"] if l["id"] == cfo["line"])
    res["leftover"].append(match._open(line, True))
    a = _ans(res, action="skip") + [{"line": cfo["line"], "action": "map", "anchor": f"{cfo['file']}:{cfo['lineno']}",
                                     "key": cfo["key"], "reason": "operating cash flow"}]
    out, probs = _apply(res, a, m, research)
    hit = next(e for e in out["matched"] if e["by"] == "agent")
    assert probs == [] and hit["cur"] == 22.0 and hit["ytd"] is True and hit["sign"] == 1


def test_a_bad_answer_changes_nothing(model, research):
    """All answers are checked first: a half-applied answer file would enter some lines and lose others."""
    import copy
    res, m = _res(model, research)
    before = copy.deepcopy(res)
    a = _ans(res, action="map", key="INCOME STATEMENT | No such row")
    out, probs = _apply(res, a, m, research)
    assert probs and out == before and res == before


def test_an_ambiguous_line_can_be_mapped_or_combined_by_the_agent(model, research):
    """Ambiguous entries keep their values, so the agent's answer becomes a real match, never a silent skip."""
    res, m = _res(model, research)
    res = _free_row_10(res)
    amb = dict(res["leftover"].pop(0))
    res["ambiguous"].append({**amb, "rows": [10]})
    a = [{"line": amb["line"], "action": "combined", "keys": ["INCOME STATEMENT | Restructuring"],
          "anchor": f"{amb['file']}:{amb['lineno']}", "reason": "restructuring is reported in other income"}]
    out, probs = _apply(res, a, m, research)
    assert probs == [] and out["combined"][0]["cur"] == 2.0 and out["skipped"] == []


def test_the_anchor_check_reads_the_lines_cells(tmp_path):
    """A dash prints zero; '11.2' on the line does not prove 1.2."""
    (tmp_path / "r.md").write_text("x\n| Restructuring | — |  | 3.0 |\n| Other | 11.2 |  | 4.0 |\n")
    lines = {"a": {"file": "r.md", "lineno": 2, "values": [0.0, 3.0], "cur_i": 0, "prior_i": 1},
             "b": {"file": "r.md", "lineno": 3, "values": [1.2, 4.0], "cur_i": 0, "prior_i": 1}}
    assert match.check_anchor({"line": "a", "anchor": "r.md:2"}, lines, str(tmp_path)) is None
    assert "not on" in match.check_anchor({"line": "b", "anchor": "r.md:3"}, lines, str(tmp_path))
