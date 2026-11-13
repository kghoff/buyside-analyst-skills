import os

import p2numcheck
import p2preflight
from fixtures import SEMI, make_src


def setup(tmp_path):
    src = make_src(str(tmp_path))
    p2preflight.run("DXCM", src, "2026-11-09")
    d = os.path.join(src, "Street Research", "_work", "research", "r1")
    os.makedirs(d)
    open(os.path.join(d, "excerpts.md"), "w").write(
        "## https://ex.com/a\n\n\"Churn runs near 18% a year for type 2 users\" said the fund manager.\n")
    return src


def test_sources_cover_sellside_web_phase1_and_company_docs(tmp_path):
    src = setup(tmp_path)
    import json
    run = json.load(open(os.path.join(src, "Street Research", "_work", "run.json")))
    s = p2numcheck.build_sources(src, run)
    assert "https://ex.com/a" in s and "Filings research" in s and "DXCM 2025 10-K" in s
    assert any(";" not in k and "Modest 2027" in k for k in s)       # semicolon label made safe


def test_report_numbers_and_quotes_confirm_against_each_source_type(tmp_path):
    src = setup(tmp_path)
    md = ("JPM models 2027 gross margin of 63.5% [2026-10-29 JPM earnings recap - Good 3Q, p1]. "
          f"The formulary loss is under 4% of US revenue [{SEMI}, p1]. "
          "One investor puts churn near 18% [Fund X, 2026-09-01, https://ex.com/a]. "
          "Revenue per customer fell 6.4% [Filings research, §10.2]. "
          "Another says churn is 31% [Fund X, 2026-09-01, https://ex.com/a]. "
          "The user asked about renewals [User's notes, Q2].\n\n"
          "A fund manager said \"churn runs near 18% a year for type 2 users\" [Fund X, 2026-09-01, https://ex.com/a].\n")
    r = p2numcheck.run_check(src, md)
    assert r["bad_citations"] == []
    assert [u["number"] for u in r["unconfirmed"]] == ["31%"]   # the only number no cited source holds
    assert r["bad_quotes"] == [] and r["confirmed"] >= 1          # small numbers (4%, 6.4%) land in "weak", by design of the filings research


def test_late_sources_flagged(tmp_path):
    src = setup(tmp_path)
    md = "A view [Fund Y, 2026-12-01, https://ex.com/a]. Old [Fund Z, 2026-01-01, https://ex.com/a]."
    assert p2numcheck.late(md, "2026-11-09", []) == ["https://ex.com/a (dated 2026-12-01)"]


def test_bold_markers_in_sources_do_not_break_quotes(tmp_path):
    src = setup(tmp_path)
    d = os.path.join(src, "Street Research", "_work", "research", "r1")
    open(os.path.join(d, "excerpts.md"), "w").write("## https://ex.com/a\n\nThe manager who **told us** churn is rising said more.\n")
    md = "He said \"who told us churn is rising\" [Fund X, 2026-09-01, https://ex.com/a].\n"
    assert p2numcheck.run_check(src, md)["bad_quotes"] == []


def test_late_flags_page_published_after_as_of_even_if_citation_date_is_old(tmp_path):
    md = "A view [Fund Z, 2026-01-01, https://ex.com/a/]."
    pub = {"https://ex.com/a": "2026-12-01", "https://ex.com/b": ""}
    assert p2numcheck.late(md, "2026-11-09", [], pub) == ["https://ex.com/a (published 2026-12-01)"]
    assert p2numcheck.late(md, "2026-11-09", []) == []


def test_sellside_pages_checked_against_the_cited_page_only(tmp_path):
    label = "2026-10-29 JPM earnings recap - Good 3Q"
    two_pages = "# JPM\n\n## Page 1\n\nWe see US growth of 14%.\n\n## Page 2\n\nWe model 2027 gross margin of 63.5%.\n"
    src = make_src(str(tmp_path), sellside={label: two_pages})
    p2preflight.run("DXCM", src, "2026-11-09")
    import json
    run = json.load(open(os.path.join(src, "Street Research", "_work", "run.json")))
    s = p2numcheck.build_sources(src, run)
    assert "63.5%" in s[f"{label}, p2"] and "63.5%" not in s[f"{label}, p1"] and label in s
    wrong = p2numcheck.run_check(src, f"JPM models 2027 gross margin of 63.5% [{label}, p1].\n")
    assert [u["number"] for u in wrong["unconfirmed"]] == ["63.5%"]       # number is on page 2, not the cited page 1
    right = p2numcheck.run_check(src, f"JPM models 2027 gross margin of 63.5% [{label}, p2].\n")
    assert right["unconfirmed"] == [] and right["confirmed"] >= 1
    span = p2numcheck.run_check(src, f"JPM models 2027 gross margin of 63.5% [{label}, p1-2].\n")
    assert span["unconfirmed"] == []                                      # a page range falls back to the whole report


def test_out_flag_keeps_per_agent_results_apart(tmp_path):
    import subprocess, sys
    src = setup(tmp_path)
    w = os.path.join(src, "Street Research", "_work")
    notes = os.path.join(str(tmp_path), "notes.md")
    open(notes, "w").write("Revenue per customer fell 6.4% [Filings research, §10.2].\n")
    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "p2numcheck.py")
    out = os.path.join(w, "checks", "r1.numcheck.md")
    subprocess.run([sys.executable, script, "--src", src, "--report", notes, "--out", out], check=True, capture_output=True)
    assert os.path.exists(out) and os.path.exists(os.path.join(w, "checks", "r1.numcheck.json"))
    assert not os.path.exists(os.path.join(w, "numcheck.md"))           # default file untouched
