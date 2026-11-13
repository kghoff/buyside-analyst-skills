import fiscal


def test_calendar_year_uses_most_months():
    # MDT's year ends in April: FY2025 (May 2024 - Apr 2025) is mostly 2024. Comparing it with DXCM's calendar
    # 2025 would put a year-old Medtronic next to this year's DexCom.
    assert fiscal.calendar_year("2025-04-25") == 2024
    assert fiscal.calendar_year("2025-12-31") == 2025
    assert fiscal.calendar_year("2026-01-03") == 2025      # 52/53-week year ending early January
    assert fiscal.calendar_year("2025-02-01") == 2024      # retailer year ending Feb 1
    assert fiscal.calendar_year("2025-06-30") == 2025      # 6/6 tie -> the end year
    assert fiscal.calendar_year("2025-09-27") == 2025


def test_fy_ends_prefers_filings_then_falls_back_to_fiscal_year_end():
    sec = {"fiscalYearEnd": "0425", "filings": [{"fy": 2025, "reportDate": "2025-04-25"},
                                                 {"fy": 2024, "reportDate": "2024-04-26"}]}
    ends = fiscal.fy_ends(sec, [2023, 2024, 2025])
    assert ends == {2023: "2023-04-25", 2024: "2024-04-26", 2025: "2025-04-25"}
