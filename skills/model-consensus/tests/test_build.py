import json
import re
import os
import shutil

import openpyxl
import pytest

import build
from conftest import REFERENCE, snap, snap_path
from xlsx import Package


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    w = tmp_path_factory.mktemp("w")
    os.makedirs(w / "snapshots")
    shutil.copy(snap_path("DXCM"), w / "snapshots")
    out = str(w / "built.xlsx")
    summary = build.build(REFERENCE, str(w), "DXCM", out)
    return w, out, summary


def find(ws, prefix, col=1):
    return next(r for r in range(1, ws.max_row + 1) if str(ws.cell(r, col).value or "").startswith(prefix))


def test_only_the_new_tab_is_added_and_every_other_part_is_byte_identical(built):
    w, out, _ = built
    before, after = Package(REFERENCE), Package(out)
    allowed = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml",
               "xl/calcChain.xml", "docProps/app.xml"}
    changed = [p for p in before.parts if p not in allowed and before.parts[p] != after.parts.get(p)]
    assert changed == []
    assert [s[0] for s in after.sheets()][-1] == "Consensus"


def test_blocks_are_in_the_house_order(built):
    _, out, _ = built
    ws = openpyxl.load_workbook(out, read_only=True)["Consensus"]
    bands = [r[0] for r in ws.iter_rows(max_col=1, values_only=True)
             if isinstance(r[0], str) and r[0][:2] in ("1.", "2.", "3.", "4.", "5.")]
    assert [b[:2] for b in bands] == ["1.", "2.", "3.", "4.", "5."]


def test_layout_has_expected_values_and_every_typed_number_has_a_note(built):
    w, out, summary = built
    import verify
    L = json.load(open(w / "layout.json"))
    assert len(L["expected"]) > 50
    assert verify.scan(out, L) == {"no_note": [], "colour": []}
    assert summary["analysts"] >= 5 and summary["chart"] is True


def test_variance_skeleton_is_empty_inputs_with_formulas(built):
    _, out, _ = built
    ws = openpyxl.load_workbook(out)["Consensus"]
    band = find(ws, "2. VARIANCE")
    assert ws.cell(band + 2, 2).value == "Revenue"
    assert all(ws.cell(band + 2, c).value is None for c in range(3, 9))        # no data, no links
    assert ws.cell(band + 2, 9).value.startswith("=IF(OR(")
    assert "10000" in ws.cell(band + 4, 9).value                                # gross margin row: bps


def test_rerun_keeps_the_users_variance_entries(built, tmp_path):
    w, out, _ = built
    wb = openpyxl.load_workbook(out)
    ws = wb["Consensus"]
    band = find(ws, "2. VARIANCE")
    ws.cell(band + 2, 3).value = 5800
    ws.cell(band + 2, 6).value = 5600
    ws.cell(band + 11, 2).value = "My extra KPI"
    ws.cell(band + 11, 6).value = f"=F{band + 2}*2"
    edited = str(tmp_path / "edited.xlsx")
    wb.save(edited)                                                             # a test copy, never the user's file
    out2 = str(tmp_path / "built2.xlsx")
    s = build.build(edited, str(w), "DXCM", out2)
    ws2 = openpyxl.load_workbook(out2)["Consensus"]
    b2 = find(ws2, "2. VARIANCE")
    assert ws2.cell(b2 + 2, 3).value == 5800 and ws2.cell(b2 + 2, 6).value == 5600
    assert ws2.cell(b2 + 11, 2).value == "My extra KPI"
    assert ws2.cell(b2 + 11, 6).value == f"=F{b2 + 2}*2"
    assert ws2.cell(b2 + 11, 9).value.startswith("=IF(OR(")
    assert s["variance_carried_over"] is True
    L = json.load(open(w / "layout.json"))
    assert L["preserved"][f"C{b2 + 2}"] == ["n", 5800]


def test_shift_formula_moves_only_same_sheet_refs_inside_the_block():
    f = build.shift_formula("F12*2+MOD!C12+'Px Data'!$B$12+LOG10(C13)+C40", 3, 10, 20)
    assert f == "F15*2+MOD!C12+'Px Data'!$B$12+LOG10(C16)+C40"


