"""Actuals in a model built the house way (model-historicals and the user's own models): Q4 = FY less Q1-Q3 with the
FY typed, Q4 balances = FY, Q2/Q3 cash flow '=<YTD>-earlier quarters'. Every test here guards a way the year-ago
column can lie when it is copied blindly."""
import json

import openpyxl
from openpyxl.comments import Comment

import actuals
import match
import modmap
import release
import make_fixture as mf

BLUE = "FF0000FF"


def _q4(tmp_path, edit=None, drop_fy=()):
    p = mf.model(str(tmp_path / "m.xlsx"), house=True, actual_q3=True)
    if edit:
        wb = openpyxl.load_workbook(p)
        edit(wb["MOD"])
        wb.save(p)
    rel = release.parse_text(mf.release_q4_md(), "q4.md")
    res = match.match(rel, modmap.ModMap(p), mf.values(actual_q3=True), "Q4 26E")
    for e in res["matched"]:
        if e["row"] in drop_fy:
            e.pop("fy_cur", None)
    out, st = str(tmp_path / "o.xlsx"), str(tmp_path / "s.json")
    rep = actuals.build(p, "Q4 26E", res, out, st, grid=mf.preprint())
    return openpyxl.load_workbook(out)["MOD"], rep, json.load(open(st))


def test_the_q4_10k_fills_the_year_column_and_q4_follows_through_its_plug(tmp_path):
    """The release left operating expenses out: the year keeps its forecast as a placeholder and Q4 is last year's
    plug over it. The 10-K's annual table (2026 | 2025 | 2024) prints the year: it replaces the placeholder in the
    YEAR column (never the quarter) and Q4 follows; a typed year it agrees with is not a difference."""
    p = mf.model(str(tmp_path / "m.xlsx"), house=True, actual_q3=True)
    text = "\n".join(x for x in mf.release_q4_md().split("\n") if not x.startswith("| Total operating expenses"))
    res = match.match(release.parse_text(text, "q4.md"), modmap.ModMap(p), mf.values(actual_q3=True), "Q4 26E")
    out, sp = str(tmp_path / "o.xlsx"), str(tmp_path / "s.json")
    actuals.build(p, "Q4 26E", res, out, sp, grid=mf.preprint())
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws["N8"].value == mf.preprint()["N8"] and ws["N8"].font.color.rgb == "FFC65911"
    assert ws["M8"].value == "=N8-L8-K8-J8"
    k = match.match(release.parse_text(mf.tenk_md(), "k.md"), modmap.ModMap(out), mf.values(actual_q3=True), "Q4 26")
    opex = next(e for e in k["matched"] if e["row"] == 8)
    assert opex["cur"] is None and opex["fy_cur"] == 140.0 and opex["basis"] == "2025"
    rep = actuals.fill_tenq(out, k, str(tmp_path / "t.xlsx"), sp)
    w = openpyxl.load_workbook(str(tmp_path / "t.xlsx"))["MOD"]
    assert w["N8"].value == 140.0 and w["N8"].font.color.rgb == BLUE and w["M8"].value == "=N8-L8-K8-J8"
    assert "N8" in rep["filled"] and "M8" not in rep["filled"] and rep["differences"] == []


def _q3(tmp_path, text=None, edit=None, restate=False, house=True):
    p = mf.model(str(tmp_path / "m.xlsx"), house=house)
    if edit:
        wb = openpyxl.load_workbook(p)
        edit(wb["MOD"])
        wb.save(p)
    rel = release.parse_text(text or mf.release_md("normal"), "rel.md")
    res = match.match(rel, modmap.ModMap(p), mf.values(), "Q3 26E")
    res["leftover"] = []
    out, st = str(tmp_path / "o.xlsx"), str(tmp_path / "s.json")
    rep = actuals.build(p, "Q3 26E", res, out, st, restate=restate, grid=mf.preprint())
    return openpyxl.load_workbook(out)["MOD"], rep, json.load(open(st)), out, st


