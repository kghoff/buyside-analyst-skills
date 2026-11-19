"""verify.py: the last gate before the finished copy replaces the user's model. Each test is a way a print-night copy
can be damaged that must stop the run instead of reaching the user's file."""
import json
import zipfile

import openpyxl

import actuals
import match
import modmap
import release
import verify
import make_fixture as mf

STATE = {"column": "L", "fy_column": None, "release_values": {}, "placeholders": []}


def _built(model, tmp_path):
    """The print-night copy actuals.build makes from the fixture's Q3 26 release with two balance-sheet lines printed
    only as one combined line (so they wait, as orange forecast placeholders)."""
    res = match.match(release.parse_text(mf.release_md("combined"), "rel.md"), modmap.ModMap(model), mf.values(), "Q3 26E")
    res["leftover"] = []
    out, sp = str(tmp_path / "out.xlsx"), str(tmp_path / "state.json")
    actuals.build(model, "Q3 26E", res, out, sp, grid=mf.preprint())
    return out, json.load(open(sp))


def _edit(src, out, fn):
    wb = openpyxl.load_workbook(src)
    fn(wb)
    wb.save(out)
    return out


def test_untouched_model_passes(model):
    assert verify.static(model, model, STATE, allow_cols=set()) == []
    assert verify.parts(model, model) == [] and verify.links(model, model) == []


def test_a_real_print_night_copy_passes_the_file_checks(model, tmp_path):
    """The copy actuals.build writes (typed values, placeholders, notes, header flip) is exactly what verify allows:
    a gate that fails every honest run would be switched off."""
    out, st = _built(model, tmp_path)
    assert st["release_values"] and st["placeholders"]
    assert verify.static(model, out, st, verify.allowed_cols(model, st)) == []
    assert verify.parts(model, out) == []
    assert verify.links(model, out) == []


def test_a_changed_cell_outside_the_allowed_columns_is_caught(model, tmp_path):
    """Only the reported quarter, its year (Q4) and the forecast may change; anything else is damage to history."""
    out = _edit(model, str(tmp_path / "x.xlsx"), lambda wb: wb["MOD"].__setitem__("F4", 999))
    probs = verify.static(model, out, STATE, allow_cols={"L"})
    assert any("MOD!F4" in p for p in probs)


def test_a_restated_cell_the_user_approved_is_allowed(model, tmp_path):
    out = _edit(model, str(tmp_path / "x.xlsx"), lambda wb: wb["MOD"].__setitem__("F4", 121))
    assert verify.static(model, out, STATE, allow_cols={"L"}, restated={"F4"}) == []


def test_the_q4_year_column_is_allowed_only_when_state_names_it(model):
    """On a Q4 print the FY column is typed from the release; on Q1-Q3 it must not move."""
    hist = verify.allowed_cols(model, {"column": "K", "fy_column": "H"})
    assert "H" in hist and "G" not in hist
    assert "H" not in verify.allowed_cols(model, {"column": "L", "fy_column": None})


def test_a_typed_release_value_without_its_note_is_caught(model, tmp_path):
    """Every typed number carries its source; a bare blue number is one the user can't trace."""
    out, st = _built(model, tmp_path)
    ref = next(iter(st["release_values"]))
    bare = _edit(out, str(tmp_path / "bare.xlsx"), lambda wb: setattr(wb["MOD"][ref], "comment", None))
    probs = verify.static(model, bare, st, verify.allowed_cols(model, st))
    assert f"MOD!{ref} has no 'Update: ' note" in probs


def test_a_placeholder_that_is_not_orange_or_has_no_note_is_caught(model, tmp_path):
    """A placeholder is a forecast standing in a reported column: unless it is orange and says so, it reads as an
    actual."""
    out, st = _built(model, tmp_path)
    ref = st["placeholders"][0]["ref"]

    def hide(wb):
        c = wb["MOD"][ref]
        c.font = openpyxl.styles.Font(color="FF0000FF")
        c.comment = None
    bad = _edit(out, str(tmp_path / "bad.xlsx"), hide)
    probs = verify.static(model, bad, st, verify.allowed_cols(model, st))
    assert f"MOD!{ref} placeholder is not orange" in probs
    assert f"MOD!{ref} has no 'Update: ' note" in probs


def test_a_placeholder_note_on_a_cell_state_does_not_list_is_caught(model, tmp_path):
    """The awaiting list is what the 10-Q rerun fills; a placeholder missing from it would stay a forecast forever."""
    out, st = _built(model, tmp_path)
    st = dict(st, placeholders=st["placeholders"][1:])
    probs = verify.static(model, out, st, verify.allowed_cols(model, st))
    assert any("placeholder note but is not listed" in p for p in probs), probs


def test_a_link_that_now_points_at_another_line_is_caught(model, tmp_path):
    """Valuation!B3 reads Revenue 2026; if MOD rows shift under it, every valuation built on it is silently wrong."""
    def swap(wb):
        wb["MOD"]["B4"], wb["MOD"]["B6"] = "Cost of sales", "Revenue"
    out = _edit(model, str(tmp_path / "y.xlsx"), swap)
    assert verify.links(model, out) == ["Valuation!B3 -> MOD!N4: was 'Revenue', now 'Cost of sales'"]


