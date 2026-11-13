import openpyxl
from evaluate import Book, ERR


def book():
    wb = openpyxl.Workbook()
    m = wb.active
    m.title = "MOD"
    m["A1"], m["A2"] = 10, 0                       # A3 left blank
    s = wb.create_sheet("S")
    s["B1"] = "=MOD!A1*2"
    s["B2"] = '=IFERROR(MOD!A1/MOD!A2,"n.a.")'
    s["B3"] = "=MOD!A1/MOD!A2"
    s["B4"] = "=MOD!A3+1"
    s["B5"] = '=IF(ISBLANK(MOD!A3),"",MOD!A3)'
    s["B6"] = '=IFERROR(B5+1,"")'
    s["B7"] = "=SUM(MOD!A1:A3)"
    s["B8"] = "=-199.7-217.7"
    s["B9"] = "=$B$1+B8"
    s["B10"] = '=IF(ISBLANK(MOD!A1),"",MOD!A1)'
    s["B11"] = '=IFERROR(B3,"n.a.")'
    return Book(wb)


def test_arithmetic_and_links():
    b = book()
    assert b.value("S", "B1") == 20
    assert abs(b.value("S", "B8") - (-417.4)) < 1e-9
    assert abs(b.value("S", "B9") - (20 - 417.4)) < 1e-9
    assert b.value("S", "B7") == 10


def test_excel_error_rules():
    b = book()
    assert b.value("S", "B2") == "n.a."          # IFERROR catches divide by zero
    assert b.value("S", "B3") is ERR             # unguarded divide by zero is an error
    assert b.value("S", "B11") == "n.a."         # IFERROR also catches an error coming from another cell
    assert b.value("S", "B4") == 1               # blank counts as 0
    assert b.value("S", "B5") == ""              # ISBLANK link to an empty estimate cell
    assert b.value("S", "B6") == ""              # "" + 1 is #VALUE! in Excel -> IFERROR alt
    assert b.value("S", "B10") == 10
