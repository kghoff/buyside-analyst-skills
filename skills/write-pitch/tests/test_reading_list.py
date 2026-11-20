# skills/write-pitch/tests/test_reading_list.py
import datetime
import os

import reading_list

FILES = [
    "R/Filings Research/2026-01-05 XYZ Filings Research Report.md",
    "R/Filings Research/2026-02-08 XYZ Filings Research Report (long version).md",
    "R/Filings Research/2026-02-09 XYZ Filings Research Report.md",
    "R/Filings Research/_work/drivers.md",
    "R/Street Research/2026-02-11 XYZ Street Research Report.md",
    "R/Street Research/_work/synthesis.md",
    "R/Street Research/_work/pm_review.md",
    "M/_model_work/forecast/forecast_writeup.md",
    "M/_model_work/model-valuation/valuation_plan.json",
    "M/_model_work/model-earnings-after/after_plan.json",
    "R/Valuation/2026-02-17 XYZ Valuation Note.md",
    "R/Valuation/2026-02-18 XYZ Valuation Note.md",
    "R/Short Check/XYZ short check 2026-02-18.md",
    "R/Pitch/_work/user_notes.md",
    "R/Pitch/_work/digest.md",
    "R/Pitch/_work/tabs/index.md",
]


def tree(tmp):
    for f in FILES:
        p = tmp / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    return str(tmp / "R"), str(tmp / "M"), str(tmp / "R" / "Pitch" / "_work")


def numbered(text):
    """The paths of the numbered list, in order."""
    return [ln.split("`")[1] for ln in text.splitlines() if ln[:1].isdigit()]


def age(path, days):
    t = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()
    os.utime(path, (t, t))


# why: the analyst reads in the spec's order (notes, reports, agent reasoning, notes, digest last), and only the
# newest report and note; reading an older valuation note would anchor the pitch on a superseded verdict
def test_order_and_newest(tmp_path):
    r, m, w = tree(tmp_path)
    paths = numbered(reading_list.build(r, m, w))
    assert all(os.path.isabs(p) for p in paths)
    names = [os.path.relpath(p, tmp_path) for p in paths]
    assert names == [
        "R/Pitch/_work/user_notes.md",
        "R/Filings Research/2026-02-09 XYZ Filings Research Report.md",
        "R/Street Research/2026-02-11 XYZ Street Research Report.md",
        "R/Filings Research/_work/drivers.md",
        "R/Street Research/_work/synthesis.md",
        "R/Street Research/_work/pm_review.md",
        "M/_model_work/forecast/forecast_writeup.md",
        "M/_model_work/model-valuation/valuation_plan.json",
        "M/_model_work/model-earnings-after/after_plan.json",
        "R/Valuation/2026-02-18 XYZ Valuation Note.md",
        "R/Short Check/XYZ short check 2026-02-18.md",
        "R/Pitch/_work/digest.md",
        "R/Pitch/_work/tabs/index.md",
    ]


# why: the long version is ~2x the tokens; the analyst reads the standard report and opens the long one only for
# sections it needs, so it must never be a numbered (must-read) item, but it must be named
def test_long_version_optional(tmp_path):
    r, m, w = tree(tmp_path)
    out = reading_list.build(r, m, w)
    assert not any("long version" in p for p in numbered(out))
    line = next(ln for ln in out.splitlines() if "2026-02-09 XYZ Filings Research Report.md" in ln)
    assert "(long version).md" in line and "optional" in line


# why: a missing optional input must be said, not silently skipped (the analyst notes it; the user hears it)
def test_missing_listed(tmp_path):
    r, m, w = tree(tmp_path)
    out = reading_list.build(r, m, w)
    miss = out[out.index("Missing (optional"):]
    for what in ("Filings research: the PM review", "Street research: the new views", "Short check plan",
                 "Earnings preview plan", "Earnings preview note", "Earnings review note"):
        assert what in miss, what
    assert "Valuation note" not in miss and "drivers" not in miss


# why: on a rerun the analyst reads the old plate and then only what changed, so a 300k-token reread is avoided;
# but the digest and tab pictures are rebuilt each run and must always be read
def test_since(tmp_path):
    r, m, w = tree(tmp_path)
    (tmp_path / "R/Pitch/_work/plate.md").write_text("old plate\n")
    for f in FILES:
        age(tmp_path / f, 30)
    age(tmp_path / "R/Pitch/_work/plate.md", 30)
    os.utime(tmp_path / "R/Valuation/2026-02-18 XYZ Valuation Note.md")          # changed today
    os.utime(tmp_path / "R/Pitch/_work/user_notes.md")
    since = datetime.date.today() - datetime.timedelta(days=10)
    out = reading_list.build(r, m, w, since)
    names = [os.path.relpath(p, tmp_path) for p in numbered(out)]
    assert names == ["R/Pitch/_work/plate.md", "R/Pitch/_work/user_notes.md",
                     "R/Valuation/2026-02-18 XYZ Valuation Note.md",
                     "R/Pitch/_work/digest.md", "R/Pitch/_work/tabs/index.md"]
    unchanged = out[out.index("Unchanged since"):out.index("Missing")]
    assert "Street Research Report.md" in unchanged and "forecast_writeup.md" in unchanged
    # without --since the plate is not on the list (first run: the plate is the analyst's to write)
    assert "plate.md" not in reading_list.build(r, m, w)


# why: an earlier pitch is a record of what was said to the PM on that day; a same-day rerun must add " (2)" to every
# file of the set (so the deck, core deck, sheet and Markdown still pair up) and never overwrite one. The names are bare:
# the skill builds into its build folder and only `mv -n` puts the files in Pitch/, so a path into Pitch/ would build there
def test_names_never_overwrite(tmp_path):
    import names
    first = names.names(tmp_path, "xyz", "2026-02-20")
    assert first["long"] == "2026-02-20 XYZ Pitch.pptx" and all(os.sep not in v for v in first.values())
    assert first["core"].endswith("2026-02-20 XYZ Pitch (core).pptx") and first["sheet"].endswith("Pitch Sheet.docx")
    (tmp_path / "2026-02-20 XYZ Pitch Sheet.pdf").write_text("x")          # any file of the set takes the suffix
    second = names.names(tmp_path, "XYZ", "2026-02-20")
    assert second == {"long": "2026-02-20 XYZ Pitch (2).pptx", "core": "2026-02-20 XYZ Pitch (core) (2).pptx",
                      "sheet": "2026-02-20 XYZ Pitch Sheet (2).docx", "md": "2026-02-20 XYZ Pitch (2).md"}
    (tmp_path / "2026-02-20 XYZ Pitch (core) (2).pptx").write_text("x")
    assert names.names(tmp_path, "XYZ", "2026-02-20")["long"].endswith("Pitch (3).pptx")
    assert names.names(tmp_path, "XYZ", "2026-02-21")["long"].endswith("2026-02-21 XYZ Pitch.pptx")
