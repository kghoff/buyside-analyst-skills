import os

from common import save, work_dir
from readcheck import DATA_COLS, GUIDE_COLS, bad_citations, check, status

LABELS = ["TEST 2024 10-K", "TEST 2025 10-K"]
GOOD = ("word " * 1000) + "Revenue grew [TEST 2024 10-K, Item 7]. " * 10


def setup(tmp_path, read=LABELS, notes=None, data_rows=None, guide_rows=None, bom=""):
    src = str(tmp_path)
    notes = GOOD if notes is None else notes
    w = work_dir(src)
    save(os.path.join(w, "slices.json"), [{"id": "s01", "title": "10-Ks", "category": "10-Ks", "hash": "h1",
                                            "files": [{"label": l} for l in LABELS]}])
    d = os.path.join(w, "readers", "s01")
    os.makedirs(d)
    open(os.path.join(d, "notes.md"), "w").write(notes)
    open(os.path.join(d, "files_read.txt"), "w", encoding="utf-8").write(bom + "\n".join(read))
    rows = data_rows if data_rows is not None else ["Installed base,FY2024,2.5,M users,\"TEST 2024 10-K, Item 1\""]
    open(os.path.join(d, "data.csv"), "w").write(",".join(DATA_COLS) + "\n" + "\n".join(rows) + "\n")
    g = guide_rows or []
    open(os.path.join(d, "guidance.csv"), "w").write(",".join(GUIDE_COLS) + "\n" + "\n".join(g) + "\n")
    return src


def test_a_complete_reader_passes_and_records_the_slice_hash(tmp_path):
    src = setup(tmp_path)
    assert check(src, "s01")["ok"]
    assert status(src) == {"done": ["s01"], "todo": []}


def test_an_unread_file_fails_the_check(tmp_path):
    # "every file must be read" is checked by code, not trusted to the agent
    r = check(setup(tmp_path, read=LABELS[:1]), "s01")
    assert not r["ok"] and any("not read: TEST 2025 10-K" in p for p in r["problems"])


def test_a_citation_to_a_file_outside_the_slice_fails(tmp_path):
    r = check(setup(tmp_path, notes="Bullish [2026-01-01 Firm note, p.2]."), "s01")
    assert not r["ok"] and any("outside this slice" in p for p in r["problems"])


def test_model_calc_and_users_notes_citations_are_allowed():
    assert bad_citations("[Model, MOD!D61] [Calc, from Item 7] [User's notes, Q3] [!KEY]", LABELS) == []


def test_data_rows_need_a_numeric_value_a_canonical_period_and_an_in_slice_source(tmp_path):
    r = check(setup(tmp_path, data_rows=['Users,2024,many,M,"Other doc, p1"']), "s01")
    text = " ".join(r["problems"])
    assert "not a finite number" in text and "period" in text and "not a file in this slice" in text


def test_status_sends_a_reader_back_when_its_slice_changed(tmp_path):
    src = setup(tmp_path)
    check(src, "s01")
    save(os.path.join(work_dir(src), "slices.json"), [{"id": "s01", "title": "10-Ks", "category": "10-Ks",
                                                        "hash": "h2", "files": [{"label": l} for l in LABELS]}])
    assert status(src)["todo"] == [{"id": "s01", "title": "10-Ks"}]


def test_semicolon_in_a_locator_is_not_a_split_but_two_sources_are():
    assert bad_citations("[TEST 2024 10-K, Item 7; Note 3]", LABELS) == []
    assert bad_citations("[TEST 2024 10-K, p1; TEST 2025 10-K, p2]", LABELS) == []
    assert bad_citations("[TEST 2024 10-K, p1; Other doc, p2]", LABELS) != []


def test_csv_source_cells_are_split_too(tmp_path):
    r = check(setup(tmp_path, data_rows=['Users,FY2024,1,M,"TEST 2024 10-K, p1; Other doc, p2"']), "s01")
    assert not r["ok"] and "not a file in this slice" in " ".join(r["problems"])


def test_always_ok_is_an_exact_first_segment():
    assert bad_citations("[Calcium Corp, p1]", LABELS) != []
    assert bad_citations("[Calc, from TEST 2019 10-K]", LABELS) == []


def test_comma_free_citation_outside_slice_fails_but_short_brackets_are_ignored():
    assert bad_citations("[TEST 2019 10-K]", LABELS) != []
    assert bad_citations("[TEST 2024 10-K] [?] [x] [!KEY]", LABELS) == []


def test_other_brackets_with_commas_are_flagged_with_the_parentheses_message(tmp_path):
    r = check(setup(tmp_path, notes=GOOD + " [see a, b]"), "s01")
    assert not r["ok"] and "use parentheses for anything else" in " ".join(r["problems"])


def test_thin_notes_fail(tmp_path):
    r = check(setup(tmp_path, notes="Short [TEST 2024 10-K, p1]."), "s01")
    assert any("notes.md too thin (" in p for p in r["problems"])


def test_a_bom_in_files_read_still_passes(tmp_path):
    assert check(setup(tmp_path, bom="\ufeff"), "s01")["ok"]


def test_nan_and_inf_values_fail(tmp_path):
    r = check(setup(tmp_path, data_rows=['A,FY2024,nan,M,"TEST 2024 10-K, p1"', 'B,FY2024,inf,M,"TEST 2024 10-K, p1"']), "s01")
    assert " ".join(r["problems"]).count("not a finite number") == 2


def test_unknown_slice_reports_instead_of_crashing(tmp_path):
    r = check(setup(tmp_path), "s99")
    assert r == {"ok": False, "problems": ["unknown slice s99"]}
