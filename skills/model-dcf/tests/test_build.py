"""build.py writes the v2 DCF tab: placed after DCF Cheat Sheet; every input is a yellow cell with a blue font (and
nothing else is yellow); WACC and the multiple are typed, never CAPM links; nothing outside the tab moves; the
recalculated tab equals dcfmath and ties to MOD; a rerun keeps what the user typed; a v1 tab gives only its Base
customer growth; an unrecognised tab stops the run."""
import json
import os
import re

import openpyxl
import pytest

import build
import context
import dcfmath
import lo
import solve
import xlverify
from test_context import model  # noqa: F401  (the synthetic MOD / Px Data / CAPM workbook)
from xledit import set_cells
from xlsx import Package

YELLOW, BLUE = "FFFFFF99", "FF0000FF"


def _build(model, out, written=None):
    """written: the inputs_written.json of the build that made `model`'s tab (None = none). Writes out + '.json'."""
    ctx = context.build(model)
    kept, formulas, kind, _ = build.read_inputs(model, ctx, written)
    solved = solve.solve(ctx, kept, kind, as_of="2026-11-10", formulas=formulas)
    build.build(model, ctx, solved, out, out + ".json")
    return ctx, solved


@pytest.fixture
def built(model, tmp_path):  # noqa: F811
    wb = openpyxl.load_workbook(model)
    wb.create_sheet("DCF Cheat Sheet")["A1"] = "cheat"
    wb.create_sheet("After")["A1"] = "after"
    from openpyxl.workbook.defined_name import DefinedName
    wb["After"].defined_names["LocalAfter"] = DefinedName("LocalAfter", attr_text="After!$A$1")
    wb.save(model)
    out = str(tmp_path / "out.xlsx")
    ctx, solved = _build(model, out)
    return {"model": model, "out": out, "ctx": ctx, "solved": solved, "tmp": tmp_path}


def _ws(path, data_only=False):
    return openpyxl.load_workbook(path, data_only=data_only)["DCF"]


def _input_refs(ctx):
    L = build.layout(ctx)
    R, cols = L["rows"], {dcfmath.label(ctx, t): build.tcol(t) for t in range(0, 31)}
    for name, years in build.input_cells(ctx).items():
        row = R[name] if name in R else build.driver_row(ctx, R, name) if name not in ("wacc", "tv_mult") else None
        for y in years:
            yield name, y, (f"C{R['wacc' if name == 'wacc' else 'mult']}" if y is None else f"{cols[y]}{row}")


def test_tab_placed_after_cheat_sheet_and_xml_clean(built):
    pkg = Package(built["out"])
    names = [s[0] for s in pkg.sheets()]
    assert names[names.index("DCF Cheat Sheet") + 1] == "DCF" and names[-1] == "After"
    assert xlverify.bad_parts(built["out"]) == []
    m = re.search(r'<definedName\b[^>]*name="LocalAfter"[^>]*>', pkg.text("xl/workbook.xml"))
    assert m and f'localSheetId="{names.index("After")}"' in m.group(0)


def test_every_input_cell_is_yellow_with_blue_font_and_nothing_else_is_yellow(built):
    """The user's rule: they change only yellow cells, so every input must be yellow and no formula may look like one."""
    ws = _ws(built["out"])
    refs = {ref for _, _, ref in _input_refs(built["ctx"])}
    assert len(refs) == 3 * 28 + 28 + 5 * 28 + 2     # 3 drivers, dgm, 5 cost rows for 2029E-2056E; MOD years are links
    for ref in refs:
        c = ws[ref]
        assert isinstance(c.value, float), (ref, c.value)
        assert c.fill.fgColor.rgb == YELLOW and c.font.color.rgb == BLUE, ref
    for row in ws.iter_rows():
        for c in row:
            if c.coordinate not in refs and c.fill and c.fill.fgColor.rgb == YELLOW:
                pytest.fail(f"{c.coordinate} is yellow but not an input")


def test_no_capm_link_no_switch_no_scenarios(built):
    ws = _ws(built["out"])
    formulas = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    assert formulas and not any("CAPM" in f or "CHOOSE" in f for f in formulas)
    texts = " ".join(str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str))
    for gone in ("Bear", "Bull", "Disaster", "Price-implied", "PROBABILITY", "TERMINAL MULTIPLE:"):
        assert gone not in texts
    assert "<dataValidations" not in Package(built["out"]).text(
        {s[0]: s[3] for s in Package(built["out"]).sheets()}["DCF"])
    R = build.layout(built["ctx"])["rows"]
    assert ws[f"C{R['wacc']}"].value == 0.08 and ws[f"C{R['mult']}"].value == 10