def _no_cycle(ws, cols):
    """No formula in the written columns reads, directly or through others there, its own cell."""
    f = {f"{c}{r}": ws[f"{c}{r}"].value[1:] for c in cols for r in range(3, 28)
         if isinstance(ws[f"{c}{r}"].value, str) and ws[f"{c}{r}"].value.startswith("=")}

    def reach(ref, seen):
        for d in actuals.deps(f.get(ref, "")):
            if d in f and d not in seen:
                seen.add(d)
                reach(d, seen)
        return seen
    return [r for r in f if r in reach(r, set())]


def test_q4_types_the_full_year_and_plugs_q4_so_there_is_no_circular_reference(tmp_path):
    """Copying last year's 'Q4 = FY - Q1..Q3' AND keeping the forecast 'FY = SUM(Q1:Q4)' made a loop."""
    ws, _, _ = _q4(tmp_path)
    assert ws["N4"].value == 530.0 and ws["N4"].font.color.rgb == BLUE
    assert ws["M4"].value == "=N4-L4-K4-J4"
    assert _no_cycle(ws, "MN") == []


def test_q4_balances_follow_last_years_direction(tmp_path):
    """Last year the Q4 balance linked to the typed year-end; this year does the same."""
    ws, _, _ = _q4(tmp_path)
    assert ws["N14"].value == 85.0 and ws["M14"].value == "=N14"


def test_q4_cash_flow_is_the_twelve_months_less_q1_to_q3(tmp_path):
    ws, _, _ = _q4(tmp_path)
    assert ws["N22"].value == 85.0 and ws["M22"].value == "=N22-SUM(J22:L22)"


def test_q4_line_without_a_full_year_column_is_typed_and_the_year_sums(tmp_path):
    """The reconciliation prints only the quarter: Q4 cannot be a plug of a year nobody printed."""
    ws, _, _ = _q4(tmp_path)
    assert ws["M25"].value == 3.0 and ws["N25"].value == "=SUM(J25:M25)"


def test_q4_per_share_line_without_a_full_year_value_waits_rather_than_summing(tmp_path):
    """Four quarterly EPS figures do not add up to the year's EPS (share counts move): the year keeps its forecast as
    a flagged placeholder until the 10-K."""
    ws, rep, _ = _q4(tmp_path, drop_fy=(12,))
    assert ws["M12"].value == 1.32 and ws["N12"].value == mf.preprint()["N12"]
    assert ws["N12"].font.color.rgb == "FFC65911" and "awaiting 10-K" in ws["N12"].comment.text
    assert "N12" in {a["ref"] for a in rep["awaiting"]}


def test_fy_header_stays_a_number_when_last_years_is(tmp_path):
    """A text '2026' next to a numeric 2025 breaks lookups and charts keyed on the year."""
    def num(ws):
        ws["H2"] = 2025
    ws, rep, _ = _q4(tmp_path, edit=num)
    assert ws["N2"].value == 2026 and rep["header"] == ["Q4 26", 2026]


def test_q3_cash_flow_uses_this_years_ytd_not_last_years_constant(tmp_path):
    """Translating last year's '=48-E22-D22' would drag 2025's YTD into 2026."""
    ws, _, _, _, _ = _q3(tmp_path)
    assert ws["L22"].value == "=61-K22-J22" and ws["L22"].font.color.rgb == BLUE


def test_a_range_reads_its_middle_cells(tmp_path):
    """SUM(L14:L16) reads L15: a waiting L15 must not leave the total summing a blank."""
    text = "\n".join(x for x in mf.release_md("normal").split("\n") if not x.startswith("| Other current assets"))
    ws, _, st, _, _ = _q3(tmp_path, text=text)
    assert ws["L15"].value == 15.5 and ws["L17"].value == 103.0      # a placeholder in the middle: the total is typed
    assert {"ref": "L17", "formula": "SUM(L14:L16)"} in st["typed_subtotals"]


def test_refs_expand_ranges_and_ignore_function_names():
    assert actuals.deps("SUM(L14:L16)") == {"L14", "L15", "L16"}
    assert actuals.deps("LOG10(L4)+L5") == {"L4", "L5"}
    assert actuals.structure("SUM(L14:L16)", "L") and not actuals.structure("L4*1.1", "L")
    assert not actuals.structure("L4+M4", "L") and not actuals.structure("Other!L4", "L")