def test_shift_formula_leaves_other_sheet_ranges_and_text_alone():
    # the end of a range on another tab (MOD!C12:F12) is not a ref to this tab; neither is text in quotes
    f = build.shift_formula('SUM(MOD!C12:F12)+SUM(C12:D13)+COUNTIF(B12,"C12")', 3, 10, 20)
    assert f == 'SUM(MOD!C12:F12)+SUM(C15:D16)+COUNTIF(B15,"C12")'


def test_carried_formula_pointing_outside_the_block_is_flagged():
    assert build.outside_refs("F12*2+J9+MOD!J9", 10, 20) == ["J9"]


def test_wrong_close_header_is_flagged_not_silently_used(tmp_path):
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    shutil.copy(snap_path("SENS"), w / "snapshots")
    s = build.build(REFERENCE, str(w), "SENS", str(tmp_path / "b.xlsx"))   # Px Data holds DXCM closes
    assert any("'SENS close'" in x for x in s["warnings"])


def test_no_px_data_skips_the_chart_and_says_so(tmp_path):
    pkg = Package(REFERENCE)
    pkg.remove_sheet("Px Data")
    m = str(tmp_path / "nopx.xlsx")
    pkg.save(m)                                                            # a test copy without Px Data
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    shutil.copy(snap_path("DXCM"), w / "snapshots")
    s = build.build(m, str(w), "DXCM", str(tmp_path / "b.xlsx"))
    assert s["chart"] is False and any("No Px Data" in x for x in s["warnings"])


# ---- addendum 1: brokers Nasdaq lists as covering but with no Yahoo action in 12 months still get a row
def test_nasdaq_only_brokers_get_blank_rating_rows_with_a_note(built):
    w, out, summary = built
    wb = openpyxl.load_workbook(out)
    ws = wb["Consensus"]
    band = find(ws, "2. VARIANCE")
    firms = {ws.cell(r, 2).value: r for r in range(8, band) if isinstance(ws.cell(r, 1).value, int)}
    # Baird's last Yahoo action is more than 12 months old, but Nasdaq (Zacks) lists it as covering
    r = firms["Baird"]
    assert ws.cell(r, 3).value == "Independent"
    assert all(ws.cell(r, c).value is None for c in range(4, 10))          # rating, bucket, PT, upside, action blank
    notes = {c.coordinate: c.comment.text for row in ws.iter_rows() for c in row if c.comment}
    assert "Listed as covering by Nasdaq (Zacks)" in notes[f"B{r}"]
    assert summary["nasdaq_only"] == 7
    # not reported as "may have dropped coverage": Nasdaq says it still covers
    assert "Baird" not in summary["dropped"] and "Goldman Sachs" in summary["dropped"]
    assert "Baird (" not in ws["A4"].value
    # rows sort by PT with the blank-PT rows last, so the reader sees the rated brokers first
    pts = [ws.cell(rr, 6).value for rr in sorted(firms.values())]
    rated = [p for p in pts if p is not None]
    assert pts[:len(rated)] == sorted(rated, reverse=True) and all(p is None for p in pts[len(rated):])
    # counts and average ignore them: Buy + Hold + Sell = brokers with a Yahoo rating
    assert summary["analysts"] == len(firms) - 7


# ---- addendum 2: "Unrated" bucket shows, stays out of Buy/Hold/Sell, gets its own count row only when present
def test_unrated_bucket_shows_and_gets_its_own_count_row(built, tmp_path):
    _, out, _ = built
    ws = openpyxl.load_workbook(out, read_only=True)["Consensus"]
    assert not any(r[0] == "Ratings: Unrated" for r in ws.iter_rows(min_col=2, max_col=2, values_only=True))
    s = snap("DXCM")
    newest = max((h for h in s["yahoo"]["history"] if h["firm"] == "UBS"), key=lambda h: h["epochGradeDate"])
    newest["toGrade"] = "Suspended"
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    json.dump(s, open(w / "snapshots" / f"{s['asof']}.json", "w"))
    o = str(tmp_path / "b.xlsx")
    build.build(REFERENCE, str(w), "DXCM", o)
    ws = openpyxl.load_workbook(o)["Consensus"]
    r = next(r for r in range(8, 60) if ws.cell(r, 2).value == "UBS")
    assert ws.cell(r, 5).value == "Unrated"
    u = find(ws, "Ratings: Unrated", col=2)
    assert ws.cell(u - 1, 2).value == "Ratings: Sell"
    assert '"Unrated"' in ws.cell(u, 5).value


