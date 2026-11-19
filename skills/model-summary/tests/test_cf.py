"""The colours must follow Valuation's house inputs: the IRR rule compares with the hurdle cell (a link to
Valuation's IRR hurdle) and the R/R rules with the Buy-at-R/R cell (a link), so changing either on Valuation recolours
SUM. Expected Delta follows the yellow band. No threshold is a typed number inside a rule."""
import re
import zipfile

import openpyxl


def _sheet_xml(out):
    z = zipfile.ZipFile(out)
    wb = z.read("xl/workbook.xml").decode()
    rid = re.search(r'<sheet name="SUM"[^>]*r:id="([^"]+)"', wb).group(1)
    rels = z.read("xl/_rels/workbook.xml.rels").decode()
    target = re.search(rf'Id="{rid}"[^>]*Target="([^"]+)"', rels).group(1)
    return z.read("xl/" + target).decode()


def _rules(out):
    x = _sheet_xml(out)
    return [(m.group(1), m.group(2)) for m in
            re.finditer(r'<conditionalFormatting sqref="([^"]+)">.*?<formula>(.*?)</formula>', x)]


def test_irr_rule_reads_the_linked_hurdle(built):
    rules = _rules(built[0])
    assert ("C33", "AND(ISNUMBER(C33),C33&gt;=$C$34)") in rules
    assert openpyxl.load_workbook(built[0])["SUM"]["C34"].value == "=Valuation!$B$9"


def test_rr_rules_read_the_linked_buy_threshold(built):
    rules = _rules(built[0])
    ladder = [f for s, f in rules if s == "AA5:AA11"]
    assert len(ladder) == 3 and all("$C$50" in f or "&lt;1)" in f for f in ladder)
    assert openpyxl.load_workbook(built[0])["SUM"]["C50"].value == "=Valuation!$B$10"


def test_street_variance_follows_the_band(built):
    """Both delta rows (EPS row 15, revenue row 8) turn green / red on the same yellow band."""
    rules = _rules(built[0])
    for r in (15, 8):
        assert [f for s, f in rules if s == f"F{r}:M{r}"] == [f"AND(ISNUMBER(F{r}),F{r}&gt;$C$51)",
                                                              f"AND(ISNUMBER(F{r}),F{r}&lt;-$C$51)"]


def test_returns_are_signed(built):
    sq = {s for s, _ in _rules(built[0])}
    assert {"C30", "C40", "C47", "T5:T9"} <= sq
