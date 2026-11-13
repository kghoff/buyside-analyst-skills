# tests/test_firms.py
import pytest

import firms
from conftest import snap


@pytest.fixture(scope="module")
def F():
    return firms.Firms()


@pytest.mark.parametrize("raw,name", [
    ("JP Morgan", "J.P. Morgan"), ("JP MORGAN SECUR", "J.P. Morgan"), ("J.P. Morgan", "J.P. Morgan"),
    ("B OF A GLBL RES", "BofA Securities"), ("BofA Securities", "BofA Securities"),
    ("BARCLAYS CAPITA", "Barclays"), ("BAIRD R W", "Baird"), ("LEERINK PARTNRS", "Leerink Partners"),
    ("SANFORD BERNSTE", "Bernstein"), ("Canaccord Genuity", "Canaccord Genuity"), ("CANACCORD GENUI", "Canaccord Genuity"),
    ("Cowen & Co.", "TD Cowen"), ("Credit Suisse", "UBS"), ("Citigroup", "Citi"), ("UBS", "UBS"),
    ("Morgan Stanley", "Morgan Stanley"), ("WELLS FARGO SEC", "Wells Fargo"), ("ZACKS RESEARCH", "Zacks"),
])
def test_names_from_different_sources_match_one_firm(F, raw, name):
    # Yahoo, Nasdaq (15-character truncations) and report file names spell the same firm differently; one firm must
    # come out, or the broker table double-counts it
    assert F.match(raw)["name"] == name


def test_unknown_name_is_not_guessed(F):
    assert F.match("Totally New Research LLC") is None


def test_types_keep_rating_shops_out_of_the_analyst_set(F):
    # House default: "analyst estimates" means banks and independent research firms, not rating shops
    assert F.match("Goldman Sachs")["type"] == "bank"
    assert F.match("Evercore ISI")["type"] == "independent"
    assert F.match("Leerink Partners")["type"] == "specialist"
    assert F.match("Morningstar")["type"] == "rating shop"
    assert F.match("Zacks")["type"] == "quant"
    assert firms.ANALYST == ("bank", "independent", "specialist")


@pytest.mark.parametrize("grade,bucket", [
    ("Overweight", "Buy"), ("Outperform", "Buy"), ("Market Outperform", "Buy"), ("Strong Buy", "Buy"),
    ("Accumulate", "Buy"), ("Neutral", "Hold"), ("Equal-Weight", "Hold"), ("Sector Perform", "Hold"),
    ("Peer Perform", "Hold"), ("Market Perform", "Hold"), ("In-Line", "Hold"), ("Underweight", "Sell"),
    ("Underperform", "Sell"), ("Reduce", "Sell"), ("Sell", "Sell"),
])
def test_rating_words_group_into_three_buckets(F, grade, bucket):
    assert F.bucket(grade) == bucket


def test_unknown_rating_word_is_flagged_not_guessed(F):
    assert F.bucket("Spicy") is None
    assert F.bucket("") is None


def test_check_on_a_real_snapshot_returns_lists(F):
    out = firms.check(snap("DXCM"), F)
    assert set(out) == {"unknown_firms", "unknown_grades"}
    assert all(isinstance(x, str) for x in out["unknown_firms"] + out["unknown_grades"])


@pytest.mark.parametrize("raw", ["Atlantic Equities", "Rothschild & Co Redburn", "Redburn Atlantic", "Redburn"])
def test_atlantic_equities_and_redburn_are_one_firm(F, raw):
    # Rothschild & Co merged Atlantic Equities into Redburn: one firm, or the broker table double-counts it
    assert F.match(raw)["name"] == "Redburn Atlantic"
    assert F.match(raw)["type"] == "independent"


@pytest.mark.parametrize("raw,name", [
    ("BTIG LLC", "BTIG"), ("UBS Investment Bank", "UBS"), ("Citi Global Markets", "Citi"),
    ("CFRA Equity Research", "CFRA"), ("Citizens JMP", "Citizens JMP"), ("Citizens", "Citizens JMP"),
])
def test_name_with_a_trailing_word_matches_even_when_the_firm_name_is_short(F, raw, name):
    # a short firm name followed by a word break is safe; "citizens" must not collapse into "citi"
    assert F.match(raw)["name"] == name


@pytest.mark.parametrize("grade,bucket", [
    ("Equalweight", "Hold"), ("Hold/Neutral", "Hold"), ("Speculative Hold", "Hold"),
    ("Sector Overweight", "Buy"), ("Market Overweight", "Buy"), ("Moderate Outperform", "Buy"),
    ("Sector Outperformer", "Buy"), ("Sector Underweight", "Sell"), ("Market Underweight", "Sell"),
    ("Moderate Sell", "Sell"), ("Avoid", "Sell"),
    ("Not Rated", "Unrated"), ("NR", "Unrated"), ("Under Review", "Unrated"), ("Suspended", "Unrated"),
    ("Restricted", "Unrated"), ("Coverage Suspended", "Unrated"), ("Tender", "Unrated"),
])
def test_more_rating_words_and_an_unrated_bucket(F, grade, bucket):
    # no-opinion words must not be counted as Buy/Hold/Sell
    assert F.bucket(grade) == bucket


def test_company_forecast_is_not_a_research_firm(F):
    f = F.match("Company Forecast")
    assert f["type"] == "other" and f["note"]
    assert "other" not in firms.ANALYST


def test_every_alias_maps_back_to_its_own_firm(F):
    # a pre-seeded alias that matches another firm would silently misfile its ratings
    for f in F.firms:
        for a in [f["name"]] + f.get("aliases", []):
            assert F.match(a)["name"] == f["name"], (a, f["name"])


@pytest.mark.parametrize("raw,name", [
    ("HSBC", "HSBC"), ("Susquehanna Financial Group", "Susquehanna"), ("Keefe Bruyette and Woods", "KBW"),
    ("B. Riley Securities", "B. Riley"), ("Seaport Global", "Seaport Research Partners"),
    ("Nomura Instinet", "Nomura"), ("Telsey", "Telsey Advisory Group"), ("Monness", "Monness Crespi Hardt"),
    ("Arete", "Arete Research"), ("Charles Schwab", "Schwab"), ("Edward D. Jones", "Edward Jones"),
    ("Macquarie", "Macquarie"), ("Berenberg", "Berenberg"), ("Erste Group", "Erste Group"), ("Daiwa", "Daiwa"),
])
def test_preseeded_firms(F, raw, name):
    assert F.match(raw)["name"] == name
