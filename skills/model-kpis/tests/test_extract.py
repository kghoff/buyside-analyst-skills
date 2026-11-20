"""Extractor rules that decide which reported figure lands in which model period."""
import json
import re
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


def test_sellside_notes_are_not_company_releases_or_calls():
    # 'JPM earnings recap' matched 'earnings' and was ranked as a company release, so a broker's figures could be read
    # into the KPI history as if the company printed them
    from ng_extract import classify_doc
    assert classify_doc("/x/ABT/Sellside Research/1 Broker Research/_md/2026-10-21 JPM earnings recap - Model Update.md") == "sellside"
    assert classify_doc("/x/ABT/Sellside Research/1 Broker Research/_md/2026-10-21 JPM earnings recap - Key Takeaways from Our 3Q26 Call.md") == "sellside"


SFM_RELEASE = """NON-GAAP MEASURE RECONCILIATION

(IN THOUSANDS, EXCEPT PER SHARE AMOUNTS)

|  | Thirteen weeks ended | Thirteen weeks ended | Twenty-six weeks ended | Twenty-six weeks ended |
| --- | --- | --- | --- | --- |
| Net income | $ | 35,343 |  |  | $ | 41,709 |  |  | $ | 91,735 |  |  | $ | 108,333 |  |
| Income tax provision (1) | 10,551 |  | 13,565 |  | 28,713 |  | 20,764 |
| Interest expense, net | 5,438 |  | 6,540 |  | 10,440 |  | 12,604 |
| Earnings before interest and taxes (EBIT) | 51,332 |  | 61,814 |  | 130,888 |  | 141,701 |
| Depreciation, amortization and accretion | 30,139 |  | 27,087 |  | 60,211 |  | 53,976 |
| Earnings before interest, taxes, depreciation and amortization (EBITDA) | $ | 81,471 |  | $ | 88,901 |  | $ | 191,099 |  | $ | 195,677 |
| Special Items: |  |  |  |  |
| Store closures (2) | — |  | — |  | 508 |  | — |
| Total Special Items - pre-tax | — |  | — |  | 508 |  | — |
| Adjusted EBITDA | $ | 81,471 |  | $ | 88,901 |  | $ | 191,607 |  | $ | 195,677 |
| Net income | $ | 35,343 |  | $ | 41,709 |  | $ | 91,735 |  | $ | 108,333 |
| Special Items: |  |  |  |  |
| Store closures, net of tax (2) | 1,000 |  | — |  | 377 |  | — |
| Adjusted Net income | $ | 36,343 |  | $ | 41,709 |  | $ | 92,112 |  | $ | 108,333 |
| Diluted earnings per share | $ | 0.30 |  | $ | 0.32 |  | $ | 0.76 |  | $ | 0.82 |
| Adjusted diluted earnings per share | $ | 0.31 |  | $ | 0.32 |  | $ | 0.76 |  | $ | 0.82 |
"""


def test_thousands_release_with_plain_gaap_start_and_printed_subtotals(tmp_path):
    # SFM: tables in thousands (model in millions), start at plain 'Net income' (no 'GAAP' prefix), print EBIT /
    # EBITDA / 'Total special items' subtotals inside the walk, and say 'Adjusted diluted earnings per share'.
    # Before: 0 candidates from 172 files, so the model got no non-GAAP section at all.
    src = tmp_path / "src" / "Press Releases" / "_md"; src.mkdir(parents=True)
    (src / "2019 Q2 TEST release 2019-08-01.md").write_text(SFM_RELEASE)
    m = str(tmp_path / "TEST_model.xlsx")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "MOD"
    for i, h in enumerate(["Q1 18", "Q2 18", "Q3 18", "Q4 18", 2018, None, "Q1 19", "Q2 19", "Q3 19", "Q4 19", 2019]):
        ws.cell(1, 3 + i, h)
    ws["A2"] = "INCOME STATEMENT"; ws["B5"] = "Net income"
    ws.cell(5, 4, 41.709); ws.cell(5, 10, 35.343)
    ws["A8"] = "BALANCE SHEET"; wb.save(m)
    w = str(tmp_path / "w")
    subprocess.run([sys.executable, os.path.join(SCRIPTS, "ng_extract.py"), "--src", str(tmp_path / "src"), "--model", m, "--work", w],
                   check=True, capture_output=True)
    C = json.load(open(os.path.join(w, "candidates.json")))["candidates"]
    by = {(c["metric"], c["period"], c["basis"]): c for c in C}
    e = by[("adjusted ebitda", "Q2 19", "3M")]
    assert e["start"] == 35.343 and e["end"] == 81.471 and e["start_matches_model"] is True
    labels = [x[0] for x in e["items"]]
    assert not any(re.search(r"EBIT|Total Special", x) for x in labels)          # printed subtotals are not items
    assert abs(sum(x[1] for x in e["items"]) - (81.471 - 35.343)) < 0.001
    n = by[("non-gaap net income", "Q2 19", "3M")]
    assert n["end"] == 36.343 and [x[1] for x in n["items"]] == [1.0]
    eps = by[("reported non-gaap eps", "Q2 19", "3M")]
    assert eps["value"] == 0.31                                                   # per-share amounts are not scaled


def test_diluted_share_row_right_after_adjusted_eps_gives_non_gaap_shares():
    # SFM prints 'Diluted weighted average shares outstanding' under 'Adjusted diluted earnings per share'; without
    # it the non-GAAP EPS row stays blank for every period
    t = ("| Adjusted diluted earnings per share | $ | 0.31 |  | $ | 0.32 |\n"
         "| Diluted weighted average shares outstanding | 118.436 |  | 130.012 |\n")
    got = [b for b in blocks(table_rows(t)) if b[0] == "non-gaap diluted shares"]
    assert len(got) == 1 and got[0][1][0][2] == [118.436, 130.012]


def test_gaap_share_row_after_non_gaap_eps_is_not_non_gaap_shares():
    # DXCM prints 'GAAP diluted weighted-average shares' under non-GAAP EPS; it differs from the non-GAAP count
    # (if-converted shares), so it must not be read as one
    t = ("| Non-GAAP diluted net income per share | $ | 0.50 |  |\n"
         "| GAAP diluted weighted-average shares outstanding | 104.3 |  |\n")
    assert not [b for b in blocks(table_rows(t)) if b[0] == "non-gaap diluted shares"]