# ---- addendum 3
def test_other_type_has_a_label():
    assert build.TYPE_LABEL["other"] == "Other"


# ---- addendum 5: the average-target helper column leaves real gaps (Excel joins a line across #N/A)
def test_average_target_column_never_holds_na(built):
    _, out, _ = built
    ws = openpyxl.load_workbook(out)["Consensus"]
    h0 = find(ws, "Date", col=18)
    vals = [ws.cell(r, 20).value for r in range(h0 + 1, ws.max_row + 1)]
    assert all(v is None or isinstance(v, (int, float)) for v in vals)
    assert any(isinstance(ws.cell(r, 21).value, str) and "NA()" in ws.cell(r, 21).value for r in range(h0 + 1, h0 + 5))


# ---- addendum 6: a period end that isn't a quarter end becomes a warning, not a crash
def test_bad_period_end_is_a_warning_not_a_crash(tmp_path):
    s = snap("DXCM")
    for t in s["yahoo"]["trend"]:
        if t["period"] == "0q":
            t["endDate"] = "2026-11-15T00:00:00.000Z"                      # mid-quarter for a December year-end
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    json.dump(s, open(w / "snapshots" / f"{s['asof']}.json", "w"))
    o = str(tmp_path / "b.xlsx")
    summary = build.build(REFERENCE, str(w), "DXCM", o)
    assert any("not a quarter end" in x for x in summary["warnings"])
    assert summary["labels"] == {"q": None, "fy": None, "fy1": None}
    ws = openpyxl.load_workbook(o)["Consensus"]
    mean = find(ws, "Consensus mean", col=2)
    assert all(ws.cell(mean, c).value is None for c in range(10, 16))      # consensus estimates blank
    assert isinstance(ws.cell(mean, 6).value, (int, float))                # the target consensus doesn't need periods


# ---- review 8 fixes ------------------------------------------------------------------------------------------------
from openpyxl.worksheet.formula import ArrayFormula  # noqa: E402


def rebuild(src, w, tmp_path, name="re.xlsx"):
    out = str(tmp_path / name)
    return out, build.build(src, str(w), "DXCM", out)


def edit_copy(src, tmp_path, fn, name="edited.xlsx"):
    """openpyxl-edit a test copy of a built workbook (never the user's file); fn(ws, variance band row)."""
    wb = openpyxl.load_workbook(src)
    ws = wb[build.TAB]
    fn(ws, find(ws, "2. VARIANCE"))
    p = str(tmp_path / name)
    wb.save(p)
    return p


def raw_copy(src, tmp_path, fn, name="raw.xlsx"):
    """Raw-XML edit of a test copy: fn(Package)."""
    pkg = Package(src)
    fn(pkg)
    p = str(tmp_path / name)
    pkg.save(p)
    return p


# 1. a "%" / bps row is decided by whole words: "Integrated CGM units" is not a rate, "Corporate costs" not a margin
def test_is_bps_matches_whole_words_only():
    for lab in ("Integrated CGM units", "Corporate costs", "Revenue", "Operators", "Margined units"):
        assert not build.is_bps(lab), lab
    for lab in ("Gross margin", "Revenue growth", "Tax rate", "% of sales", "Margins", "Growth rates", "OPERATING MARGIN"):
        assert build.is_bps(lab), lab


