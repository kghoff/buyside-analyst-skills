import os

import match
import modmap
import release
import make_fixture as mf


def _res(model, research):
    path = os.path.join(research, "Press Releases", "_md", "2026 Q3 TEST release 2026-10-29.md")
    rel = release.parse_files([path], research)
    return match.match(rel, modmap.ModMap(model), mf.values(), "Q3 26E"), modmap.ModMap(model)


def _ans(res, **kw):
    e = res["leftover"][0]
    return [{"line": e["line"], "anchor": f"{e['file']}:{e['lineno']}", "reason": "no such row in MOD", **kw}]


def test_new_line_is_reported_never_typed(model, research):
    """Adding a row would shift every reference in the workbook; that is model-historicals' job."""
    res, m = _res(model, research)
    out, probs = match.apply_answers(res, _ans(res, action="new_line"), m, research)
    assert probs == [] and out["new_lines"][0]["label"] == "Other income, net"
    assert all(e["label"] != "Other income, net" for e in out["matched"])


def test_an_anchor_that_is_not_the_lines_own_is_refused(model, research):
    res, m = _res(model, research)
    a = _ans(res, action="skip")
    a[0]["anchor"] = a[0]["anchor"].rsplit(":", 1)[0] + ":1"
    _, probs = match.apply_answers(res, a, m, research)
    assert probs and "not the line's own" in probs[0]


def test_every_open_line_needs_an_answer(model, research):
    res, m = _res(model, research)
    _, probs = match.apply_answers(res, [], m, research)
    assert probs == [f"{res['leftover'][0]['line']}: not answered"]


def test_agent_map_uses_the_scaled_value(model, research):
    res, m = _res(model, research)
    out, probs = match.apply_answers(res, _ans(res, action="map", key="INCOME STATEMENT | Restructuring"), m, research)
    hit = next(e for e in out["matched"] if e["by"] == "agent")
    assert probs == [] and hit["cur"] == 2.0 and hit["row"] == 10
