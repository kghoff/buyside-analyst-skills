import json, os

import appendix
from p2common import FETCH_COLS, write_csv


def test_appendix_lists_sources_searches_blocked_and_ledger(tmp_path):
    src = str(tmp_path)
    w = os.path.join(src, "Street Research", "_work")
    os.makedirs(w)
    json.dump({"sellside": [{"label": "2026-10-29 JPM recap", "firm": "JPM", "type": "earnings recap", "date": "2026-10-29"}]},
              open(os.path.join(w, "run.json"), "w"))
    write_csv(os.path.join(w, "research", "r1", "fetched.csv"), FETCH_COLS, [
        {"url": "https://a.com/x", "fetched_on": "2026-11-09", "status": "ok", "title": "Bear | case", "published": "2026-09-01"},
        {"url": "https://pay.com/y", "fetched_on": "2026-11-09", "status": "blocked", "title": "Paywalled", "published": ""}])
    open(os.path.join(w, "research", "r1", "searches.txt"), "w").write("dexcom bear case\n\ndexcom churn\n")
    write_csv(os.path.join(w, "ledger_marked.csv"), ["id", "topic", "claim", "agrees", "differs", "adds", "gap-closed", "marks_summary"],
              [{"id": "D2-01", "topic": "driver2", "claim": "Price falls", "agrees": "1", "differs": "2", "adds": "0", "gap-closed": "0", "marks_summary": "differs"}])
    md = appendix.build(src)
    assert md.startswith("## 10 Appendix")
    assert "2026-10-29 JPM recap" in md and "https://a.com/x" in md and "Bear / case" in md   # | escaped for tables
    assert "dexcom churn" in md and "https://pay.com/y" in md and "D2-01" in md
    assert "### 10.3 Blocked or failed pages (1)" in md
    assert "| D2-01 | driver2 | Price falls | 1 | 2 | 0 | 0 | differs |" in md and "| Agrees | Differs | Adds | Gap closed |" in md


def test_empty_sections_say_none(tmp_path):
    src = str(tmp_path)
    w = os.path.join(src, "Street Research", "_work")
    os.makedirs(w)
    json.dump({"sellside": []}, open(os.path.join(w, "run.json"), "w"))
    md = appendix.build(src)
    assert md.count("None.") == 4 and "| Date |" not in md and "| Query |" not in md


def test_repeat_fetches_listed_once_and_ok_wins(tmp_path):
    src = str(tmp_path)
    w = os.path.join(src, "Street Research", "_work")
    os.makedirs(w)
    json.dump({"sellside": []}, open(os.path.join(w, "run.json"), "w"))
    row = {"url": "https://a.com/x", "fetched_on": "2026-11-09", "status": "ok", "title": "T", "published": "2026-09-01"}
    write_csv(os.path.join(w, "research", "r1", "fetched.csv"), FETCH_COLS,
              [row, dict(row, status="blocked"), dict(row, url="https://a.com/x/")])   # second fetch + retry
    md = appendix.build(src)
    assert "0 sell-side reports, 1 web pages" in md and "### 10.3 Blocked or failed pages (0)" in md


def test_brackets_in_page_titles_never_become_citations(tmp_path):
    # the PDF turns any [bracket text] into a footnote; a page title like "[Earnings Call] Abbott Q3" is not a source
    src = str(tmp_path)
    w = os.path.join(src, "Street Research", "_work")
    os.makedirs(w)
    json.dump({"sellside": []}, open(os.path.join(w, "run.json"), "w"))
    write_csv(os.path.join(w, "research", "r1", "fetched.csv"), FETCH_COLS, [
        {"url": "https://a.com/x", "fetched_on": "2026-11-09", "status": "ok", "title": "[Earnings Call] Abbott Q3",
         "published": "2026-10-22"}])
    md = appendix.build(src)
    assert "(Earnings Call) Abbott Q3" in md and "[Earnings Call]" not in md