# 2. The user typed over a generated variance cell: their cell wins and the summary names it
def test_rerun_keeps_the_users_own_variance_cells_and_regenerates_untouched_ones(built, tmp_path):
    w, out, _ = built

    def ed(ws, vb):
        ws.cell(vb + 2, 9).value = 0.05                                   # typed a number over I
        ws.cell(vb + 3, 10).value = f"=F{vb + 3}-D{vb + 3}"                # their own formula in J
        r = vb + 4                                                        # old-style bps formula (pre-IFERROR build)
        ws.cell(r, 11).value = f'=IF(OR(E{r}="",H{r}=""),"",(H{r}-E{r})*10000)'
    out2, s = rebuild(edit_copy(out, tmp_path, ed), w, tmp_path)
    ws = openpyxl.load_workbook(out2)[build.TAB]
    vb = find(ws, "2. VARIANCE")
    assert ws.cell(vb + 2, 9).value == 0.05
    assert ws.cell(vb + 3, 10).value == f"=F{vb + 3}-D{vb + 3}"
    r = vb + 4
    assert ws.cell(r, 11).value == f'=IF(OR(E{r}="",H{r}=""),"",IFERROR((H{r}-E{r})*10000,""))'   # regenerated
    assert ws.cell(vb + 2, 10).value.startswith("=IF(OR(")                                         # untouched: regenerated
    named = " ".join(s["warnings"])
    assert f"{build.TAB}!I{vb + 2}" in named and f"{build.TAB}!J{vb + 3}" in named
    assert f"{build.TAB}!K{r}" not in named
    L = json.load(open(w / "layout.json"))
    assert L["preserved"][f"I{vb + 2}"] == ["n", 0.05]
    assert L["preserved"][f"J{vb + 3}"] == ["f", f"F{vb + 3}-D{vb + 3}"]
    assert f"I{vb + 2}" not in L["expected"] and f"J{vb + 3}" not in L["expected"]


# 3. a bps row survives text in its inputs (IFERROR), and the expected value agrees
def test_bps_variance_formula_has_iferror_and_expected_is_consistent(built, tmp_path):
    w, out, _ = built

    def ed(ws, vb):
        ws.cell(vb + 4, 3).value = 0.6; ws.cell(vb + 4, 6).value = 0.62    # gross margin: numbers
        ws.cell(vb + 5, 3).value = 0.3; ws.cell(vb + 5, 6).value = "tbd"   # operating margin: text
    out2, _ = rebuild(edit_copy(out, tmp_path, ed), w, tmp_path)
    ws = openpyxl.load_workbook(out2)[build.TAB]
    vb = find(ws, "2. VARIANCE")
    r = vb + 4
    assert ws.cell(r, 9).value == f'=IF(OR(C{r}="",F{r}=""),"",IFERROR((F{r}-C{r})*10000,""))'
    L = json.load(open(w / "layout.json"))
    assert abs(L["expected"][f"I{r}"] - 200) < 1e-6
    assert L["expected"][f"I{r + 1}"] is None                             # text input: IFERROR gives ""


