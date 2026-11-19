# tests/test_callnotes.py
"""Call Notes read across quarters (13.7: summaries side by side show how the story shifted): a new quarter goes in
at column B and older quarters move right untouched; a rerun rewrites only its own column and keeps cells the user
edited; a driver new this quarter shows '—' for the older quarters."""
import re
import zipfile

import openpyxl
import pytest

import callnotes as cn
import context
from tabkit import changed_parts, tab_parts
from xlsx import Package, Styles

TOPICS = ["Guidance (near-term)", "Driver: Units", "Tone"]


def test_new_quarter_goes_first_and_old_ones_stay():
    old = {"order": ["Q3 26"], "head": {"Q3 26": {"date": "2026-10-29", "file": "f3.md"}},
           "cells": {("Q3 26", "Guidance (near-term)"): "old guide", ("Q3 26", "Tone"): "calm"}, "topics": TOPICS[::2]}
    new = {"Guidance (near-term)": [{"text": "new guide", "anchor": "f4.md:3"}], "Driver: Units": [], "Tone": []}
    g, users = cn.merge(old, "Q4 26", {"date": "2027-02-10", "file": "f4.md"}, new, TOPICS, written=None)
    assert g["order"] == ["Q4 26", "Q3 26"]
    assert g["cells"][("Q3 26", "Tone")] == "calm"
    assert g["cells"][("Q3 26", "Driver: Units")] == "—"
    assert g["cells"][("Q4 26", "Guidance (near-term)")] == "new guide" and not users


def test_rerun_keeps_the_users_edit():
    written = {"Q4 26": {"Tone": "agent tone"}}
    old = {"order": ["Q4 26"], "head": {"Q4 26": {"date": "d", "file": "f"}},
           "cells": {("Q4 26", "Tone"): "my own words"}, "topics": ["Tone"]}
    new = {"Tone": [{"text": "agent tone 2", "anchor": "f.md:1"}]}
    g, users = cn.merge(old, "Q4 26", {"date": "d", "file": "f"}, new, ["Tone"], written)
    assert g["cells"][("Q4 26", "Tone")] == "my own words" and users == {("Q4 26", "Tone")}


def test_rerun_rewrites_a_cell_the_user_left_alone():
    """Our own text from the last build is ours to replace: the new agent text goes in."""
    written = {"Q4 26": {"Tone": "agent tone"}}
    old = {"order": ["Q4 26"], "head": {}, "cells": {("Q4 26", "Tone"): "agent tone"}, "topics": ["Tone"]}
    g, users = cn.merge(old, "Q4 26", {"date": "d", "file": "f"}, {"Tone": [{"text": "new", "anchor": "f.md:1"}]},
                        ["Tone"], written)
    assert g["cells"][("Q4 26", "Tone")] == "new" and not users


def test_a_topic_only_in_older_quarters_stays():
    """A driver dropped from this quarter's plan keeps its row: the older quarters' history is still worth reading."""
    old = {"order": ["Q3 26"], "head": {}, "cells": {("Q3 26", "Driver: Old"): "old driver"},
           "topics": ["Tone", "Driver: Old"]}
    g, users = cn.merge(old, "Q4 26", {"date": "d", "file": "f"}, {"Tone": []}, ["Tone"], None)
    assert g["topics"] == ["Tone", "Driver: Old"]
    assert g["cells"][("Q3 26", "Driver: Old")] == "old driver" and g["cells"][("Q4 26", "Driver: Old")] == ""


def test_no_record_a_differing_nonempty_cell_is_the_users():
    old = {"order": ["Q4 26"], "head": {}, "cells": {("Q4 26", "Tone"): "typed by me"}, "topics": ["Tone", "Driver: Units"]}
    new = {"Tone": [{"text": "agent", "anchor": "f.md:1"}], "Driver: Units": [{"text": "units", "anchor": "f.md:2"}]}
    g, users = cn.merge(old, "Q4 26", {"date": "d", "file": "f"}, new, ["Tone", "Driver: Units"], None)
    assert g["cells"][("Q4 26", "Tone")] == "typed by me" and users == {("Q4 26", "Tone")}
    assert g["cells"][("Q4 26", "Driver: Units")] == "units"      # empty cell: not the user's


def test_no_record_a_cell_equal_to_the_agents_is_not_the_users():
    old = {"order": ["Q4 26"], "head": {}, "cells": {("Q4 26", "Tone"): "agent"}, "topics": ["Tone"]}
    g, users = cn.merge(old, "Q4 26", {"date": "d", "file": "f"}, {"Tone": [{"text": "agent", "anchor": "f.md:1"}]},
                        ["Tone"], None)
    assert g["cells"][("Q4 26", "Tone")] == "agent" and not users


