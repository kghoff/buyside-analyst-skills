from numcheck import check_report, numbers, quotes

SOURCES = {"TEST 2024 10-K": "Revenue was $1,234.5 million, up 12.34% from 2023. Gross margin was 61.2%."}
POOL = [0.1234, 1234.5, 290.0]
MODEL = {"Model, MOD!H61": [500.0], "Model, MOD!I61": [700.0]}


def run(md):
    return check_report(md, SOURCES, MODEL, POOL)


def test_a_number_in_its_cited_source_is_confirmed():
    r = run("Revenue grew 12.3% [TEST 2024 10-K, Item 7].")
    assert r["confirmed"] == 1 and r["unconfirmed"] == []


def test_a_number_missing_from_its_cited_source_is_flagged():
    # the whole point of provenance: a cited number has to be in the citation
    r = run("Gross margin was 64.0% [TEST 2024 10-K, Item 7].")
    assert r["unconfirmed"][0]["number"] == "64.0%"


def test_precision_follows_what_was_written_and_billions_scale_from_millions():
    # a small number needs a 3+ digit anchor from the same unit, found near it in the source
    assert run("Revenue was $1.2 billion, up 12.3% [TEST 2024 10-K, Item 7].")["confirmed"] == 2
    assert run("Revenue was $1.3 billion [TEST 2024 10-K, Item 7].")["unconfirmed"]


def test_years_quarters_slides_and_items_are_not_checked():
    assert numbers("In FY2024 and 2023, Q3, S41, Item 7, slide 12 we had none") == []


def test_an_uncited_number_is_listed():
    assert run("Revenue was $1,234.5 million.")["uncited"][0]["number"] == "$1,234.5 million"


def test_calc_numbers_are_checked_against_the_driver_math():
    assert run("Operating income rose by 290.0 (Calc).")["confirmed"] == 1
    assert run("Margin was 12.3% (Calc).")["confirmed"] == 1          # 0.1234 in the pool, written as a percent


def test_a_table_row_without_its_own_citation_uses_the_caption_below():
    md = "| Year | Revenue |\n|---|---|\n| 2024 | 1,234.5 |\n\nSource: [TEST 2024 10-K, Item 8]"
    assert run(md)["confirmed"] == 1


def test_a_citation_to_a_document_phase_1_never_read_is_flagged():
    r = run("Target $200 [2026-01-01 Firm note, p1].")
    assert r["bad_citations"] == ["2026-01-01 Firm note, p1"]


def test_only_an_exact_first_word_is_an_always_allowed_citation():
    # "Calcium Corp" is a real document label, not the skill's own arithmetic
    assert run("Target $200 [Calcium Corp, p1].")["bad_citations"] == ["Calcium Corp, p1"]
    assert run("Operating income rose by 290.0 [Calc, from drivers].")["confirmed"] == 1


def test_model_citation_is_checked_only_against_that_cell():
    assert run("Revenue was 500.0 [Model, MOD!H61].")["confirmed"] == 1
    assert run("Revenue was 700.0 [Model, MOD!H61].")["unconfirmed"]          # 700 lives in I61, not H61
    assert run("Revenue was 700.0 [Model, MOD!H61; Model, MOD!I61].")["confirmed"] == 1
    assert run("Revenue was 700.0 [Model, MOD!H61] [Model, MOD!I61].")["confirmed"] == 1


def test_model_citation_without_a_cell_is_a_bad_citation():
    r = run("Revenue was 500.0 [Model, series].")
    assert len(r["bad_citations"]) == 1 and "cite model numbers by cell, e.g. [Model, MOD!H61]" in r["bad_citations"][0]
    assert r["uncited"] == []                                                  # listed once, not twice


def test_calc_is_checked_only_against_driver_math_and_calculated_is_not_calc():
    assert run("Revenue was 500.0 (Calc).")["unconfirmed"]                    # 500 is a model number, not driver math
    assert run("Calculated 290.0 here.")["uncited"]


def test_small_number_far_from_any_anchor_is_weak_not_unconfirmed():
    far = {"Doc": "47 units shipped." + " filler" * 400 + " Revenue 1,234.5 million."}
    r = check_report("Revenue 1,234.5 million included 47 units [Doc, p1].", far, {}, [])
    assert r["confirmed"] == 1 and [w["number"] for w in r["weak"]] == ["47"] and r["unconfirmed"] == []
    near = {"Doc": "47 units shipped; revenue 1,234.5 million."}
    assert check_report("Revenue 1,234.5 million included 47 units [Doc, p1].", near, {}, [])["confirmed"] == 2
    # no anchor-sized number in the unit at all
    assert check_report("It shipped 47 units [Doc, p1].", near, {}, [])["weak"]


def test_signs_and_ranges():
    assert numbers("fell -99.9%")[0]["number"] == "99.9%"
    n = numbers("guidance of $4.60\u20134.625 billion")
    assert n[0]["suffix"] == "billion" and n[0]["value"] == 4.6
    assert numbers("4.6 to 4.7 billion")[0]["suffix"] == "billion"