def _mini(tmp_path, cells, name="mini.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = build.TAB
    for ref, v in cells.items():
        ws[ref] = v
    p = str(tmp_path / name)
    wb.save(p)                                                            # a synthetic test workbook
    return p


# 4. the variance block ends at any later band (not just "3. "), else at 3 empty rows, with a warning
def test_read_variance_stops_at_any_later_band(tmp_path):
    p = _mini(tmp_path, {"A1": "2. VARIANCE TABLE", "B3": "Revenue", "C3": 5, "I3": 0.1,
                         "A6": "4. RATING HISTORY LOG", "B8": "not the user's"})
    v = build.read_variance(p)
    assert v["end"] == 6 and (7, 2) not in v["cells"] and v["warnings"] == []
    assert v["cells"][(2, 2)] == "Revenue" and v["ik"][(2, 9)] == 0.1


def test_read_variance_without_an_end_band_stops_at_three_empty_rows_and_warns(tmp_path):
    p = _mini(tmp_path, {"A1": "2. VARIANCE TABLE", "B3": "Revenue", "B5": "EPS", "B9": "far below"})
    v = build.read_variance(p)
    assert v["end"] == 6 and (8, 2) not in v["cells"] and (4, 2) in v["cells"]
    assert v["warnings"] and "end" in v["warnings"][0].lower()


# 5. the "another tab points at Consensus" guard: tight on sheet names, wide on where it looks
def test_guard_ignores_a_tab_merely_ending_in_consensus(built, tmp_path):
    w, out, _ = built

    def ed(pkg):
        x = pkg.text("xl/worksheets/sheet1.xml")
        pkg.put("xl/worksheets/sheet1.xml", re.sub(r"<f>[^<]*</f>", "<f>'Old Consensus'!A1+1</f>", x, count=1))
    p = raw_copy(out, tmp_path, ed)
    assert build.consensus_refs(Package(p)) == []
    rebuild(p, w, tmp_path)                                               # no exit 3


def test_guard_catches_a_defined_name_and_another_tabs_chart(built, tmp_path):
    w, out, _ = built

    def name(pkg):
        x = pkg.text("xl/workbook.xml")
        pkg.put("xl/workbook.xml", x.replace("</sheets>", '</sheets><definedNames><definedName name="user">'
                                                         "Consensus!$A$1</definedName></definedNames>", 1))
    p = raw_copy(out, tmp_path, name)
    assert build.consensus_refs(Package(p))
    with pytest.raises(SystemExit) as e:
        rebuild(p, w, tmp_path)
    assert e.value.code == 3

    def chart(pkg):
        x = pkg.text("xl/charts/chart1.xml")                              # a chart on another tab
        pkg.put("xl/charts/chart1.xml", re.sub(r"<c:f>[^<]*</c:f>", "<c:f>Consensus!$S$8:$S$20</c:f>", x, count=1))
    p2 = raw_copy(out, tmp_path, chart, "raw2.xlsx")
    assert any("chart1" in x for x in build.consensus_refs(Package(p2)))


def test_guard_skips_the_consensus_tabs_own_chart(built):
    _, out, _ = built
    assert build.consensus_refs(Package(out)) == []


# 6. an array formula the user typed is carried over as an array formula, not as text
def test_rerun_carries_an_array_formula(built, tmp_path):
    w, out, _ = built

    def ed(ws, vb):
        ws.cell(vb + 7, 6).value = ArrayFormula(f"F{vb + 7}", f"=SUM(C{vb + 2}:C{vb + 3}*2)")
    out2, _ = rebuild(edit_copy(out, tmp_path, ed), w, tmp_path)
    ws = openpyxl.load_workbook(out2)[build.TAB]
    vb = find(ws, "2. VARIANCE")
    v = ws.cell(vb + 7, 6).value
    assert isinstance(v, ArrayFormula) and v.text == f"=SUM(C{vb + 2}:C{vb + 3}*2)"
    L = json.load(open(w / "layout.json"))
    assert L["preserved"][f"F{vb + 7}"] == ["fa", f"SUM(C{vb + 2}:C{vb + 3}*2)"]


# 7. the VML shape-id scan reads o:idmap whatever the attribute order
def test_vml_id_scan_ignores_attribute_order():
    pkg = Package(REFERENCE)
    pkg.put("xl/drawings/vmlDrawing99.vml", '<xml><o:shapelayout v:ext="edit"><o:idmap data="40, 41" v:ext="edit"/>'
                                            "</o:shapelayout></xml>")
    assert build.next_vml_id(pkg) == 42


# 8. a rerun puts the tab back where the user moved it
def test_rerun_keeps_the_tabs_position_and_active_tab(built, tmp_path):
    w, out, _ = built

    def move(pkg):
        x = pkg.text("xl/workbook.xml")
        tag = re.search(r'<sheet name="Consensus"[^>]*/>', x).group(0)
        x = x.replace(tag, "")
        tags = re.findall(r"<sheet\b[^>]*/>", x)
        x = x.replace(tags[2], tag + tags[2])
        x = re.sub(r'activeTab="\d+"', 'activeTab="2"', x)
        x = x.replace("<bookViews><workbookView ", '<bookViews><workbookView firstSheet="1" ')
        x = x.replace("</sheets>", '</sheets><definedNames><definedName name="pa" localSheetId="5">'
                                   "'Px Events'!$A$1</definedName></definedNames>", 1)
        pkg.put("xl/workbook.xml", x)
    moved = raw_copy(out, tmp_path, move)
    before = Package(moved)
    names_before = [s[0] for s in before.sheets()]
    assert names_before.index("Consensus") == 2
    out2, _ = rebuild(moved, w, tmp_path)
    after = Package(out2)
    assert [s[0] for s in after.sheets()] == names_before
    wbx = after.text("xl/workbook.xml")
    assert 'activeTab="2"' in wbx and 'firstSheet="1"' in wbx and 'localSheetId="5"' in wbx
    wb = openpyxl.load_workbook(out2)
    assert wb.sheetnames == names_before and wb.active.title == "Consensus"
    import verify
    allowed = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml",
               "xl/calcChain.xml", "docProps/app.xml"} | verify.tab_parts(before)
    changed = [p for p in before.parts if p not in allowed and before.parts[p] != after.parts.get(p)]
    assert changed == []