def test_a_users_cell_stays_the_users_on_the_next_rerun():
    """written() records a user's cell as None, so the run after next still keeps it (not compared as ours)."""
    old = {"order": ["Q4 26"], "head": {}, "cells": {("Q4 26", "Tone"): "mine"}, "topics": ["Tone"]}
    g, users = cn.merge(old, "Q4 26", {"date": "d", "file": "f"}, {"Tone": [{"text": "a", "anchor": "f.md:1"}]},
                        ["Tone"], {"Q4 26": {"Tone": "a"}})
    rec = cn.written(g, "Q4 26", users, {"Q3 26": {"Tone": "older"}})
    assert rec == {"Q3 26": {"Tone": "older"}, "Q4 26": {"Tone": None}}
    g2, users2 = cn.merge(g, "Q4 26", {"date": "d", "file": "f"}, {"Tone": [{"text": "b", "anchor": "f.md:1"}]},
                          ["Tone"], rec)
    assert g2["cells"][("Q4 26", "Tone")] == "mine" and users2 == {("Q4 26", "Tone")}


# ---------------------------------------------------------------- the tab in the workbook
NOTES = {"Guidance (near-term)": [{"text": "We expect $1.1 billion", "anchor": "call.md:12"},
                                  {"text": "the second half & more", "anchor": "call.md:40"}],
         "Driver: Units": [], "Tone": [{"text": "confident", "anchor": "call.md:7"}]}


def _write(src, out, grid, notes=NOTES):
    pkg = Package(src)
    st = Styles(pkg.text("xl/styles.xml"))
    part = cn.write(pkg, st, grid, notes, "TEST")
    pkg.put("xl/styles.xml", st.render())
    pkg.save(out)
    return part


def _grid(old=None, quarter="Q4 26"):
    old = old or {"order": [], "head": {}, "cells": {}, "topics": []}
    return cn.merge(old, quarter, {"date": "2027-02-10", "file": "TEST/Transcripts/call.md"}, NOTES, TOPICS, None)[0]


def test_write_puts_the_tab_after_earnings_and_touches_nothing_else(model, tmp_path):
    out = str(tmp_path / "o.xlsx")
    part = _write(model, out, _grid())
    names = [s[0] for s in Package(out).sheets()]
    assert names[names.index("Earnings") + 1] == cn.TAB
    assert changed_parts(model, out, tab_parts(Package(out), cn.TAB)) == []
    wb = openpyxl.load_workbook(out)
    ws = wb[cn.TAB]
    assert ws["A1"].value.startswith("TEST call notes") and ws["A4"].value == "Topic" and ws["B4"].value == "Q4 26"
    assert ws["B6"].value == "TEST/Transcripts/call.md" and ws["A8"].value == "Guidance (near-term)"
    assert ws["B8"].value == "We expect $1.1 billion • the second half & more"
    assert ws["B8"].comment.text == "call.md:12; call.md:40" and ws["B10"].comment.text == "call.md:7"
    assert ws["B9"].value is None and ws["B9"].comment is None
    assert ws.freeze_panes == "B8" and ws.column_dimensions["A"].width == 28 and ws.column_dimensions["B"].width == 60
    wb.close()
    assert part in tab_parts(Package(out), cn.TAB)


def test_a_second_write_replaces_the_tab(model, tmp_path):
    """No duplicate tab and no orphaned comments / VML: a rerun leaves exactly one set of the tab's parts."""
    first = str(tmp_path / "first.xlsx")
    _write(model, first, _grid())
    second = str(tmp_path / "second.xlsx")
    g = _grid(cn.read(first), "Q1 27")
    _write(first, second, g)
    pkg = Package(second)
    assert [s[0] for s in pkg.sheets()].count(cn.TAB) == 1
    z = zipfile.ZipFile(second)
    n0 = [n for n in zipfile.ZipFile(model).namelist() if re.search(r"comments\d+\.xml$|\.vml$", n)]
    n2 = [n for n in z.namelist() if re.search(r"comments\d+\.xml$|\.vml$", n)]
    assert len(n2) == len(n0) + 2
    ct = z.read("[Content_Types].xml").decode()
    assert all(f'PartName="/{n}"' in ct for n in n2 if n.endswith(".xml"))
    blocks = [b for n in n2 if n.endswith(".vml") for d in re.findall(rb'idmap[^>]*data="([\d,]+)"', z.read(n))
              for b in d.split(b",")]
    assert len(blocks) == len(set(blocks))
    wb = openpyxl.load_workbook(second)
    assert wb[cn.TAB]["B4"].value == "Q1 27" and wb[cn.TAB]["C4"].value == "Q4 26"
    assert wb[cn.TAB]["C9"].value is None and wb[cn.TAB]["C8"].comment.text == "call.md:12; call.md:40"
    wb.close()