def test_nothing_else_changed_and_tab_equals_dcfmath(built):
    work = built["tmp"]
    before = xlverify._grid(lo.recalc(built["model"], str(work / "rb")))
    ra = lo.recalc(built["out"], str(work / "ra"))
    after = xlverify._grid(ra)
    assert xlverify.compare(before, after, new_tabs=("DCF",)) == []
    ws = _ws(ra, data_only=True)
    R = build.layout(built["ctx"])["rows"]
    inp = built["solved"]["inputs"]
    c = dcfmath.prepare(built["ctx"], inp)
    o = dcfmath.run(dcfmath.to_scn(inp, c), c)
    assert abs(ws[f"C{R['vps']}"].value - o["value_per_share"]) < 0.01
    for t in range(1, 31):
        for n in ("rev", "oi"):
            assert ws[f"{build.tcol(t)}{R[n]}"].value == pytest.approx(o[n][t - 1], rel=1e-6)
    for t in range(1, c["k"] + 1):
        assert ws[f"{build.tcol(t)}{R['rev']}"].value == pytest.approx(c["mod"]["rev"][t - 1], rel=1e-9)
    assert ws[f"C{R['price']}"].value == built["ctx"]["price"]["last"]["value"]


def test_price_is_the_last_close_whatever_px_data_grows_to(built):
    ws = _ws(built["out"])
    R = build.layout(built["ctx"])["rows"]
    assert ws[f"C{R['price']}"].value == "=INDEX('Px Data'!$B:$B,MATCH(9.99E+307,'Px Data'!$B:$B))"
    assert ws[f"D{R['price']}"].value == "=INDEX('Px Data'!$A:$A,MATCH(9.99E+307,'Px Data'!$B:$B))"


def test_reverse_table_is_grey_italic_snapshot_with_run_date(built):
    ws = _ws(built["out"])
    L = build.layout(built["ctx"])
    assert "2026-11-10" in ws[f"B{L['rows']['rev_hdr']}"].value
    for row, pk, d in L["reverse_rows"]:
        c = ws[f"C{row}"]
        assert c.value == built["ctx"]["price"][pk]["value"] and c.font.i and c.font.color.rgb == "FF808080"


def _edit_dcf(path, out, cells):
    pkg = Package(path)
    part = {s[0]: s[3] for s in pkg.sheets()}["DCF"]
    pkg.put(part, set_cells(pkg.text(part), cells, replace=True)[0])
    pkg.save(out)


def test_mod_year_opex_and_working_capital_ratios_are_formulas_not_inputs(built):
    """They can't move anything (revenue = MOD there), so a yellow cell would mislead the user."""
    ws = _ws(built["out"])
    R = build.layout(built["ctx"])["rows"]
    for n in ("opex_inc", "wc_inc"):
        for t in (1, 2):
            c = ws[f"{build.tcol(t)}{R[n]}"]
            assert isinstance(c.value, str) and c.value.startswith("=") and c.fill.fgColor.rgb != YELLOW, (n, t)
        assert isinstance(ws[f"{build.tcol(3)}{R[n]}"].value, float)


def test_mod_years_link_every_driver_to_mod_so_nothing_is_split_only(built):
    """The forecast plan's identity names MOD rows, so 2027-2028 driver levels are links (green), their growth is a
    formula, and revenue there is the identity on those links (equal to MOD revenue)."""
    ws = _ws(built["out"])
    R = build.layout(built["ctx"])["rows"]
    for t in (1, 2):
        for j in range(3):
            lv, g = ws[f"{build.tcol(t)}{R[f'lv{j}']}"], ws[f"{build.tcol(t)}{R[f'g{j}']}"]
            assert lv.value.startswith("=MOD!") and lv.font.color.rgb == "FF008000"
            assert g.value.startswith("=IFERROR(") and g.fill.fgColor.rgb != YELLOW
    assert ws[f"{build.tcol(3)}{R['g0']}"].fill.fgColor.rgb == YELLOW
    assert "long-run 3.0%" in ws[f"{build.tcol(3)}{R['g0']}"].comment.text


