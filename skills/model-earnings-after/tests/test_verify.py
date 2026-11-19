"""verify.compare without LibreOffice, on hand-made recalculated copies: a wrong or broken cell in bands 9-15 stops
the copy from replacing the model, while an error above the start that the user's model already showed is not ours
and must not stop it (only a new one is worth a warning). A Call Notes tab without this quarter means the build lost
the call summary."""
import openpyxl

import verify


def _book(path, band_err=False, old_err=True, new_err=False, quarter="Q4 26", cn_err=False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Earnings"
    if old_err:
        ws["B2"] = "#DIV/0!"
    if new_err:
        ws["B3"] = "#REF!"
    ws["B10"], ws["B11"] = 0.08, "#N/A"
    if band_err:
        ws["C12"] = "#VALUE!"
    cn = wb.create_sheet("Call Notes")
    cn["A4"], cn["B4"] = "Topic", quarter
    if cn_err:
        cn["B8"] = "#NAME?"
    wb.save(path)
    return str(path)


LAY = {"start": 10, "expected": {"$B$10": 0.08, "$B$11": None}}


def test_clean_copy_passes_and_old_errors_above_are_not_ours(tmp_path):
    before = _book(tmp_path / "in.xlsx")
    assert verify.compare(_book(tmp_path / "v.xlsx"), LAY, "Q4 26", before) == ([], [])


def test_wrong_value_missing_na_and_stray_error_are_problems(tmp_path):
    v = _book(tmp_path / "v.xlsx", band_err=True)
    probs, _ = verify.compare(v, {"start": 10, "expected": {"$B$10": 0.09, "$B$11": None}}, "Q4 26")
    assert any("B$10" in p for p in probs) and any("C12" in p for p in probs)
    probs, _ = verify.compare(v, {"start": 10, "expected": {"$B$10": 0.08, "$B$11": 1.0}}, "Q4 26")
    assert any("B$11" in p for p in probs)


def test_a_new_error_above_the_start_is_a_warning_not_a_problem(tmp_path):
    before = _book(tmp_path / "in.xlsx")
    probs, warn = verify.compare(_book(tmp_path / "v.xlsx", new_err=True), LAY, "Q4 26", before)
    assert probs == [] and len(warn) == 1 and "1 error cell" in warn[0] and "B3" in warn[0] and "B2" not in warn[0]


def test_call_notes_errors_and_missing_quarter(tmp_path):
    probs, _ = verify.compare(_book(tmp_path / "v.xlsx", quarter="Q3 26", cn_err=True), LAY, "Q4 26")
    assert any("Call Notes!B8" in p for p in probs) and any("no column for Q4 26" in p for p in probs)
