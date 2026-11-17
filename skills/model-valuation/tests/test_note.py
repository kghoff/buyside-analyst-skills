# tests/test_note.py
"""The note says every judgment call (CLAUDE.md: a call the user never hears about is the worst outcome) and lists
what the brief cut; numbers come from the recalculated tab."""
import json
import os
import subprocess
import sys

import fitz
import openpyxl
import pytest

import build
import note
import verify
from test_build import work  # noqa: F401


@pytest.fixture
def noted(model, work, tmp_path):  # noqa: F811
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    r = verify.run(model, out, work)
    return work, r["recalculated"]


def test_note_has_sections_and_calls(noted):
    work, values = noted
    md = note.write_md(work, "TEST", values, "2026-11-17")
    for h in ("## 1 The recommendation", "## 4 The DCF scenarios", "## 7 Judgment calls", "## 8 What the brief cut"):
        assert h in md
    plan = json.load(open(os.path.join(work, "valuation_plan.json")))
    for n in plan["notes"]:
        assert n in md
    for rd in plan["scenarios"]["rounds"]:
        assert rd["why"] in md
    # the fixed calls and the brief's missing sections are told, not left for the user to guess
    assert "first four forecast quarters" in md and "25%" in md
    ctx = json.load(open(os.path.join(work, "context.json")))
    for m in ctx["brief"]["missing"]:
        assert m in md


def test_numbers_come_from_the_recalculated_tab(noted, tmp_path):
    """Change the blended reward price in the recalculated file: the note must follow it, so nothing is retyped."""
    work, values = noted
    ref = json.load(open(os.path.join(work, "layout.json")))["ref"]["blended_reward"].replace("$", "")
    bent = str(tmp_path / "bent.xlsx")
    wb = openpyxl.load_workbook(values, data_only=True)  # a test copy, never the user's file
    wb["Valuation"][ref] = 123.45
    wb.save(bent)
    assert "$123.45" not in note.write_md(work, "TEST", values, "2026-11-17")
    assert "$123.45" in note.write_md(work, "TEST", bent, "2026-11-17")


def test_user_override_shows_agent_and_user_value(noted):
    """A cell the user changed is the user's; the note must say what the agent suggested and what the user kept."""
    work, values = noted
    p = os.path.join(work, "inputs_written.next.json")
    rec = json.load(open(p))
    rec["hurdle"] = {"value": 0.15, "user": True}
    json.dump(rec, open(p, "w"))
    md = note.write_md(work, "TEST", values, "2026-11-17")
    assert "IRR hurdle: agent 20.0% → yours 15.0%" in md


def _weasyprint_works():
    env = dict(os.environ, DYLD_FALLBACK_LIBRARY_PATH=":".join(["/opt/homebrew/lib", "/usr/local/lib"]))
    return subprocess.run([sys.executable, "-c", "import weasyprint"], env=env, capture_output=True).returncode == 0


def test_main_writes_md_and_pdf_with_contents(noted, tmp_path):
    """CLAUDE.md: every report or PDF has a table of contents after the cover. Without WeasyPrint the MD is still
    written and the PDF is reported as skipped with a reason (never silently)."""
    work, values = noted
    od = tmp_path / "Valuation"
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(note.__file__), "note.py"), "--work", work,
                        "--ticker", "TEST", "--out-dir", str(od), "--values", values, "--date", "2026-11-17"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)
    assert os.path.exists(od / "2026-11-17 TEST Valuation Note.md")
    if _weasyprint_works():
        assert res["pdf"] == str(od / "2026-11-17 TEST Valuation Note.pdf")
        doc = fitz.open(res["pdf"])
        assert "Contents" in "".join(doc[i].get_text() for i in range(min(3, len(doc))))
    else:
        assert res["pdf"] is None and res["pdf_skipped"]


def test_pdf_null_when_render_fails(noted, tmp_path, monkeypatch):
    """A failed PDF is reported with its reason and the MD still stands."""
    work, values = noted
    monkeypatch.setattr(note, "RENDER", str(tmp_path / "no_such_render.py"))
    res = note.main(["--work", work, "--ticker", "TEST", "--out-dir", str(tmp_path / "V"), "--values", values,
                     "--date", "2026-11-17"])
    assert res["pdf"] is None and res["pdf_skipped"]
    assert os.path.exists(res["md"])


def test_gap_flag_carries_the_agents_explanation(noted, tmp_path):
    """A DCF case more than 25% from its multiple target must come with the agent's reason, or a loud warning."""
    work, values = noted
    wb = openpyxl.load_workbook(values, data_only=True)   # keep the recalculated values, not the formulas
    ws = wb["Valuation"]
    r = next(c.row for (c,) in ws.iter_rows(min_col=1, max_col=1) if c.value == "DCF vs multiple target")
    ws[f"B{r}"] = "gap > 25%: see note"
    bent = str(tmp_path / "gap.xlsx")
    wb.save(bent)
    md = note.write_md(work, "TEST", bent, "2026-11-17")
    assert "no gap flags" not in md and "**Bear**:" in md and "no explanation for this gap" in md
    p = os.path.join(work, "valuation_plan.json")
    plan = json.load(open(p))
    plan["notes"].append("The bear DCF sits far below the risk price because the WACC rises to 9%.")
    json.dump(plan, open(p, "w"))
    md = note.write_md(work, "TEST", bent, "2026-11-17")
    assert "**Bear**: -7.7% from its target. The bear DCF sits far below" in md