def test_kpi_tiles_are_checked():
    ok = '<div class="kpi"><div class="v">12.3%</div><div class="l">growth [TEST 2024 10-K, Item 8]</div></div>'
    bad = ok.replace("12.3%", "64.0%")
    assert run(ok)["confirmed"] == 1 and run(bad)["unconfirmed"][0]["number"] == "64.0%"


def test_a_citation_after_the_period_stays_in_the_unit():
    r = run("Revenue grew 12.3%. [TEST 2024 10-K, Item 7]")
    assert r["confirmed"] == 1 and r["uncited"] == []


def test_numbers_that_are_names_are_skipped():
    assert numbers("a 30-day window, the 10-K, a 12-month view, on March 15 and Sep. 30") == []


def test_price_csv_citation_checks_the_close_on_that_date():
    px = [{"date": "2024-07-25", "close": "75.42", "spy": "540.1"}, {"date": "2024-07-26", "close": "80.00", "spy": "544.0"}]
    ok = check_report("It closed at $75.42 [price.csv, 2024-07-25].", {}, {}, [], px)
    assert ok["confirmed"] == 1 and ok["bad_citations"] == []
    # the close on another date is not the close on the cited date
    assert check_report("It closed at $80.00 [price.csv, 2024-07-25].", {}, {}, [], px)["unconfirmed"]
    assert check_report("It closed at $99.99 [price.csv, 2024-07-25].", {}, {}, [], px)["unconfirmed"]


def test_dates_are_not_numbers_but_negatives_are():
    assert [n["number"] for n in numbers("as of 2026-10-29 revenue was $5.2 billion")] == ["$5.2 billion"]
    assert [n["number"] for n in numbers("On October 29, 2026 and Oct 29 it fell -12.7%")] == ["12.7%"]


QSRC = {"Q 2024 10-K": "Management said it is \u201cfocused on durable growth\u201d and that we expect the\nmix shift to continue through the year. Pricing was stable."}


def runq(md):
    return check_report(md, QSRC, MODEL, POOL)


def test_a_quote_present_in_the_cited_source_passes():
    assert runq('Management is "focused on durable growth" [Q 2024 10-K, Item 7].')["bad_quotes"] == []


def test_a_quote_absent_from_the_cited_source_is_flagged():
    # a paraphrase in quotation marks reads as the company's own words
    r = runq('Management is "deeply committed to long term growth" [Q 2024 10-K, Item 7].')
    assert r["bad_quotes"][0]["quote"] == "deeply committed to long term growth"
    assert r["bad_quotes"][0]["line"] == 1


def test_curly_quotes_and_line_breaks_still_match():
    assert runq("It said \u201cthe mix shift to continue through the year\u201d [Q 2024 10-K, Item 7].")["bad_quotes"] == []


def test_a_three_word_quote_is_ignored():
    assert quotes('He said "not in source" here.') == []
    assert runq('He said "not in source" [Q 2024 10-K, Item 7].')["bad_quotes"] == []


def test_a_quote_with_an_ellipsis_matches_when_its_pieces_are_present():
    ok = runq('It said "focused on durable growth ... and that we expect the mix shift" [Q 2024 10-K, Item 7].')
    assert ok["bad_quotes"] == []
    bad = runq('It said "focused on durable growth ... and nothing else matters here" [Q 2024 10-K, Item 7].')
    assert len(bad["bad_quotes"]) == 1


def test_a_quote_cited_only_to_model_or_uncited_is_unsourced():
    r = runq('Mgmt called it "an entirely new growth engine" [Model, MOD!H61]. Also "an entirely new growth engine" here.')
    assert len(r["bad_quotes"]) == 2


PEER = {"2026 Q3 PEER call": "CFO: We haven't seen a degradation of pricing around the world. US revenue grew 14%."}


def test_a_citation_that_is_exactly_a_source_label_needs_no_locator():
    # A transcript has no pages, so agents cite it bare: '[2026 Q3 PEER call]'. Without a comma the checker used to
    # ignore the bracket, so every quote in the sentence was 'cites nothing' (three verbatim Dexcom quotes, ABT 2026-11-18).
    r = check_report('The CFO said "we haven\'t seen a degradation of pricing" and US grew 14% [2026 Q3 PEER call].', PEER, {}, [])
    assert r["bad_quotes"] == [] and r["unconfirmed"] == [] and r["uncited"] == []
    r = check_report('The CFO said "we haven\'t seen any erosion of pricing" [2026 Q3 PEER call].', PEER, {}, [])
    assert r["bad_quotes"][0]["cites"] == ["2026 Q3 PEER call"]


def test_editorial_brackets_are_still_not_citations():
    # only a bracket that IS a known label counts; "[s]" inside a quote never does
    r = check_report('The CEO said pricing "remain[s] under pressure in every market" [2026 Q3 PEER call].', PEER, {}, [])
    assert r["bad_citations"] == [] and [q["cites"] for q in r["bad_quotes"]] == [["2026 Q3 PEER call"]]