def test_reverse_table_says_one_driver_shift_on_first_five_input_years(built):
    ws = _ws(built["out"])
    R = build.layout(built["ctx"])["rows"]
    assert "one driver at a time, shift on 2029e-2033e" in ws[f"B{R['rev_hdr']}"].comment.text.lower()


def test_layout_and_formatting_follow_the_users_edit(built):
    """The user reformatted the DXCM tab by hand (2026-11-10); every rerun must come out the way they left it, or they redo
    it each time."""
    ws = _ws(built["out"])
    R = build.layout(built["ctx"])["rows"]
    usd = '"$"#,##0.0_);\\("$"#,##0.0\\);"-"_)'
    assert ws["B1"].value.endswith("30 yr DCF") and ws["B1"].font.b and ws.row_dimensions[1].height == 24
    assert ws.column_dimensions["B"].width == 39.5 and ws.sheet_view.zoomScale == 115
    assert ws.row_dimensions[R["rev_hdr"]].height == 68
    # terminal value sits in the valuation block and PV of TV discounts it 30 years at the WACC
    assert ws[f"B{R['tv']}"].value == "Terminal Value"
    assert ws[f"C{R['tv']}"].value == f"=AL{R['ufcf']}*C{R['mult']}"
    assert ws[f"C{R['pv_tv']}"].value == f"=C{R['tv']}/(1+C{R['wacc']})^AL{R['period']}"
    assert ws[f"B{R['equity']}"].value == "Equity value (MCAP)" and ws[f"C{R['equity']}"].font.b
    # PV of FCF discounts directly (no discount-factor row), bold, boxed from year 0 to year 30
    assert ws[f"I{R['pv']}"].value == f"=I{R['ufcf']}/(1+$C${R['wacc']})^I{R['period']}"
    assert ws[f"I{R['pv']}"].font.b and ws[f"I{R['pv']}"].border.top.style == "thin"
    assert ws[f"H{R['pv']}"].border.left.style == "thin" and ws[f"AL{R['pv']}"].border.right.style == "thin"
    assert ws[f"AM{R['pv']}"].value is None
    # spacer rows between line groups
    for a, b in (("g0", "lv1"), ("g1", "lv2"), ("g2", "rev"), ("rev_yoy", "gm"), ("dgm", "gross"), ("opex_inc", "oi"),
                 ("tax", "nopat"), ("wc_inc", "ufcf"), ("ufcf_margin", "pv")):
        assert R[b] == R[a] + 2 and ws[f"B{R[a] + 1}"].value is None, (a, b)
    # $ on money lines; customers one decimal without $ (house default)
    for n in ("rev", "gross", "opex", "oi", "nopat", "da", "capex", "wc", "ufcf", "pv"):
        assert ws[f"J{R[n]}"].number_format == usd, n
    assert "$" not in ws[f"J{R['lv0']}"].number_format and ".0" in ws[f"J{R['lv0']}"].number_format  # no unit, no $
    for n in ("lv0", "lv1", "gm", "nopat"):
        assert ws[f"B{R[n]}"].font.b, n
    for n in ("g0", "g1", "da_pct", "capex_pct", "wc_inc", "ufcf_margin"):
        assert ws[f"B{R[n]}"].font.i and ws[f"J{R[n]}"].font.i, n
    for n in ("g0", "da", "capex", "wc"):
        assert ws[f"B{R[n]}"].alignment.indent == 1, n
    assert ws[f"B{R['ufcf']}"].value == "UNLEVERED FCF"
    assert ws[f"B{R['lv0']}"].value == "Units" and ws[f"B{R['g0']}"].value == "Units growth, % yoy"


def test_build_records_only_the_defaults_it_wrote(built, tmp_path):
    """Cells holding the user's values are left out, so the next rerun still sees them as theirs."""
    R = build.layout(built["ctx"])["rows"]
    edited = str(tmp_path / "e.xlsx")
    _edit_dcf(built["out"], edited, {f"{build.tcol(3)}{R['g0']}": ("n", 0.077, 0)})
    out2 = str(tmp_path / "e2.xlsx")
    _build(edited, out2, built["out"] + ".json")
    w2 = json.load(open(out2 + ".json"))
    assert "2029E" not in w2["Units"] and "2030E" in w2["Units"]
    kept, _, _, _ = build.read_inputs(out2, built["ctx"], out2 + ".json")
    assert kept == {"Units": {"2029E": 0.077}}


