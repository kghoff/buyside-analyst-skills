import openpyxl

import mnotes
from xlsx import Package


def test_note_lands_on_the_cell_and_the_users_note_is_kept(model, tmp_path):
    """Every typed number carries its source; the user's own notes are never replaced."""
    pkg = Package(model)
    part = next(p for n, _, _, p in pkg.sheets() if n == "MOD")
    mnotes.add_notes(pkg, part, {"L4": "Update: Revenue 140.0 - rel.md line 14", "D4": "Update: test"})
    pkg.finish()
    out = str(tmp_path / "o.xlsx")
    pkg.save(out)
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws["L4"].comment.text.startswith("Update: Revenue 140.0")
    assert ws["D4"].comment.text.startswith("10-K 2025 line 10") and "Update: test" in ws["D4"].comment.text


def test_notes_on_a_sheet_with_no_comments_part(tmp_path):
    """A model with no notes on MOD yet must get a new comments part, not a crash."""
    p = str(tmp_path / "nc.xlsx")
    import make_fixture as mf
    mf.model(p)
    wb = openpyxl.load_workbook(p)
    wb["MOD"]["D4"].comment = None
    wb.save(p)
    pkg = Package(p)
    part = next(pp for n, _, _, pp in pkg.sheets() if n == "MOD")
    mnotes.add_notes(pkg, part, {"L4": "Update: Revenue 140.0 - rel.md line 14"})
    pkg.finish()
    out = str(tmp_path / "o.xlsx")
    pkg.save(out)
    ws = openpyxl.load_workbook(out)["MOD"]
    assert ws["L4"].comment.text.startswith("Update: Revenue") and ws["D4"].comment is None