def test_rerun_keeps_consensus_active_when_it_is_the_last_tab(built, tmp_path):
    w, out, _ = built
    n = len(Package(out).sheets())

    def act(pkg):
        pkg.put("xl/workbook.xml", re.sub(r'activeTab="\d+"', f'activeTab="{n - 1}"', pkg.text("xl/workbook.xml")))
    out2, _ = rebuild(raw_copy(out, tmp_path, act), w, tmp_path)
    assert f'activeTab="{n - 1}"' in Package(out2).text("xl/workbook.xml")
    assert openpyxl.load_workbook(out2, read_only=True).active.title == "Consensus"


# ---- final review -------------------------------------------------------------------------------------------------
from datetime import date, timedelta  # noqa: E402

import firms as FM  # noqa: E402
import ratings  # noqa: E402


def _w(tmp_path, *snaps_, est=None):
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    for s in snaps_:
        json.dump(s, open(w / "snapshots" / f"{s['asof']}.json", "w"))
    if est is not None:
        json.dump(est, open(w / "estimates.json", "w"))
    return w


def notes_of(ws):
    return {c.coordinate: c.comment.text for row in ws.iter_rows() for c in row if c.comment}


# 2. a reporter in another currency: headers say so, P/E is not computed across currencies
def test_foreign_reporting_currency_labels_columns_and_blanks_cross_currency_pe(tmp_path):
    s = snap("DXCM")
    s["yahoo"]["financial"]["financialCurrency"] = "EUR"                   # price stays USD (an ADR)
    w = _w(tmp_path, s)
    o = str(tmp_path / "b.xlsx")
    summary = build.build(REFERENCE, str(w), "DXCM", o)
    ws = openpyxl.load_workbook(o)["Consensus"]
    heads = [ws.cell(7, c).value for c in range(13, 16)]
    assert heads == ["Rev Q4 26 (EUR M)", "Rev FY 26 (EUR M)", "Rev FY 27 (EUR M)"]
    vb = find(ws, "2. VARIANCE")
    assert ws.cell(vb + 1, 2).value.startswith("(EUR M")
    assert ws["E3"].value == "Price:" and "EUR" in ws["G3"].value and "USD" in ws["G3"].value
    assert any("EUR" in x and "USD" in x for x in summary["warnings"])
    nts = notes_of(ws)
    L = json.load(open(w / "layout.json"))
    for lab in ("P/E on Street high EPS", "P/E on Street low EPS", "P/E on consensus EPS"):
        r = find(ws, lab, col=2)
        assert ws.cell(r, 12).value is None                               # no P/E: price USD, EPS EUR
        assert f"L{r}" not in L["expected"]
        assert "price and EPS in different currencies" in nts[f"B{r}"]
    import verify
    assert verify.scan(o, L) == {"no_note": [], "colour": []}


def test_usd_reporter_keeps_dollar_headers_and_pe(built):
    _, out, summary = built
    ws = openpyxl.load_workbook(out)["Consensus"]
    assert ws.cell(7, 13).value == "Rev Q4 26 ($M)"
    r = find(ws, "P/E on consensus EPS", col=2)
    assert ws.cell(r, 12).value.startswith("=IF(")
    assert not any("currenc" in x for x in summary["warnings"])


