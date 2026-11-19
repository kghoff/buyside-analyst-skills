"""SUM must never disagree with the model, so every link is found by its LABEL on the source tab, not by a fixed row.
A row that moves must move the link; a block that is gone must stop the build and name the skill to rerun."""
import shutil

import openpyxl
import pytest

import links


@pytest.fixture(scope="module")
def L(fixture_model):
    return links.collect(fixture_model)


def test_cap_table_ties_to_the_dcf_bridge(L):
    d = L["dcf"]
    assert (d["price"], d["date"], d["shares"], d["net_debt"]) == ("DCF!$C$18", "DCF!$D$18", "DCF!$C$16", "DCF!$C$14")
    assert (d["cash"], d["st"], d["debt_cur"], d["debt_lt"]) == ("DCF!$C$10", "DCF!$C$11", "DCF!$C$12", "DCF!$C$13")


def test_primary_multiple_block(L):
    v = L["val"]
    assert v["kind"] == "P/E" and v["action"] == "Valuation!$B$3"
    assert v["hurdle"] == "Valuation!$B$9" and v["buy_rr"] == "Valuation!$B$10"
    p = v["primary"]
    assert p["ntm1"]["ref"] == "Valuation!$B$36" and p["ntm1"]["label"] == "P/E: NTM+1 EPS (Q1 27E to Q4 27E)"
    assert p["reward_price"]["ref"] == "Valuation!$B$39" and p["risk_metric"]["label"] == "P/E: risk EPS"
    assert p["risk_price"]["ref"] == "Valuation!$B$42" and v["blended_rr"] == "Valuation!$B$71"
    i = v["irr"]
    assert i["irr"]["ref"] == "Valuation!$B$91" and i["price3"]["ref"] == "Valuation!$B$90"
    assert i["mult3"]["ref"] == "Valuation!$B$88" and i["years"]["ref"] == "Valuation!$B$86"


def test_ladder_and_tree(L):
    v = L["val"]
    assert len(v["ladder"]) == 7 and v["ladder"][0]["entry"] == "Valuation!$B$75"
    assert [b["name"] for b in v["tree"]] == ["Bull", "Base", "Risk", "Bear"]
    # only branches whose target IS the primary multiple's reward / risk price get EPS x multiple columns
    assert [b["case"] for b in v["tree"]] == [None, "reward", "risk", None]
    assert v["tree_ev"]["target"] == "Valuation!$B$121"


def test_multiples_ranges_street_and_adv(L):
    m = L["mult"]
    assert m["ranges"]["abs"]["today"] == "Multiples!$B$7"
    assert m["ranges"]["abs"]["5 years median"] == "Multiples!$H$7"
    assert m["ranges"]["sp"]["label"] == "GAAP P/E − S&P 500 P/E" and m["ranges"]["peer"]["today"] == "Multiples!$B$13"
    assert m["street"] == {"2026E": "Multiples!$B$34", "2027E": "Multiples!$C$34"}
    assert m["adv"] == "Multiples!$H$39"


def test_mod_years_and_ntm_fcf_are_internal(L):
    md = L["mod"]
    assert md["years"] == ["2022", "2023", "2024", "2025", "2026E", "2027E", "2028E", "2029E"]
    assert md["ntm_quarters"] == ["Q1 26E", "Q4 26E"]
    assert md["ntm_fcf"].startswith("IF(COUNT(") and md["ntm_fcf"].count("$12") == 8   # 4 quarters x (COUNT + sum)
    assert md["basis"] == "gaap" and md["rows"]["ebitda"] == [6, 10]                    # GAAP: operating income + D&A


def test_moved_row_moves_the_link(fixture_model, tmp_path):
    m = str(tmp_path / "moved.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)
    wb["Valuation"].insert_rows(30)                 # everything from row 30 down moves one row
    wb.save(m)                                      # a test copy, never a user's model
    assert links.collect(m)["val"]["primary"]["reward_price"]["ref"] == "Valuation!$B$40"


def test_missing_block_names_the_skill(fixture_model, tmp_path):
    m = str(tmp_path / "gone.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)
    wb["Valuation"]["A83"] = None
    wb.save(m)
    with pytest.raises(SystemExit, match="model-valuation"):
        links.collect(m)


def test_missing_tab_names_the_skill(fixture_model, tmp_path):
    m = str(tmp_path / "nodcf.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)
    del wb["DCF"]
    wb.save(m)
    with pytest.raises(SystemExit, match="/model-dcf"):
        links.collect(m)