def test_read_round_trips_and_history_is_newest_first(model, tmp_path):
    first = str(tmp_path / "first.xlsx")
    _write(model, first, _grid())
    g = cn.read(first)
    assert g["order"] == ["Q4 26"] and g["topics"] == TOPICS
    assert g["head"]["Q4 26"] == {"date": "2027-02-10", "file": "TEST/Transcripts/call.md"}
    assert g["cells"] == {("Q4 26", "Guidance (near-term)"): "We expect $1.1 billion • the second half & more",
                          ("Q4 26", "Tone"): "confident"}
    second = str(tmp_path / "second.xlsx")
    _write(first, second, _grid(g, "Q1 27"))
    h = context.history(second)
    assert [x["quarter"] for x in h] == ["Q1 27", "Q4 26"]
    assert h[1]["cells"]["Tone"] == "confident" and h[0]["head"]["file"] == "TEST/Transcripts/call.md"


def test_read_without_the_tab_is_empty(fixture_model):
    assert cn.read(fixture_model) == {"order": [], "head": {}, "cells": {}, "topics": [], "notes": {}, "dropped": []}


# ---------------------------------------------------------------- review fixes
def _edit(src, dst, fn):
    """A test copy edited the way a user would in Excel (openpyxl is fine on a test file, never on the user's)."""
    wb = openpyxl.load_workbook(src)
    fn(wb)
    wb.save(dst)
    return dst


def _first(model, tmp_path):
    a = str(tmp_path / "a.xlsx")
    _write(model, a, _grid())
    return a


def test_older_quarters_keep_their_notes_and_the_users_own(model, tmp_path):
    """The file:line notes are the audit trail of an older call; a user's comment on an older cell is theirs."""
    ed = _edit(_first(model, tmp_path), str(tmp_path / "b.xlsx"),
               lambda wb: setattr(wb[cn.TAB]["B10"], "comment", openpyxl.comments.Comment("my comment", "me")))
    out = str(tmp_path / "c.xlsx")
    _write(ed, out, _grid(cn.read(ed), "Q1 27"))
    ws = openpyxl.load_workbook(out)[cn.TAB]
    assert ws["C4"].value == "Q4 26" and ws["C8"].comment.text == "call.md:12; call.md:40"
    assert "my comment" in ws["C10"].comment.text


def test_a_users_edit_in_an_older_column_is_kept(model, tmp_path):
    ed = _edit(_first(model, tmp_path), str(tmp_path / "b.xlsx"), lambda wb: wb[cn.TAB].__setitem__("B10", "my words"))
    out = str(tmp_path / "c.xlsx")
    _write(ed, out, _grid(cn.read(ed), "Q1 27"))
    assert cn.read(out)["cells"][("Q4 26", "Tone")] == "my words"


def test_clean_strips_xml_invalid_characters_caps_and_normalises():
    assert cn.clean("a\x0bb\x00c\td\r\ne\rf￾") == "abc\td\ne\nf"
    t = cn.clean("x" * 40000)
    assert len(t) == cn.CAP and t.endswith(cn.CUT)
    from xlsx import esc
    assert esc("a\x0b<b") == "a&lt;b"


def test_bad_text_is_cleaned_before_it_is_written_or_recorded(model, tmp_path):
    """A control character would make the file unreadable; text over Excel's limit would be cut by Excel and then
    look like the user's edit on the rerun. What written() records equals what the tab reads back."""
    notes = {"Tone": [{"text": "a\x0bb\r\nc", "anchor": "f.md:1\x01"}],
             "Driver: Units": [{"text": "y" * 40000, "anchor": "f.md:2"}]}
    g, u = cn.merge(None, "Q4 26", {"date": "d", "file": "f"}, notes, TOPICS, None)
    rec = cn.written(g, "Q4 26", u)
    assert rec["Q4 26"]["Tone"] == "ab\nc" and len(rec["Q4 26"]["Driver: Units"]) == cn.CAP
    out = str(tmp_path / "o.xlsx")
    _write(model, out, g, notes)
    back = cn.read(out)
    assert back["cells"][("Q4 26", "Tone")] == "ab\nc" and back["notes"][("Q4 26", "Tone")] == "f.md:1"
    assert back["cells"][("Q4 26", "Driver: Units")] == rec["Q4 26"]["Driver: Units"]
    g2, u2 = cn.merge(back, "Q4 26", {"date": "d", "file": "f"}, notes, TOPICS, rec)
    assert not u2


