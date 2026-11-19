import os, re, subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from render import join_sections, render, to_html


def test_html_inlines_images_and_styles_callouts(tmp_path):
    os.makedirs(tmp_path / "fig")
    plt.figure().savefig(tmp_path / "fig" / "a.png")
    html = to_html("## Hi\n\n> [!KEY] Three drivers.\n\n![x](fig/a.png)", str(tmp_path), "Footer")
    assert "data:image/png;base64," in html and 'class="callout key"' in html


def test_sections_join_in_file_name_order(tmp_path):
    d = tmp_path / "sections"
    d.mkdir()
    (d / "02-b.md").write_text("B")
    (d / "01-a.md").write_text("A")
    assert join_sections(str(d)) == "A\n\nB\n"


def test_pdf_has_the_footer_on_its_pages(tmp_path):
    # the user reads the PDF; the footer (ticker, phase, date) and page numbers must print
    md = tmp_path / "r.md"
    md.write_text("# Report\n\n## One\n\nText.\n\n## Two\n\nMore text.\n")
    out = render(str(md), str(tmp_path / "r.pdf"), "TEST filings research")
    text = subprocess.run(["pdftotext", out, "-"], capture_output=True, text=True).stdout
    assert "TEST filings research" in text and "Two" in text


def test_back_to_back_callouts_stay_separate(tmp_path):
    html = to_html("> [!KEY] One.\n\n> [!WATCH] Two.", str(tmp_path), "F")
    assert html.count('class="callout') == 2


def test_a_list_right_after_a_paragraph_still_renders_as_a_list(tmp_path):
    html = to_html("Para.\n- a\n- b", str(tmp_path), "F")
    assert "<ul>" in html and html.count("<li>") == 2


def test_a_list_inside_a_callout_stays_in_the_callout(tmp_path):
    html = to_html("> [!WATCH] Text\n> - a\n> - b", str(tmp_path), "F")
    assert 'class="callout watch"' in html and "<ul>" in html and html.count("<li>") == 2


def test_table_rows_starting_with_a_dash_are_untouched(tmp_path):
    html = to_html("| A | B |\n|---|---|\n| - | x |", str(tmp_path), "F")
    assert "<table>" in html and "<ul>" not in html


SECTIONS = "# Report\n\n## Alpha section\n\nText.\n\n### Beta part\n\nMore.\n\n## Gamma section\n\nText.\n\n## Delta section\n\nText.\n"


def _toc_numbers(pdf):
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"^\s*(\w+ (?:section|part))\s+(\d+)\s*$", text, re.M)}, text


def test_contents_lists_each_heading_with_the_page_it_is_on(tmp_path):
    # a contents page is only useful if its numbers are the real ones
    md = tmp_path / "r.md"
    md.write_text(SECTIONS)
    out = render(str(md), str(tmp_path / "r.pdf"), "F")
    nums, text = _toc_numbers(out)
    assert "Contents" in text
    # TOC is page 1; every h2 starts a page; Beta part shares Alpha's page
    assert nums == {"Alpha section": 2, "Beta part": 2, "Gamma section": 3, "Delta section": 4}


def test_contents_links_point_at_ids_that_exist(tmp_path):
    html = to_html(SECTIONS, str(tmp_path), "F", toc=True)
    hrefs = re.findall(r'href="#([^"]+)"', html)
    assert len(hrefs) == 4
    for h in hrefs:
        assert f'id="{h}"' in html


def test_contents_goes_after_the_cover(tmp_path):
    html = to_html('<div class="cover"><div class="band"><h1>T</h1></div></div>\n\n## One\n\nx\n', str(tmp_path), "F", toc=True)
    assert html.index('class="cover"') < html.index('class="toc"') < html.index("<h2")


def test_no_toc_omits_contents(tmp_path):
    assert 'class="toc"' not in to_html(SECTIONS, str(tmp_path), "F", toc=False)
    md = tmp_path / "r.md"
    md.write_text(SECTIONS)
    out = render(str(md), str(tmp_path / "r.pdf"), "F", toc=False)
    assert "Contents" not in subprocess.run(["pdftotext", out, "-"], capture_output=True, text=True).stdout


def test_an_indented_list_that_mentions_a_heading_is_not_its_page(tmp_path):
    # appendix intros list their sub-sections; the contents number must be the real heading's page
    md = tmp_path / "r.md"
    md.write_text("## Appendix\n\n- Alpha part\n- Beta part\n\n## Alpha part\n\nx\n\n## Beta part\n\ny\n")
    nums, _ = _toc_numbers(render(str(md), str(tmp_path / "r.pdf"), "F"))
    assert nums["Alpha part"] == 3 and nums["Beta part"] == 4


def test_citations_become_footnotes_colored_by_source(tmp_path):
    # the user reads company facts (blue) differently from our own math (orange); the full source text must survive
    html = to_html("Rev [DXCM 2025 10-K, Item 7 / Revenue]. GM [Calc, drivers_math Price vs volume]. "
                   "Px [price.csv, 2025-12-31]. ROIC [Model, MOD!BP285].", str(tmp_path), "F")
    assert '<span class="fn co">DXCM 2025 10-K, Item 7 / Revenue</span>' in html
    assert html.count('class="fn calc"') == 3 and "[" not in html.split("<body>")[1]