def test_build_saves_what_it_wrote_in_every_input_cell(built):
    w = json.load(open(built["out"] + ".json"))
    refs = list(_input_refs(built["ctx"]))
    assert sum(1 if y is None else 0 for _, y, _ in refs) == 2
    for name, y, _ in refs:
        assert (w[name] if y is None else w[name][y]) == (built["solved"]["inputs"][name] if y is None
                                                         else built["solved"]["inputs"][name][y])


def test_rerun_keeps_what_the_user_typed_and_refreshes_the_rest(built):
    """The user owns the inputs: a cell that differs from what the last build wrote is theirs; a cell still equal to what the
    build wrote takes a fresh default (so MOD changes flow through)."""
    R = build.layout(built["ctx"])["rows"]
    edited = str(built["tmp"] / "edited.xlsx")
    cells = {f"{build.tcol(3)}{R['g0']}": ("n", 0.077, 0), f"{build.tcol(10)}{R['dgm']}": ("n", 15.0, 0),
             f"C{R['wacc']}": ("n", 0.095, 0), f"{build.tcol(20)}{R['tax']}": ("n", 0.5, 0)}
    _edit_dcf(built["out"], edited, cells)
    w = json.load(open(built["out"] + ".json"))
    w["tax"]["2046E"] = 0.5                     # as if the last build had written 0.5 (an old default)
    wpath = str(built["tmp"] / "w.json")
    json.dump(w, open(wpath, "w"))
    out2 = str(built["tmp"] / "out2.xlsx")
    ctx, solved = _build(edited, out2, wpath)
    inp, first = solved["inputs"], built["solved"]["inputs"]
    assert solved["kept_from"] == "existing"
    assert inp["Units"]["2029E"] == 0.077 and inp["dgm"]["2036E"] == 15.0 and inp["wacc"] == 0.095
    assert inp["tax"]["2046E"] == pytest.approx(first["tax"]["2045E"])   # equal to what was written: fresh default
    assert solved["kept"] == {"Units": ["2029E"], "dgm": ["2036E"], "wacc": ["value"]}
    ws = _ws(out2)
    assert ws[f"{build.tcol(3)}{R['g0']}"].value == 0.077 and ws[f"C{R['wacc']}"].value == 0.095
    assert [s[0] for s in Package(out2).sheets()].count("DCF") == 1 and xlverify.bad_parts(out2) == []


def test_rerun_keeps_a_formula_the_user_typed_as_a_formula(built, monkeypatch):
    import tempfile
    scratch = built["tmp"] / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))    # the formula's value needs a recalculated copy
    R = build.layout(built["ctx"])["rows"]
    c40, c39 = f"{build.tcol(14)}{R['g0']}", f"{build.tcol(13)}{R['g0']}"
    edited = str(built["tmp"] / "f.xlsx")
    _edit_dcf(built["out"], edited, {c40: ("f", f"{c39}/2", 0)})
    out2 = str(built["tmp"] / "f2.xlsx")
    ctx, solved = _build(edited, out2, built["out"] + ".json")
    assert solved["formulas"] == {"Units": {"2040E": f"{c39}/2"}}
    assert solved["inputs"]["Units"]["2040E"] == pytest.approx(built["solved"]["inputs"]["Units"]["2039E"] / 2)
    assert "Units" in solved["kept"] and "2040E" in solved["kept"]["Units"]
    c = _ws(out2)[c40]
    assert c.value == f"={c39}/2" and c.fill.fgColor.rgb == YELLOW
    assert "2040E" not in json.load(open(out2 + ".json"))["Units"]       # a formula is always the user's
    assert list(scratch.iterdir()) == []      # that recalculated copy of the user's model is not kept


def test_rerun_defaults_a_cleared_cell(built):
    R = build.layout(built["ctx"])["rows"]
    edited = str(built["tmp"] / "cleared.xlsx")
    _edit_dcf(built["out"], edited, {f"{build.tcol(20)}{R['tax']}": ("s", "", 0)})
    ctx = context.build(edited)
    kept, formulas, kind, _ = build.read_inputs(edited, ctx)          # no written file: every number counts as the user's
    s = solve.solve(ctx, kept, kind, formulas=formulas)
    assert s["defaulted"] == {"tax": ["2046E"]}