def test_crlf_in_the_tab_is_not_taken_for_a_user_edit():
    old = {"order": ["Q4 26"], "head": {}, "cells": {("Q4 26", "Tone"): "a\r\nb"}, "topics": ["Tone"]}
    g, users = cn.merge(old, "Q4 26", {}, {"Tone": [{"text": "a\nb", "anchor": "f.md:1"}]}, ["Tone"],
                        {"Q4 26": {"Tone": "a\rb"}})
    assert not users and g["cells"][("Q4 26", "Tone")] == "a\nb"


def test_header_is_found_by_label_after_rows_are_inserted(model, tmp_path):
    ed = _edit(_first(model, tmp_path), str(tmp_path / "b.xlsx"), lambda wb: wb[cn.TAB].insert_rows(3, 2))
    g = cn.read(ed)
    assert g["order"] == ["Q4 26"] and g["topics"] == TOPICS and g["head"]["Q4 26"]["date"] == "2027-02-10"
    assert g["cells"][("Q4 26", "Tone")] == "confident"


def test_a_tab_without_its_header_stops_rather_than_lose_history(model, tmp_path):
    ed = _edit(_first(model, tmp_path), str(tmp_path / "b.xlsx"), lambda wb: wb[cn.TAB].__setitem__("A4", "Topics!"))
    with pytest.raises(SystemExit, match="header row is gone"):
        cn.read(ed)


def test_text_outside_the_grid_is_reported_as_dropped(model, tmp_path):
    """A column the user inserted with a blank header is not a quarter: the rebuild loses it, so the run says so."""
    def ins(wb):
        wb[cn.TAB].insert_cols(2)
        wb[cn.TAB]["B8"] = "my col"
    g = cn.read(_edit(_first(model, tmp_path), str(tmp_path / "b.xlsx"), ins))
    assert g["order"] == ["Q4 26"] and g["dropped"] == [{"ref": "B8", "text": "my col"}]


def test_a_rerun_of_an_older_quarter_keeps_its_column(model, tmp_path):
    """Only a new quarter goes to B; rerunning Q4 26 after Q1 27 exists rewrites column C, with its notes."""
    a, b = _first(model, tmp_path), str(tmp_path / "b.xlsx")
    _write(a, b, _grid(cn.read(a), "Q1 27"))
    g = _grid(cn.read(b), "Q4 26")
    assert g["order"] == ["Q1 27", "Q4 26"]
    out = str(tmp_path / "c.xlsx")
    _write(b, out, g)
    ws = openpyxl.load_workbook(out)[cn.TAB]
    assert ws["C4"].value == "Q4 26" and ws["C10"].comment.text == "call.md:7"


def test_a_retired_or_renamed_topic_is_listed():
    old = {"order": ["Q3 26"], "head": {}, "cells": {("Q3 26", "Mood"): "calm", ("Q3 26", "Tone"): "x"},
           "topics": ["Tone", "Mood"]}
    g, _ = cn.merge(old, "Q4 26", {}, {"Tone": []}, ["Tone"], None)
    assert g["renamed_or_retired"] == ["Mood"] and g["cells"][("Q3 26", "Mood")] == "calm"


def test_the_tab_goes_back_after_earnings_when_the_user_moved_it(model, tmp_path):
    """Each run puts the tab back right after Earnings, wherever the user dragged it."""
    ed = _edit(_first(model, tmp_path), str(tmp_path / "b.xlsx"),
               lambda wb: wb.move_sheet(cn.TAB, offset=-wb.sheetnames.index(cn.TAB)))
    assert [s[0] for s in Package(ed).sheets()][0] == cn.TAB
    out = str(tmp_path / "c.xlsx")
    _write(ed, out, _grid(cn.read(ed), "Q1 27"))
    names = [s[0] for s in Package(out).sheets()]
    assert names[names.index("Earnings") + 1] == cn.TAB and names.count(cn.TAB) == 1


def test_with_no_earnings_tab_it_goes_last(model, tmp_path):
    pkg = Package(model)
    pkg.remove_sheet("Earnings")
    src = str(tmp_path / "noearn.xlsx")
    pkg.save(src)
    out = str(tmp_path / "o.xlsx")
    _write(src, out, _grid())
    assert [s[0] for s in Package(out).sheets()][-1] == cn.TAB
    openpyxl.load_workbook(out).close()