def test_ttm_and_averages_over_earlier_columns_are_structure_but_later_or_absolute_are_inputs():
    """A TTM sum or an average of earlier quarters only re-arranges numbers already in the model, so it is copied
    like a subtotal; a Q4 plug reads the year column to its RIGHT (an input), and an absolute reference keeps
    pointing at last year."""
    assert actuals.structure("SUM(I386:L386)", "L") and actuals.structure("AVERAGE(J5,K5,L5)", "L")
    assert actuals.structure("K601", "L")                      # beginning cash = last quarter's ending cash
    assert not actuals.structure("N4-L4-K4-J4", "M") and not actuals.structure("SUM($I386:L386)", "L")


def test_an_absolute_reference_makes_the_year_ago_formula_an_input(tmp_path):
    """'=F7-$F$8' translated keeps pointing at last year; the reported value goes in instead."""
    def absref(ws):
        ws["F9"] = "=F7-$F$8"
    ws, _, _, _, _ = _q3(tmp_path, edit=absref)
    assert ws["L9"].value == 52.0 and ws["L9"].font.color.rgb == BLUE
    assert not actuals.structure("F11/$F$27", "F")


def _tenq_after(tmp_path, out, sp, text=None):
    v = mf.values()
    v.update({"L4": 140, "L6": 52, "L7": 88, "L24": 88})
    res = match.match(release.parse_text(text or mf.tenq_md(), "q.md"), modmap.ModMap(out), v, "Q3 26")
    rep = actuals.fill_tenq(out, res, str(tmp_path / "t.xlsx"), sp)
    return openpyxl.load_workbook(str(tmp_path / "t.xlsx"))["MOD"], rep, json.load(open(sp))


def test_a_formula_over_a_placeholder_stays_a_formula_and_the_10q_replaces_the_placeholder(tmp_path):
    """Non-GAAP gross profit = GAAP + amortization: the release does not print either, so amortization keeps its
    forecast as a placeholder and the formula keeps working over it; the 10-Q's number replaces the placeholder
    (blue, sourced) and the formula never changes."""
    text = mf.release_md("normal")
    text = text[:text.index("## Reconciliation")] + text[text.index("## Key metrics"):]
    ws, rep, st, out, sp = _q3(tmp_path, text=text)
    assert ws["L25"].value == 3.0 and ws["L25"].font.color.rgb == "FFC65911" and ws["L26"].value == "=L24+L25"
    assert st["typed_subtotals"] == [] and "L26" not in {a["ref"] for a in st["awaiting"]}
    w, rep2, st2 = _tenq_after(tmp_path, out, sp)
    assert w["L25"].value == 3.0 and w["L25"].font.color.rgb == BLUE and "L25" in rep2["filled"]
    assert w["L25"].comment.text.startswith("Update: Amortization") and w["L26"].value == "=L24+L25"
    assert st2["placeholders"] == [] and st2["awaiting"] == []


def test_the_10q_never_diffs_against_a_placeholder_and_leaves_unprinted_ones_listed(tmp_path):
    """A placeholder is a forecast: '10-Q differs from the release' against it would be a false alarm. A line the
    10-Q does not print either stays a placeholder, still listed for the user."""
    text = "\n".join(x for x in mf.release_md("normal").split("\n") if not x.startswith("| Other current assets"))
    ws, rep, st, out, sp = _q3(tmp_path, text=text)
    assert ws["L15"].value == 15.5                             # forecast placeholder; the 10-Q prints 16.0
    tq = "\n".join(x for x in mf.tenq_md().split("\n") if not x.startswith("| Units"))
    w, rep2, st2 = _tenq_after(tmp_path, out, sp, tq)
    assert w["L15"].value == 16.0 and w["L15"].font.color.rgb == BLUE
    assert all(d["ref"] != "L15" for d in rep2["differences"])
    assert [p["ref"] for p in st2["placeholders"]] == [p["ref"] for p in st["placeholders"] if p["ref"] != "L15"]