# 4. staleness is decided at build time from this snapshot, whatever estimates.json says
def test_stale_flag_is_recomputed_at_build_time(tmp_path):
    s = snap("DXCM")
    asof = date.fromisoformat(s["asof"])
    rows, _ = ratings.latest_by_firm(ratings.actions(s, FM.Firms()), asof)
    firm_old, firm_new = sorted(r["firm"] for r in ratings.split_types(rows)[0])[:2]

    def fe(d, stale):
        f = f"/x/{d.isoformat()} Firm earnings recap - a.md"
        return {"date": d.isoformat(), "file": f, "stale": stale, "values": {"eps": {"FY 27": {
            "metric": "eps", "period": "FY 27", "value": 3.2, "raw": "3.20", "file": f, "line_no": 3,
            "report_date": d.isoformat()}}}}
    est = {firm_old: fe(asof - timedelta(days=120), False),               # says fresh, is 120 days old
           firm_new: fe(asof, True)}                                      # says stale, is today's report
    w = _w(tmp_path, s, est=est)
    o = str(tmp_path / "b.xlsx")
    summary = build.build(REFERENCE, str(w), "DXCM", o)
    assert summary["stale"] == [firm_old]
    ws = openpyxl.load_workbook(o)["Consensus"]
    row = {ws.cell(r, 2).value: r for r in range(8, 60)}
    old, new = ws.cell(row[firm_old], 12), ws.cell(row[firm_new], 12)
    assert old.font.color.rgb == build.GREY and old.font.i
    assert new.font.color.rgb == build.BLUE
    assert ws.cell(row[firm_old], 16).value.endswith("(stale)")
    assert not ws.cell(row[firm_new], 16).value.endswith("(stale)")
    import verify
    assert verify.scan(o, json.load(open(w / "layout.json"))) == {"no_note": [], "colour": []}


# 9. the summary's changes include price-target moves since the last snapshot
def test_changes_list_target_moves_since_the_previous_snapshot(tmp_path):
    cur = snap("DXCM")
    acts = ratings.actions(cur, FM.Firms())
    tc = max(a["date"] for a in acts if a["kind"] == "Target change")
    prev = json.loads(json.dumps(cur))
    prev["asof"] = (tc - timedelta(days=1)).isoformat()
    w = _w(tmp_path, prev, cur)
    summary = build.build(REFERENCE, str(w), "DXCM", str(tmp_path / "b.xlsx"))
    moved = [a for a in acts if a["kind"] == "Target change" and a["date"] > tc - timedelta(days=1)]
    for a in moved:
        assert f"{a['firm']}: PT {a['pt_from']:.2f} → {a['pt_to']:.2f} on {a['date']}" in summary["changes"]
    older = [a for a in acts if a["kind"] == "Target change" and a["date"] < tc - timedelta(days=1)]
    assert not any(f"on {a['date']}" in x and a["firm"] in x for a in older for x in summary["changes"])


def test_layout_follows_house_formatting(built):
    # Hand edits on the DXCM tab, kept for every company: "Price:" next to the price, the column
    # headers repeated above the consensus rows, and header rows tall enough for their wrapped text
    _, out, _ = built
    ws = openpyxl.load_workbook(out)["Consensus"]
    assert ws["E3"].value == "Price:" and ws["E3"].font.b and ws["B3"].value is None
    cm = next(r for r in range(1, 80) if ws.cell(r, 2).value == "Consensus mean")
    assert ws.cell(cm - 1, 3).value == "Type" and ws.cell(cm - 1, 16).value == "Estimates from"
    assert ws.cell(cm - 1, 2).value is None and ws.row_dimensions[cm - 1].height == 32
    shop_hdr = next(r for r in range(cm, 120) if ws.cell(r, 4).value == "Rating / score")
    assert ws.row_dimensions[shop_hdr].height == 34
    bands = {str(ws.cell(r, 1).value)[:2]: r for r in range(1, ws.max_row + 1)
             if isinstance(ws.cell(r, 1).value, str) and ws.cell(r, 1).value[:2] in ("3.", "4.", "5.")}
    assert ws.row_dimensions[bands["3."] + 1].height == 34      # chart data headers (R-V)
    assert ws.row_dimensions[bands["4."] + 1].height == 17      # log header
    assert ws.row_dimensions[bands["5."] + 1].height == 51      # snapshot header
