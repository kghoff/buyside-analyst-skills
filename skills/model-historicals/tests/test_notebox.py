"""notebox: a note's box is drawn as wide as the visible part of the columns its anchor names. Notes on a year column
were anchored across a 2-wide spacer and grouped, hidden quarters, so they opened a few pixels wide and the user resized
each by hand. fix re-anchors only squashed boxes (never one the user sized), and every note-writing skill runs it."""
import os
import re
import sys
import zipfile

import openpyxl
from openpyxl.comments import Comment

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import notebox  # noqa: E402
from xlsx import comments_parts  # noqa: E402

# B = a year column, C = a 2-wide spacer, D-G = hidden quarters, H = the next year column (0-based: 1, 2, 3-6, 7)
SQUASHED = "2, 15, 4, 2, 6, 15, 9, 16"       # spacer + hidden quarters: 2 px on screen
USER_BOX = "7, 3, 6, 2, 10, 5, 12, 9"            # a box the user resized by hand: wide, must be left alone


def _model(tmp_path, name="m.xlsx"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    ws.column_dimensions["B"].width = 9
    ws.column_dimensions["C"].width = 2
    for c in "DEFG":
        ws.column_dimensions[c].width = 9
        ws.column_dimensions[c].hidden = True
    for c in "HIJK":
        ws.column_dimensions[c].width = 9
    ws["B5"].comment = Comment("source: 10-K", "Claude")
    ws["B7"].comment = Comment("the user's note", "the user")
    p = str(tmp_path / name)
    wb.save(p)
    with zipfile.ZipFile(p) as z:
        data = {i.filename: z.read(i.filename) for i in z.infolist()}
    vp = next(n for n in data if n.endswith(".vml"))
    anchors = iter([SQUASHED, USER_BOX])                 # the skills' own VML (openpyxl writes notes with no anchor)
    vml = comments_parts({"B5": "source: 10-K", "B7": "the user's note"}, 1)[1]
    data[vp] = re.sub(r"<x:Anchor>[^<]*</x:Anchor>", lambda m: f"<x:Anchor>{next(anchors)}</x:Anchor>", vml).encode()
    with zipfile.ZipFile(p, "w") as z:
        for n, b in data.items():
            z.writestr(n, b)
    return p, vp


def _anchors(p, vp):
    with zipfile.ZipFile(p) as z:
        return [[int(x) for x in a.replace(",", " ").split()]
                for a in re.findall(r"<x:Anchor>([^<]*)</x:Anchor>", z.read(vp).decode())]


def test_check_flags_only_the_squashed_box(tmp_path):
    p, _ = _model(tmp_path)
    bad = notebox.check(p)
    assert len(bad) == 1 and bad[0].startswith("MOD!B5")


def test_fix_reanchors_on_visible_columns_and_leaves_users_box(tmp_path):
    p, vp = _model(tmp_path)
    out = str(tmp_path / "o.xlsx")
    assert notebox.fix(p, out) == 1
    new, user_box = _anchors(out, vp)
    assert new[0] == 7                               # starts in the next year column, not the spacer or a hidden quarter
    assert new[2:4] == [4, 2]                        # same rows as before
    assert user_box == [int(x) for x in USER_BOX.replace(",", " ").split()]
    assert notebox.check(out) == []
    with zipfile.ZipFile(p) as a, zipfile.ZipFile(out) as b:   # only the drawing changed
        assert [n for n in a.namelist() if a.read(n) != b.read(n)] == [vp]


def test_fix_is_idempotent(tmp_path):
    p, _ = _model(tmp_path)
    notebox.fix(p, p)
    with open(p, "rb") as f:
        once = f.read()
    assert notebox.fix(p, p) == 0
    with open(p, "rb") as f:
        assert f.read() == once


def test_since_leaves_drawings_the_build_did_not_write(tmp_path):
    """A tab-only skill (DCF, Px tabs) must not touch other tabs' notes: its check proves nothing else changed."""
    p, _ = _model(tmp_path)
    assert notebox.fix(p, str(tmp_path / "o.xlsx"), since=p) == 0