def test_restating_a_quarter_reports_the_q4_plug_it_moves(tmp_path):
    """Q4 = FY less Q1-Q3: a recast Q3 25 silently changes Q4 25 unless the ask shows it."""
    ws, rep, _, _, _ = _q3(tmp_path, text=mf.release_md("recast"), restate=True)
    assert ws["F4"].value == 121.0
    hit = [k for k in rep["restate_knock_on"] if k["ref"] == "F4"]
    assert hit == [{"ref": "F4", "moves": "G4", "period": "Q4 25", "formula": "=H4-F4-E4-D4", "by": -1.0}]


def test_plan_notes_leave_the_cells_actuals_rewrites(tmp_path):
    """A 'Plan: ' note on an actual number would describe a forecast that is no longer there."""
    def plan(ws):
        ws["L4"].comment = Comment("Plan: revenue = units x price", "model-forecast")
        ws["L15"].comment = Comment("Plan: carried forward", "model-forecast")
    text = "\n".join(x for x in mf.release_md("normal").split("\n") if not x.startswith("| Other current assets"))
    ws, _, _, _, _ = _q3(tmp_path, text=text, edit=plan)
    assert ws["L4"].comment.text.startswith("Update: Revenue") and "Plan:" not in ws["L4"].comment.text
    assert ws["L15"].comment.text.startswith("Update: forecast placeholder") and "Plan:" not in ws["L15"].comment.text
    assert ws["D4"].comment.text.startswith("10-K 2025")


def test_waiting_driver_rows_say_driver_not_10q(tmp_path):
    """A driver row (units x price, a tax-rate assumption) is never in a 10-Q: the report must not promise it."""
    def driver(ws):
        ws["A28"], ws["B28"], ws["C28"], ws["L28"] = "INCOME STATEMENT DRIVERS", "Tax rate", "%", 0.2
    text = "\n".join(x for x in mf.release_md("normal").split("\n") if not x.startswith("| Other current assets"))
    _, _, st, _, _ = _q3(tmp_path, text=text, edit=driver)
    kinds = {a["ref"]: a["kind"] for a in st["awaiting"]}
    assert kinds["L28"] == "driver" and kinds["L15"] == "10-Q"


def test_analysis_rows_no_filing_prints_say_manual_and_empty_cells_stay_empty(tmp_path):
    """An annualised figure (=F11*4) holds a constant, so it is not copied; the report must say the user re-enters it
    rather than promise a 10-Q. A TTM sum over earlier quarters IS copied (it only adds numbers already there). A row
    the user left empty this quarter gets no new formula."""
    def rows(ws):
        ws["A28"], ws["B28"], ws["C28"] = "ROIC, ROE, ROA", "Annualised net income", "$m"
        ws["F28"], ws["L28"] = "=F11*4", "=L11*4"
        ws["B29"], ws["C29"], ws["F29"] = "Old revenue total", "$m", "=F4"
        ws["B30"], ws["C30"], ws["F30"], ws["L30"] = "TTM net income", "$m", "=F11+E11+D11", "=L11*3"
    _, _, st, out, _ = _q3(tmp_path, edit=rows)
    ws = openpyxl.load_workbook(out)["MOD"]
    assert {a["ref"]: a["kind"] for a in st["awaiting"]}["L28"] == "manual" and ws["L28"].value is None
    assert ws["L29"].value is None and ws["L30"].value == "=L11+K11+J11"


def test_the_report_lists_forecast_formulas_that_read_a_blank_waiting_cell(tmp_path):
    """A blank actual (no pre-print value to keep) feeds next quarter's forecast; the user must hear which cells,
    not find #DIV/0! later. A placeholder holds a number, so its readers are not listed."""
    text = "\n".join(x for x in mf.release_md("normal").split("\n") if not x.startswith("| Other current assets"))
    _, rep, _, _, _ = _q3(tmp_path, text=text)
    assert rep["waiting_read_elsewhere"] == {}
