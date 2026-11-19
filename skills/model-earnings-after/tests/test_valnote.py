"""The before side of band 13 is read from the last Valuation Note dated before the release (the user's choice:
no change to model-earnings-before). A layout the parser does not recognise gives '?', never a guess; and if
model-valuation stops writing the strings the parser relies on, test_formats_still_written fails here first."""
import os
import shutil

import pytest

import make_fixture as mf
import valnote

MV = os.path.join(os.path.dirname(__file__), "..", "..", "model-valuation", "scripts")


def test_latest_note_before_the_release(fixture_research, tmp_path):
    """A note written after the release already knows the print, so it cannot be the 'before' valuation."""
    root = str(tmp_path / "TEST")
    shutil.copytree(fixture_research, root)
    d = os.path.join(root, "Valuation")
    for name in ("2027-02-20 TEST Valuation Note.md", "2026-11-18 OTHER Valuation Note.md",
                 "2026-11-16 TEST Valuation Note.md"):
        with open(os.path.join(d, name), "w") as f:
            f.write("x")
    p = valnote.latest_before(root, "TEST", "2027-02-10")
    assert os.path.basename(p) == "2026-11-17 TEST Valuation Note.md"
    assert valnote.latest_before(root, "TEST", "2026-11-01") is None
    assert valnote.latest_before(str(tmp_path / "nowhere"), "TEST", "2027-02-10") is None


def test_parse_reads_every_label_with_its_line(fixture_research):
    """Every 'before' number cites the note's line, so the reader can check it against the note itself."""
    path = os.path.join(fixture_research, mf.VALNOTE)
    got = valnote.parse(path)
    lines = open(path).read().splitlines()
    assert got["problem"] is None and got["multiples"] == ["P/E"]
    for lab, (before, _) in mf.VALUATION.items():
        v = got["values"][lab]
        assert v["value"] == pytest.approx(before, abs=0.006), lab
        assert lab.split(" ")[0] in lines[v["line"] - 1], lab
    assert set(valnote.labels(got["multiples"])) <= set(got["values"])


def test_unknown_layout_gives_nothing_not_a_guess(tmp_path):
    """A note in some other layout must not be mined for numbers that look right: band 13 shows '?' instead."""
    p = tmp_path / "2026-01-01 X Valuation Note.md"
    p.write_text("# something else\n| IRR | 12% |\n")
    got = valnote.parse(str(p))
    assert got["values"] == {} and "layout" in got["problem"]


def test_after_reads_the_valuation_tab_by_label(fixture_model):
    """The after side links to the Valuation tab's cells, found by the same labels the note prints."""
    got = valnote.after(fixture_model)
    assert got["title"].startswith("TEST valuation")
    for lab, (_, after) in mf.VALUATION.items():
        c = got["cells"][lab]
        assert c["ref"].startswith("'Valuation'!$B$") and c["value"] == pytest.approx(after), lab


def test_formats_still_written():
    """If model-valuation changes its wording, this fails before a real note silently parses to '?'."""
    src = open(os.path.join(MV, "note.py")).read() + open(os.path.join(MV, "build.py")).read()
    for s in valnote.RELIED_ON:
        assert s in src, f"model-valuation no longer writes {s!r}: update valnote.py"