def test_a_tab_without_a_year_header_stops_with_a_plain_message(built):
    R = build.layout(built["ctx"])["rows"]
    edited = str(built["tmp"] / "odd.xlsx")
    _edit_dcf(built["out"], edited, {f"B{R['years']}": ("s", "my own row", 0)})
    with pytest.raises(SystemExit, match="does not recognise"):
        build.read_inputs(edited, built["ctx"], built["out"] + ".json")


def test_when_the_drivers_change_shared_inputs_carry_and_old_driver_rows_are_reported(built):
    """A tab built for other drivers (e.g. before the forecast's identity changed) still gives up the inputs it shares
    (gross margin, costs, WACC); a growth row with no home is reported with the years the user typed, never dropped
    silently."""
    R = build.layout(built["ctx"])["rows"]
    edited = str(built["tmp"] / "old.xlsx")
    _edit_dcf(built["out"], edited, {f"B{R['g0']}": ("s", "Customers growth, % yoy", 0),
                                      f"{build.tcol(5)}{R['g0']}": ("n", 0.2, 0),
                                      f"{build.tcol(5)}{R['dgm']}": ("n", 12.0, 0)})
    w = json.load(open(built["out"] + ".json"))
    w["Customers"] = w.pop("Units")              # the old build recorded that row's defaults under its own name
    wpath = str(built["tmp"] / "old_w.json")
    json.dump(w, open(wpath, "w"))
    kept, _, _, orphans = build.read_inputs(edited, built["ctx"], wpath)
    assert kept == {"dgm": {"2031E": 12.0}}
    assert orphans == [{"row_label": "Customers growth, % yoy", "typed_years": ["2031E"]}]


def test_no_existing_tab_means_all_defaults(built):
    assert build.read_inputs(built["model"], built["ctx"]) == ({}, {}, None, [])
    assert built["solved"]["kept"] == {}


def test_reverse_table_names_each_driver_in_the_wide_label_column(built):
    """Driver names come from the company's identity and can be long; the narrow columns would cut them off."""
    ws = _ws(built["out"])
    L = build.layout(built["ctx"])
    R = L["rows"]
    assert ws[f"B{R['price_last']}"].value.startswith("Last close (") and ws[f"B{R['price_last']}"].font.b
    names = [ws[f"B{row}"].value for row, pk, _ in L["reverse_rows"] if pk == "last"]
    assert names == ["Units", "Price", "Other revenue", "Gross margin"]
    assert {ws[f"D{row}"].value for row, _, _ in L["reverse_rows"]} == {"% pts / yr", "bps / yr"}


def test_a_snapshot_number_with_no_value_is_left_blank_not_written_as_nan(built):
    """A reverse-DCF figure with no meaning (e.g. the CAGR of a driver that is 0) must not reach the sheet as 'nan':
    that is not a number to Excel and the file no longer opens cleanly."""
    solved = json.loads(json.dumps(built["solved"]))
    row, pk, d = next(r for r in build.layout(built["ctx"])["reverse_rows"] if r[2] != "dgm"
                      and solved["reverse"][r[1]][r[2]].get("status") == "ok")
    solved["reverse"][pk][d]["driver_cagr5"] = float("nan")
    out = str(built["tmp"] / "nan.xlsx")
    build.build(built["model"], built["ctx"], solved, out, out + ".json")
    assert _ws(out)[f"F{row}"].value is None


def test_year_columns_widen_only_when_a_number_would_print_as_hashes():
    """ABT 2026-11: 2043E-2056E revenue passed $100,000M and the terminal value ~$480,000M; at the user's width 11
    they printed '###'. The user's width (11) stays whenever the tab's largest number fits (DXCM), and the year
    columns widen just enough when it doesn't."""
    assert build.year_col_width([5_000.0, 61_234.5, 98_765.4]) == 11              # DXCM-sized: the user's layout
    w = build.year_col_width([107_242.2, 480_380.4, -2_000.0])
    assert w > 11 and w >= len("$480,380.4 ") + 1                                  # "$480,380.4" plus its ")" pad
    assert build.year_col_width([-480_380.4]) >= len("($480,380.4)") + 1
