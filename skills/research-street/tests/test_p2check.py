import json, os

import p2check
import p2preflight
from fixtures import SEMI, SELLSIDE, make_src
from p2common import LEDGER_COLS, MARK_COLS, write_csv

LEDGER = [
    {"id": "D2-01", "topic": "driver2", "claim": "Revenue per customer keeps falling, by less each year",
     "phase1_cite": "DXCM 2025 10-K, Item 7", "phase1_section": "10.2"},
    {"id": "G1", "topic": "gap", "claim": "What is the quarterly base?", "phase1_cite": "", "phase1_section": "15"},
    {"id": "G2", "topic": "gap", "claim": "Churn?", "phase1_cite": "", "phase1_section": "15"},
    {"id": "G3", "topic": "gap", "claim": "Price per sensor?", "phase1_cite": "", "phase1_section": "15"},
]
NOTES = ("Analysts differ on pricing. " * 200) + " ".join(f"[{SEMI}, p1]" for _ in range(6))


def mark(**kw):
    row = {"claim_id": "D2-01", "stance": "differs", "view": "Pricing pressure grows in 2027",
           "reasoning": "PBM rebates step up", "holder": "J.P. Morgan, Robbie Marcus", "holder_type": "sell-side",
           "tier": "", "date": "2026-10-21", "source": f"{SEMI}, p1"}
    row.update(kw)
    return row


def setup(tmp_path):
    src = make_src(str(tmp_path))
    p2preflight.run("DXCM", src, "2026-11-09")
    w = os.path.join(src, "Street Research", "_work")
    write_csv(os.path.join(w, "ledger.csv"), LEDGER_COLS, LEDGER)
    json.dump([{"n": 1}, {"n": 2}, {"n": 3}], open(os.path.join(w, "gaps.json"), "w"))
    return src, w


def write_reader(w, gid, labels, marks, notes=NOTES):
    d = os.path.join(w, "readers", gid)
    os.makedirs(d, exist_ok=True)
    write_csv(os.path.join(d, "marks.csv"), MARK_COLS, marks)
    open(os.path.join(d, "notes.md"), "w").write(notes)
    open(os.path.join(d, "files_read.txt"), "w").write("\n".join(labels) + "\n")


def test_ledger_needs_a_row_per_gap(tmp_path):
    src, w = setup(tmp_path)
    assert p2check.check_ledger(src) == []
    write_csv(os.path.join(w, "ledger.csv"), LEDGER_COLS, LEDGER[:2])
    assert any("gap 2" in p for p in p2check.check_ledger(src))


def test_reader_passes_and_semicolon_label_is_one_citation(tmp_path):
    src, w = setup(tmp_path)
    run = json.load(open(os.path.join(w, "run.json")))
    g = run["groups"][0]
    assert SEMI in g["labels"]                    # all three fixture reports fit in one group
    write_reader(w, g["id"], g["labels"], [mark()])
    assert p2check.check(src, g["id"]) == []


def test_reader_problems_are_specific(tmp_path):
    src, w = setup(tmp_path)
    g = json.load(open(os.path.join(w, "run.json")))["groups"][0]
    bad = [mark(claim_id="X9"), mark(stance="maybe"), mark(claim_id="D2-01", stance="gap-closed"),
           mark(date="Oct 2026"), mark(reasoning=""), mark(source="Some Other Report, p2")]
    write_reader(w, g["id"], g["labels"][:-1], bad, notes="short")
    probs = "\n".join(p2check.check(src, g["id"]))
    for needle in ("X9", "stance", "gap-closed only", "date", "reasoning", "Some Other Report",
                   "not in files_read", "words"):
        assert needle in probs, needle


def write_researcher(w, rid, fetched, excerpts, marks, notes):
    d = os.path.join(w, "research", rid)
    os.makedirs(d, exist_ok=True)
    write_csv(os.path.join(d, "fetched.csv"), ["url", "fetched_on", "status", "title", "published"], fetched)
    open(os.path.join(d, "excerpts.md"), "w").write(excerpts)
    write_csv(os.path.join(d, "marks.csv"), MARK_COLS, marks)
    open(os.path.join(d, "notes.md"), "w").write(notes)
    open(os.path.join(d, "searches.txt"), "w").write("dexcom pricing bear case\n")


