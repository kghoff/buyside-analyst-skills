"""The note is what the PM reads: a table of contents after the cover (house rule), the seven wrap items the chapter
lists, every call-summary quote with its file:line, every judgment call and yellow cell, and every number as the
recalculated tab shows it (a number retyped by hand can drift from the model). A missing PDF renderer leaves the
Markdown and says why. The slow tests read the session's one real recalculation; the fast ones a copy whose formula
cells hold build.py's expected values (no LibreOffice)."""
import json
import os
import re
import shutil
import sys

import openpyxl
import pytest

import build
import make_fixture as mf
import note

PLAN = os.path.join(os.path.dirname(__file__), "fixtures", "plan_example.json")
TRANSCRIPT_CITE = r"Earnings Calls/_md/2026 Q4 TEST call\.md:\d+"


def _section(md, n):
    return md.split(f"## {n} ", 1)[1].split("\n## ", 1)[0]


def _table_rows(text):
    """The first Markdown table in text: [cells] per body row."""
    lines = text.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith("| "))
    rows = []
    for ln in lines[i + 2:]:                                   # past the header and the |---| line
        if not ln.startswith("|"):
            break
        rows.append([c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", ln)[1:-1]])
    return rows


@pytest.fixture
def fake(model, fixture_research, tmp_path):
    """(work, values): a built copy whose checked formula cells hold build.py's expected values, plus a Q3 26
    column on Call Notes so the note has a previous quarter to compare with."""
    import context
    w = str(tmp_path / "w")
    os.makedirs(w)
    json.dump(mf.YAHOO, open(os.path.join(w, "yahoo_after.json"), "w"))
    context.run(model, w, "TEST", values=model, research=fixture_research, today="2027-02-28")
    shutil.copy(PLAN, os.path.join(w, "after_plan.json"))
    out = str(tmp_path / "out.xlsx")
    build.build(model, w, "TEST", out)
    lay = json.load(open(os.path.join(w, "layout.json")))
    wb = openpyxl.load_workbook(out)
    ws = wb["Earnings"]
    for ref, v in lay["expected"].items():
        ws[ref.replace("$", "")].value = "#N/A" if v is None else v
    cn = wb["Call Notes"]
    head = next(r for r in cn.iter_rows() if r[0].value == "Topic")[0].row
    cn.cell(head, 3, "Q3 26")
    tone = next(c.row for c in cn["A"] if c.value == "Tone")
    cn.cell(tone, 3, "Cautious on the launch.")
    vals = str(tmp_path / "values.xlsx")
    wb.save(vals)
    return w, vals


def _md(work, values, out_dir):
    return open(note.write_md(work, "TEST", str(out_dir), "2027-02-28", values)).read()


def test_fast_sections_wrap_and_changes_since_last_quarter(fake, tmp_path):
    w, vals = fake
    p = note.write_md(w, "TEST", str(tmp_path / "Earnings Reviews"), "2027-02-28", vals)
    assert os.path.basename(p) == "TEST Q4 26 after-print note 2027-02-28.md"
    md = open(p).read()
    assert md.index('<div class="cover">') < md.index("Contents") < md.index("## 1 Headline")
    for i, s in enumerate(note.SECTIONS, start=1):
        assert f"## {i} {s}" in md
    tone = md.split("### Tone", 1)[1].split("###", 1)[0]
    assert "Changed since last quarter: Q3 26 read: Cautious on the launch." in tone
    assert "new this quarter (nothing in Q3 26)" in md.split("### Capital allocation", 1)[1].split("###", 1)[0]
    assert "First quarter in Call Notes" not in md


def test_fast_placeholder_and_yellow_cells_listed(fake, tmp_path):
    """A call the user never hears about is the worst outcome: every yellow cell appears with its cell, and the
    model-update placeholder is marked, not given a beat / miss."""
    w, vals = fake
    md = _md(w, vals, tmp_path)
    lay = json.load(open(os.path.join(w, "layout.json")))
    j = _section(md, 7)
    for lab, ref in lay["inputs"].items():
        assert f"Earnings!{ref}" in j and lab in j, lab
    units = [r for r in _table_rows(_section(md, 2)) if r[0] == "KEY OPERATING METRICS | Units"][0]
    assert units[-1] == build.PLACEHOLDER
    assert "KEY OPERATING METRICS | Units: \"estimate, awaiting 10-Q\"" in _section(md, 6)


def test_pdf_null_with_the_reason_when_render_is_missing(fake, tmp_path, monkeypatch, capsys):
    w, vals = fake
    monkeypatch.setattr(note, "RENDER", str(tmp_path / "nowhere" / "render.py"))
    monkeypatch.setattr(sys, "argv", ["note.py", "--work", w, "--ticker", "test", "--out-dir", str(tmp_path / "o"),
                                      "--values", vals, "--date", "2027-02-28"])
    note.main()
    r = json.loads(capsys.readouterr().out)
    assert r["pdf"] is None and "render.py is not at" in r["pdf_skipped"] and os.path.exists(r["md"])


@pytest.mark.slow
def test_sections_and_wrap_items(recalc_run, tmp_path):
    md = _md(recalc_run["work"], recalc_run["verify"]["recalculated"], tmp_path)
    assert md.index("Contents") < md.index("## 1 ")
    for s in ("thoughts on the quarter", "estimates and the multiple", "catalyst path", "controversies",
              "updated guidance", "updated IRR", "updated risk/reward"):
        assert s.lower() in _section(md, 4).lower(), s
    assert re.search(r"\"[^\"]+\" \[" + TRANSCRIPT_CITE + r"\]", _section(md, 3))
    assert "First quarter in Call Notes" in md                     # the fixture model had no Call Notes before
    assert "## 7 Judgment calls" in md
    plan = json.load(open(PLAN))
    for c in plan["judgment_calls"]:
        assert c in _section(md, 7)


@pytest.mark.slow
def test_reaction_table_numbers_are_the_recalculated_cells(recalc_run, tmp_path):
    """Every number in section 2's table is the recalculated cell in its own format: Revenue +4% against the
    freeze is a beat, operating income -3% a miss."""
    vals = recalc_run["verify"]["recalculated"]
    md = _md(recalc_run["work"], vals, tmp_path)
    lay = recalc_run["layout"]
    ws = openpyxl.load_workbook(vals, data_only=True)["Earnings"]
    rows = _table_rows(_section(md, 2))
    assert rows
    checked = 0
    for r in rows:
        row = int(re.sub(r"\D", "", lay["refs"][r[0]]))
        for col, txt in zip("BCDEF", r[1:]):
            c = ws[f"{col}{row}"]
            if isinstance(c.value, (int, float)):
                assert txt == note.fmt(c), (r[0], col)
                checked += 1
    assert checked >= 15
    by = {r[0]: r for r in rows}
    assert by["INCOME STATEMENT | Revenue"][4:] == ["4.0%", "beat"]
    assert by["INCOME STATEMENT | Operating Income"][4:] == ["-3.0%", "miss"]


def test_fast_users_changes_and_unverified_are_named(fake, tmp_path):
    """The user's own yellow values are flagged as theirs, and an anchor that never held is named UNVERIFIED."""
    w, vals = fake
    p = os.path.join(w, "layout.json")
    lay = json.load(open(p))
    lay["users"] = ["React: the call"]
    json.dump(lay, open(p, "w"))
    json.dump(["sfot.tone"], open(os.path.join(w, "unverified.json"), "w"))
    j = _section(_md(w, vals, tmp_path), 7)
    assert "| React: the call | hold **You changed this.** |" in j
    assert "Your changes kept: React: the call." in j and "- UNVERIFIED: sfot.tone" in j
