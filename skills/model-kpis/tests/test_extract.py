"""Extractor rules that decide which reported figure lands in which model period."""
import json
import os
import subprocess
import sys

import openpyxl

from mdtable import restatement_bridges, table_rows
from ng_extract import blocks

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")

BRIDGE = """Itemized Reconciliation

| (In millions) | As Previously Reported | ASU 2020-06 Adjustment | As Adjusted |
|---|---|---|---|
| GAAP net income | $ 62.9 | $ 15.5 | $ 78.4 |
| Interest expense on senior convertible notes, net of tax | — | 1.2 | 1.2 |

| | Three Months Ended | |
|---|---|---|
| GAAP net income | 70.0 | 62.9 |
"""


def test_restatement_bridge_is_found_and_regular_tables_are_not():
    # its columns are 'old basis / adjustment / new basis', not periods: read as periods they put a restated
    # add-back (1.2) into a year the user's model keeps as originally filed (the v1 failure)
    br = restatement_bridges(BRIDGE)
    assert len(br) == 1 and br[0][0] == 3 and br[0][1] == 6
    assert "As Previously Reported" in br[0][2]


def test_as_adjusted_column_alone_is_not_a_bridge():
    # 2018 releases show 2017 'As Adjusted' comparatives in ordinary period columns; those ARE data
    t = "| | Q3 18 | Q3 17 As Adjusted |\n|---|---|---|\n| GAAP net income | 46.6 | (2.0 |\n"
    assert restatement_bridges(t) == []


OLD_SHARES = """| Non-GAAP diluted net income (loss) per share(6) | $ | 0.17 |  |  | 0.00 |  | $ | (0.25 | ) |  | $ | (0.63 | ) |
| Shares used to compute net income (loss) per share |  |  |  |  |  |  |  |
| Basic | 88.5 |  |  | 86.7 |  |  | 88.0 |  |  | 86.1 |  |
| Diluted | 90.3 |  |  | 86.7 |  |  | 89.3 |  |  | 86.1 |  |
"""


def test_old_basic_diluted_share_layout_gives_diluted_shares():
    # DXCM 2015-18 put the share counts under a heading; without them Q3 17 / Q4 17 / FY17 EPS stay blank
    got = [b for b in blocks(table_rows(OLD_SHARES)) if b[0] == "non-gaap diluted shares"]
    assert len(got) == 1 and got[0][1][0][2] == [90.3, 86.7, 89.3, 86.1]


def test_basic_row_is_not_taken_as_diluted():
    got = [b for b in blocks(table_rows(OLD_SHARES)) if b[0] == "non-gaap diluted shares"]
    assert all(r[2][0] != 88.5 for _, rows in got for r in rows)


def _model(path):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    hdr = ["Q1 21", "Q2 21", "Q3 21", "Q4 21", 2021, None, "Q1 22", "Q2 22", "Q3 22", "Q4 22", 2022]
    for i, h in enumerate(hdr): ws.cell(1, 3 + i, h)
    ws["A2"] = "INCOME STATEMENT"; ws["B5"] = "Net income"
    ws.cell(5, 4, 62.9); ws.cell(5, 10, 80.0)                 # Q2 21 as originally filed, Q2 22
    ws["A8"] = "BALANCE SHEET"
    wb.save(path)


RELEASE = """| | Three Months Ended June 30, | | Six Months Ended June 30, | |
|---|---|---|---|---|
| GAAP net income | 80.0 | 78.4 | 150.0 | 140.0 |
| Amortization of intangible assets | 1.0 | 0.5 | 2.0 | 1.0 |
| Non-GAAP net income | 81.0 | 78.9 | 152.0 | 141.0 |
| Interest expense on senior convertible notes, net of tax | 1.1 | 1.2 | 2.2 | 2.4 |
| Non-GAAP net income used for diluted EPS, if-converted | 82.1 | 80.1 | 154.2 | 143.4 |
"""


def test_extras_follow_their_documents_basis_and_skip_year_to_date(tmp_path):
    # the Q2 22 release's Q2 21 column is restated (GAAP 78.4 vs 62.9 filed): its add-back must not be used, and
    # the six-month column must never stand in for a quarter
    src = tmp_path / "src" / "Press Releases" / "_md"; src.mkdir(parents=True)
    (src / "Q2 22 TEST release 2022-07-28.md").write_text(RELEASE)
    m = str(tmp_path / "TEST_model.xlsx"); _model(m); w = str(tmp_path / "w")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "ng_extract.py"), "--src", str(tmp_path / "src"), "--model", m, "--work", w],
                   check=True, capture_output=True)
    C = json.load(open(os.path.join(w, "candidates.json")))["candidates"]
    ifc = {(c["period"], c["basis"]): c for c in C if c["metric"] == "if-converted add-back"}
    assert set(ifc) == {("Q2 22", "3M"), ("Q2 21", "3M")}
    assert ifc[("Q2 21", "3M")]["start_matches_model"] is False
    assert ifc[("Q2 22", "3M")]["start_matches_model"] is None


def test_call_transcripts_are_calls_not_releases():
    # 'Earnings Calls' contains 'earnings'; v2 ranked every transcript as a press release (the top source)
    from ng_extract import classify_doc
    assert classify_doc("/x/DXCM/Earnings Calls/_md/Q1 21 DXCM call.md") == "call"
    assert classify_doc("/x/DXCM/Press Releases/_md/Q1 21 DXCM release 2021-04-29.md") == "release"
    assert classify_doc("/x/Other folder/Q1 21 ACME earnings call transcript.md") == "call"


def test_period_from_year_first_and_old_file_names():
    # /collect-documents renamed folders to year-first; a wrong period here puts a release's numbers in the wrong column
    from ng_extract import period_of
    assert period_of("Press Releases/_md/2024 Q3 DXCM release 2024-10-24.md") == "Q3 24"
    assert period_of("10-Qs/_md/DXCM 2024 Q1 10-Q.md") == "Q1 24"       # not "Q1 10" from "Q1 10-Q"
    assert period_of("Press Releases/_md/Q3 24 DXCM release 2024-10-24.md") == "Q3 24"
    assert period_of("10-Ks/_md/DXCM 2024 10-K.md") == "FY 24"
    assert period_of("Investor Events/_md/2023-06-23 DXCM Investor Day.md") is None
