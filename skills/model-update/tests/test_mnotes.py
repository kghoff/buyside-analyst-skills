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