def test_a_changed_part_on_another_tab_is_caught_but_mods_own_parts_are_not(model, tmp_path):
    """Other tabs (Earnings band 7, Valuation...) must be byte-identical; MOD's sheet, rels and notes may change."""
    out, _ = _built(model, tmp_path)
    assert verify.parts(model, out) == []
    bad = str(tmp_path / "bad.xlsx")
    with zipfile.ZipFile(out) as zi, zipfile.ZipFile(bad, "w") as zo:
        for i in zi.infolist():
            data = zi.read(i.filename)
            if i.filename == "xl/worksheets/sheet2.xml":            # the Earnings tab
                data = data.replace(b"FROZEN FORECAST", b"FROZEN FORECASX") if b"FROZEN" in data else data + b" "
            zo.writestr(i, data)
    assert verify.parts(model, bad) == ["part changed: xl/worksheets/sheet2.xml"]


def test_new_error_cells_are_caught_but_ones_the_model_already_had_are_not():
    """A real model may carry a few errors the user lives with; only errors the update adds stop the run."""
    before = {"MOD": {"A1": "#DIV/0!", "B1": 1}, "DCF": {"C3": "#REF!"}}
    same = {"MOD": {"A1": "#DIV/0!", "B1": 2}, "DCF": {"C3": "#REF!"}}
    worse = {"MOD": {"A1": "#DIV/0!", "B1": "#VALUE!"}, "DCF": {"C3": "#REF!"}}
    assert verify.new_errors(before, same) == []
    assert verify.new_errors(before, worse) == ["MOD: 2 error cells, was 1 (MOD!B1)"]
    assert verify.new_errors({}, {"MOD": {"A1": "#N/A"}}) == ["MOD: 1 error cells, was 0 (MOD!A1)"]


def test_a_balance_sheet_that_does_not_balance_in_the_reported_column_is_caught(model):
    """Assets must equal liabilities and equity in the quarter just reported, or a line landed on the wrong row."""
    ok = {"L17": 103.0, "L20": 103.0}
    assert verify.balance(ok, model, "L") == []
    assert verify.balance({"L17": 103.0, "L20": 101.0}, model, "L") == [
        "balance sheet does not balance in L: total assets 103.0 vs liabilities and equity 101.0"]


def test_a_users_own_note_with_the_update_note_appended_counts(model, tmp_path):
    """On a cell that already had the user's note, the 'Update: ' text is appended after it (the user's words are
    kept): that cell is sourced, and failing it would stop every run on a real model full of notes."""
    from openpyxl.comments import Comment
    noted = _edit(model, str(tmp_path / "noted.xlsx"),
                  lambda wb: setattr(wb["MOD"]["L4"], "comment", Comment("my revenue note", "user")))
    out, st = _built(noted, tmp_path)
    assert "L4" in st["release_values"]
    assert verify.static(noted, out, st, verify.allowed_cols(noted, st)) == []


def test_the_balance_rows_are_found_in_a_real_models_spelling(model, tmp_path):
    """The user's DXCM model writes 'TOTAL ASSETS:' and 'TOTAL LIABILITIES & EQUITY:'; missing them skipped the
    check without a word."""
    def caps(wb):
        wb["MOD"]["B17"], wb["MOD"]["B20"] = "TOTAL ASSETS:", "TOTAL LIABILITIES & EQUITY:"
    p = _edit(model, str(tmp_path / "caps.xlsx"), caps)
    assert verify.balance({"L17": 103.0, "L20": 101.0}, p, "L") != []


def test_a_model_without_the_balance_rows_says_so_instead_of_passing(model, tmp_path):
    p = _edit(model, str(tmp_path / "nobs.xlsx"), lambda wb: wb["MOD"].__setitem__("B17", "Assets"))
    assert verify.balance({"L17": 103.0, "L20": 103.0}, p, "L") == [
        "balance sheet check: no 'Total assets' and 'Total liabilities and equity' rows found in MOD column B"]


def _forecast_col(path):
    return sorted(verify.forecast_cols(path))[0]


def test_a_roll_that_changes_only_forecast_columns_passes(model, tmp_path):
    """The roll rewrites forecast assumptions on the actuals copy; that is the whole point of it and must pass."""
    mid, st = _built(model, tmp_path)
    c = _forecast_col(mid)
    after = _edit(mid, str(tmp_path / "rolled.xlsx"), lambda wb: wb["MOD"].__setitem__(f"{c}4", 777))
    assert verify.roll(mid, after, st) == []


def test_a_roll_that_writes_into_the_reported_quarter_is_caught(model, tmp_path):
    """The reported column holds the release's numbers; a forecast build writing there would overwrite actuals."""
    mid, st = _built(model, tmp_path)
    after = _edit(mid, str(tmp_path / "rolled.xlsx"), lambda wb: wb["MOD"].__setitem__(f"{st['column']}4", 1))
    assert any(f"MOD!{st['column']}4" in p for p in verify.roll(mid, after, st))


def test_a_roll_that_moves_mod_rows_is_refused_because_state_refs_would_go_stale(model, tmp_path):
    """state.json names the awaiting cells, placeholders and typed subtotals by cell; if the roll inserts or moves a MOD
    row they point at the wrong rows and the 10-Q rerun would fill (or put formulas into) the wrong cells. Every
    reference moving consistently (as Excel's insert does) does not make it safe, so the move itself stops the run."""
    from xlsx import Package
    from xledit import insert_rows
    mid, st = _built(model, tmp_path)
    pkg = Package(mid)
    insert_rows(pkg, "MOD", 5, 1)                  # a row inserted by a build: everything below shifts, links follow
    pkg.finish()
    after = str(tmp_path / "moved.xlsx")
    pkg.save(after)
    assert verify.links(mid, after) == []          # the links still read the same lines: only the move check sees it
    probs = verify.roll(mid, after, st)
    assert len(probs) == 1 and "moved" in probs[0] and "/model-forecast" in probs[0]
