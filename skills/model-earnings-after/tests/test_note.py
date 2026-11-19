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


def test_fast_vs_consensus_from_the_grid(fake, tmp_path):
    """The print against the Street as it stood before the print: the grid's consensus cell, and actual / consensus
    - 1 from the two cells; a line the grid has no consensus for says n/a, never 0%."""
    w, vals = fake
    md = _md(w, vals, tmp_path)
    s2 = _section(md, 2)
    rows = {r[0]: r for r in _table_rows(s2)}
    wb = openpyxl.load_workbook(vals)
    ws = wb["Earnings"]
    lay = json.load(open(os.path.join(w, "layout.json")))
    ctx = json.load(open(os.path.join(w, "context.json")))
    for lab, grid in (("INCOME STATEMENT | Revenue", "Revenue"), ("INCOME STATEMENT | EPS, diluted", "EPS")):
        ref = next(r["q_ref"] for r in ctx["consensus"]["rows"] if r["label"] == grid).split("!")[1].replace("$", "")
        cons = ws[ref]
        act = ws[f"C{re.sub(r'[^0-9]', '', lay['refs'][lab])}"].value
        assert rows[lab][6] == note.fmt(cons)
        assert rows[lab][7] == f"{(act / cons.value - 1) * 100:.1f}%"
    assert rows["INCOME STATEMENT | Gross Profit"][6:] == ["n/a", "n/a"]
    assert "Consensus is as typed into the grid before the print (Earnings tab band 6: Consensus tab mean row " \
           "(Yahoo snapshot 2026-11-01)); a /model-consensus rerun after the print can change it." in s2


def test_fast_no_consensus_in_the_grid(fake, tmp_path):
    w, vals = fake
    p = os.path.join(w, "context.json")
    ctx = json.load(open(p))
    ctx["consensus"] = {"where": None, "rows": [], "source": None}
    json.dump(ctx, open(p, "w"))
    s2 = _section(_md(w, vals, tmp_path), 2)
    assert "No consensus numbers in the variance grid." in s2 and "Consensus is as typed" not in s2
    assert all(r[6:] == ["n/a", "n/a"] for r in _table_rows(s2))


class _C:
    def __init__(self, v, f):
        self.value, self.number_format = v, f


def test_fmt_uses_the_formats_own_decimals():
    """A number reads as the tab shows it: 43.98 in a 0.0 cell is 44.0 on screen, so the note says 44.0."""
    assert note.fmt(_C(43.98, "0.0")) == "44.0"
    assert note.fmt(_C(43.98, "0.00")) == "43.98"
    assert note.fmt(_C(1234.56, "#,##0")) == "1,235"
    assert note.fmt(_C(1234.56, "#,##0.0")) == "1,234.6"
    assert note.fmt(_C(3, "0")) == "3"


def _call_notes_heads(vals, heads, tone):
    """Rewrite the copy's Call Notes header row and Tone row: heads / tone texts from column B on."""
    wb = openpyxl.load_workbook(vals)
    cn = wb["Call Notes"]
    h = next(r for r in cn.iter_rows() if r[0].value == "Topic")[0].row
    t = next(c.row for c in cn["A"] if c.value == "Tone")
    for j in range(2, 8):
        cn.cell(h, j).value = cn.cell(t, j).value = None
    for j, (q, x) in enumerate(zip(heads, tone), start=2):
        cn.cell(h, j, q)
        cn.cell(t, j, x)
    wb.save(vals)


def test_previous_quarter_is_the_column_right_after_ours(fake, tmp_path):
    """The user may keep a newer column left of this quarter: the previous quarter is still the one right after
    ours, and 'First quarter' only shows when no other quarter is on the tab."""
    w, vals = fake
    _call_notes_heads(vals, ["Q1 27", "Q4 26", "Q3 26"], ["newer", "now", "Cautious on the launch."])
    tone = _md(w, vals, tmp_path).split("### Tone", 1)[1].split("###", 1)[0]
    assert "Changed since last quarter: Q3 26 read: Cautious on the launch." in tone
    _call_notes_heads(vals, ["Q1 27", "Q4 26"], ["newer", "now"])
    md = _md(w, vals, tmp_path)
    assert "No older quarter after Q4 26" in md and "First quarter in Call Notes" not in md
    _call_notes_heads(vals, ["Q4 26"], ["now"])
    assert "First quarter in Call Notes." in _md(w, vals, tmp_path)


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
    assert units[5] == build.PLACEHOLDER
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
    assert by["INCOME STATEMENT | Revenue"][4:6] == ["4.0%", "beat"]
    assert by["INCOME STATEMENT | Operating Income"][4:6] == ["-3.0%", "miss"]


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


def _weasyprint_loads():
    """(True, '') or (False, why): render.py runs WeasyPrint with the Homebrew library path, so try the same."""
    import subprocess
    env = dict(os.environ)
    env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(filter(None, [env.get("DYLD_FALLBACK_LIBRARY_PATH"),
                                                               "/opt/homebrew/lib", "/usr/local/lib"]))
    r = subprocess.run([sys.executable, "-c", "import weasyprint"], capture_output=True, text=True, env=env)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]


@pytest.mark.slow
def test_pdf_is_made_when_render_works(recalc_run, tmp_path):
    """The PM reads the PDF: when WeasyPrint is there, render makes it and its first page carries the ticker."""
    ok, why = _weasyprint_loads()
    if not ok or not os.path.exists(note.RENDER):
        pytest.skip(f"WeasyPrint cannot load ({why}) or render.py is missing: the PDF cannot be made here")
    md = note.write_md(recalc_run["work"], "TEST", str(tmp_path), "2027-02-28", recalc_run["verify"]["recalculated"])
    pdf, reason = note.render(md, md[:-3] + ".pdf", "TEST after-print note · 2027-02-28")
    assert reason is None and pdf and os.path.exists(pdf)
    import fitz
    assert "TEST" in fitz.open(pdf)[0].get_text()
    assert not os.path.exists(md[:-3] + ".render.md")             # the temporary copy without the contents list