def test_researcher_web_citations_must_be_fetched_and_excerpted(tmp_path):
    src, w = setup(tmp_path)
    json.dump([{"id": "r1", "title": "Driver 2", "ledger_ids": ["D2-01"]}], open(os.path.join(w, "researchers.json"), "w"))
    ok = {"url": "https://ex.com/a", "fetched_on": "2026-11-09", "status": "ok", "title": "A", "published": "2026-09-01"}
    blocked = dict(ok, url="https://pay.com/b", status="blocked")
    good = mark(source="Jane Doe, 2026-09-01, https://ex.com/a", holder_type="independent")
    notes = ("Bears argue pricing. " * 300) + " ".join("[Jane Doe, 2026-09-01, https://ex.com/a]" for _ in range(6))
    write_researcher(w, "r1", [ok, blocked], "## https://ex.com/a\n\n\"PBM rebates step up\"\n", [good], notes)
    assert p2check.check(src, "r1") == []
    write_researcher(w, "r1", [ok, blocked], "## https://ex.com/a\n\nx\n## https://made.up/c\n\ny\n",
                     [good, mark(source="X, 2026-01-01, https://pay.com/b")], notes + " [Y, undated, https://ex.com/zz]")
    probs = "\n".join(p2check.check(src, "r1"))
    assert "https://pay.com/b" in probs           # blocked page cited
    assert "https://ex.com/zz" in probs           # never fetched
    assert "https://made.up/c" in probs           # excerpt for a page that was not fetched ok


def test_status_lists_todo_and_pass(tmp_path):
    src, w = setup(tmp_path)
    json.dump([{"id": "r1", "title": "x", "ledger_ids": []}], open(os.path.join(w, "researchers.json"), "w"))
    st = p2check.status(src)
    assert set(st.values()) == {"todo"} and "r1" in st and "s1" in st


def _researcher_case(tmp_path, url, cite_url, source=None, notes_cite=None, excerpt_url=None):
    src, w = setup(tmp_path)
    ok = {"url": url, "fetched_on": "2026-11-09", "status": "ok", "title": "A", "published": "2026-09-01"}
    c = notes_cite or f"[Jane Doe, 2026-09-01, {cite_url}]"
    notes = ("Bears argue pricing. " * 300) + " ".join(c for _ in range(6))
    write_researcher(w, "r1", [ok], f"## {excerpt_url or url}\n\nx\n",
                     [mark(source=source or f"Jane Doe, 2026-09-01, {cite_url}", holder_type="independent")], notes)
    return p2check.check(src, "r1")


def test_trailing_slash_and_parenthesis_urls_match(tmp_path):
    assert _researcher_case(tmp_path / "a", "https://ex.com/a/", "https://ex.com/a") == []
    assert _researcher_case(tmp_path / "b", "https://ex.com/a", "https://ex.com/a/", excerpt_url="https://ex.com/a/") == []
    u = "https://en.wikipedia.org/wiki/Dexcom_(company)"
    assert _researcher_case(tmp_path / "c", u, u) == []


def test_web_citation_needs_author_date_url(tmp_path):
    probs = "\n".join(_researcher_case(tmp_path / "a", "https://ex.com/a", "https://ex.com/a",
                                       source="Blog, https://ex.com/a", notes_cite="[https://ex.com/a]"))
    assert probs.count("web citation needs") >= 2 and "marks.csv line 2" in probs and "notes.md" in probs
    assert "web citation needs" in "\n".join(_researcher_case(tmp_path / "b", "https://ex.com/a", "https://ex.com/a",
                                                              notes_cite="[Blog, https://ex.com/a]"))


def test_unknown_reader_group_is_a_plain_problem(tmp_path):
    src, w = setup(tmp_path)
    write_reader(w, "s9", [], [mark()])
    assert p2check.check(src, "s9") == ["no reader group s9 in run.json"]
