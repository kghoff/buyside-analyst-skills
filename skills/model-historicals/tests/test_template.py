"""The superset template must stay consistent however many optional rows a company drops."""
import os
import openpyxl
import pytest
from build import find_rows, prune, REQUIRED, OPTIONAL
from rows import drop_terms

T = os.path.join(os.path.dirname(__file__), "..", "assets", "core_template.xlsx")


def test_every_role_has_a_template_row():
    assert [r for r in REQUIRED if r not in find_rows(openpyxl.load_workbook(T).worksheets[0])] == []


def test_dropping_every_optional_row_leaves_sums_and_eps_consistent():
    wb = openpyxl.load_workbook(T); ws = wb.worksheets[0]
    prune(ws, find_rows(ws), set(), [])
    row = find_rows(ws)
    assert not set(OPTIONAL) & set(row)
    d = lambda role: ws.cell(row[role], 4).value
    assert d("EPSD") == f"=D{row['NI']}/D{row['SD']}"                    # no NCI / preferred: EPS on net income
    assert d("TCA") == f"=D{row['CASH']}"                                # only the always-kept lines remain
    assert d("NI") == f"=D{row['PRETAX']}+D{row['TAX']}"


def test_a_ratio_on_a_dropped_row_is_refused():
    # a deleted row inside a ratio would silently change its meaning
    assert drop_terms("=D5+D6+D7", {6}, {}) == "=D5+D7" and drop_terms("=D5-D6", {5}, {}) == "=-D6"
    with pytest.raises(ValueError):
        drop_terms("=D6/D27", {6}, {})
