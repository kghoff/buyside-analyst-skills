from p2cites import cited_urls, normalize, safe_label, web_dates

SEMI = "2026-10-21 JPM flash note - Shifts Favor Libre; Modest 2027 US Headwind"


def test_web_part_becomes_url_label():
    assert normalize("x [Jane Doe (JPM), 2026-08-14, https://ex.com/a?b=1] y") == "x [https://ex.com/a?b=1, web] y"


def test_mixed_citation_keeps_document_part_and_strips_trailing_punctuation():
    out = normalize("[DXCM 2025 10-K, Item 7; Bob, undated, https://x.org/p.]")
    assert out == "[DXCM 2025 10-K, Item 7; https://x.org/p, web]"


def test_semicolon_label_made_safe_so_phase1_split_keeps_it_whole():
    out = normalize(f"[{SEMI}, p1]", [SEMI])
    assert out == f"[{safe_label(SEMI)}, p1]" and ";" not in out


def test_markdown_links_untouched():
    assert normalize("see [the note](https://a.b/c)") == "see [the note](https://a.b/c)"


def test_cited_urls_and_dates():
    t = "[A, 2026-01-02, https://a.com/1]; text [B, undated, https://b.com/2; DXCM 2025 10-K, Item 1]"
    assert cited_urls(t) == {"https://a.com/1", "https://b.com/2"}
    assert web_dates(t) == [("2026-01-02", "https://a.com/1"), ("undated", "https://b.com/2")]


def test_parenthesis_url_survives_but_wrapping_paren_is_stripped():
    from p2cites import canon
    assert canon("https://en.wikipedia.org/wiki/Dexcom_(company)") == "https://en.wikipedia.org/wiki/Dexcom_(company)"
    assert canon("https://x.org/a).") == "https://x.org/a"
    assert canon("https://x.org/a/") == "https://x.org/a"
    assert normalize("[A, undated, https://en.wikipedia.org/wiki/Dexcom_(company)]") == \
        "[https://en.wikipedia.org/wiki/Dexcom_(company), web]"
    assert cited_urls("[A, undated, https://x.org/a/]") == {"https://x.org/a"}