def test_outside_views_print_in_their_own_color(tmp_path):
    # the street research sets outside views against the company's record: a sell-side note, investor letter or web page must
    # never look like a company fact. Company labels never take the '<date> <name> ... - <title>' shape.
    sell = "2026-10-29 JPM earnings recap - Overall Good 3Q, p5"
    letter = "2025-09-30 Sands Capital fund letter - Select Growth Quarterly Report, p2"
    web = "Elise Reuter, 2026-11-02, https://www.medtechdive.com/news/abbott-dexcom/873461/"
    company = "2026-05-14 DXCM Investor Day, S68"
    html = to_html(f"A [{sell}]. B [{letter}]. C [{web}]. D [{company}]. E [Filings research, §10.2]. "
                   f"F [User's notes, p1]. G [Calc, drivers_math Price].", str(tmp_path), "F")
    assert html.count('class="fn ext"') == 3 and f'<span class="fn co">{company}</span>' in html
    assert html.count('class="fn co"') == 3 and html.count('class="fn calc"') == 1
    assert ".fn.ext::footnote-call" in html and ".fn.ext::footnote-marker" in html
    # an '&' in a firm name becomes '&amp;' in the HTML; its ';' must not hide the URL
    html = to_html("H [Bernstein Litowitz Berger & Grossmann LLP, undated, https://www.blbglaw.com/x]. "
                   "I [Filings research, §9.2; Elise Reuter, 2026-11-02, https://a.com/b].", str(tmp_path), "F")
    assert html.count('class="fn ext"') == 1 and html.count('class="fn co"') == 1


def test_unconfirmed_is_a_flag_not_a_footnote(tmp_path):
    html = to_html("about 62-63% [unconfirmed] for 2026", str(tmp_path), "F")
    assert '<span class="flag">unconfirmed</span>' in html and 'class="fn' not in html


def test_non_citation_brackets_are_untouched(tmp_path):
    # links, callout markers, code and editorial brackets in quotes are not sources
    html = to_html('> [!KEY] One.\n\nSee [the 10-K](https://sec.gov). Quote "move[s] to ketones". `a[0:3]`',
                   str(tmp_path), "F")
    assert 'class="fn' not in html and "move[s]" in html and "a[0:3]" in html and 'href="https://sec.gov"' in html


def test_a_long_multi_source_citation_is_still_one_footnote(tmp_path):
    cite = "; ".join(f"DXCM {y} 10-K, Item 7 / Results of Operations" for y in range(2016, 2026))
    assert len(cite) > 240
    html = to_html(f"Ten years [{cite}].", str(tmp_path), "F")
    assert html.count('class="fn co"') == 1 and cite in html


def test_pdf_footnotes_restart_each_section_and_leave_no_brackets(tmp_path):
    md = tmp_path / "r.md"
    md.write_text("## One\n\nA [DXCM 2025 10-K, Item 1]. B [Calc, drivers_math X].\n\n"
                  "## Two\n\nC [2026 Q3 DXCM call, CFO prepared].\n")
    text = subprocess.run(["pdftotext", render(str(md), str(tmp_path / "r.pdf"), "F", toc=False), "-"],
                          capture_output=True, text=True).stdout
    pages = text.split("\f")
    assert "[" not in text
    assert "1. DXCM 2025 10-K, Item 1" in pages[0] and "2. Calc, drivers_math X" in pages[0]
    assert "1. 2026 Q3 DXCM call, CFO prepared" in pages[1]


def test_a_misplaced_kpi_footnote_moves_the_tile_row_not_the_callout_above():
    # KPI tiles are divs, not paragraphs: marking the KEY callout's paragraph instead left an empty full-page callout
    from render import _keep_together
    html = to_html("## One\n\n> [!KEY]\n> Bottom line.\n\n<div class=\"kpis\"><div class=\"kpi\"><div class=\"v\">$1</div>"
                   "<div class=\"l\">Revenue [ABC 2025 10-K, Item 7]</div></div></div>\n", ".", "F")
    once = _keep_together(html, [0])
    body = once.split("<body", 1)[1]
    assert '<div class="kpis fnkeep">' in body and "fnkeep" not in body.split('<div class="kpis', 1)[0]
    # still misplaced after one pass: the tile row (not the callout) starts a new page
    assert '<div class="kpis fnbreak">' in _keep_together(once, [0])


def test_a_peer_document_label_prints_as_an_outside_view_when_listed(tmp_path):
    # A competitor's own call ('2026 Q3 PEER call') has a company-document shape; only the caller knows it is a peer,
    # so research-street passes its labels in. Without the list it stays blue, as before.
    md = "Peer US growth was 14% [2026 Q3 PEER call]. Ours [ABC 2025 10-K, Item 7]."
    assert '<span class="fn ext">2026 Q3 PEER call</span>' in to_html(md, str(tmp_path), "F", outside=["2026 Q3 PEER call"])
    html = to_html(md, str(tmp_path), "F")
    assert '<span class="fn co">2026 Q3 PEER call</span>' in html and '<span class="fn co">ABC 2025 10-K, Item 7</span>' in html
