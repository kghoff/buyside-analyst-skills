import json
import os

from conftest import FIX
import lines


def test_every_line_has_a_label_and_input_lines_have_sources():
    # a line with no MOD pattern or no XBRL field would silently stay blank for every company
    for k in lines.INPUTS:
        assert k in lines.MOD and k in lines.XBRL, k
    assert set(lines.CALC) == {"gross_profit", "ebitda", "fcf"}
    assert set(lines.KEYS) == set(lines.INPUTS) | set(lines.CALC)


def test_xbrl_values_follow_house_sign_convention():
    # MOD convention: costs and outflows negative, so Gross Profit = Revenue + COGS and FCF = CFO + CapEx
    d = json.load(open(os.path.join(FIX, "abt_xbrl.json")))
    by_fy, tags = lines.from_xbrl(d)
    assert by_fy["revenue"][2025] == 44328.0
    assert by_fy["cogs"][2025] == -19319.0
    assert by_fy["capex"][2025] == -2171.0
    assert by_fy["dividends"][2025] < 0
    assert by_fy["tax"][2025] == -1942.0
    assert tags["revenue"][2025] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert "Goodwill" in tags["gwi"][2025]
