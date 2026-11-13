import os

from conftest import FIX
import segments

MD = os.path.join(FIX, "seg_sample.md")


def test_cut_keeps_whole_tables_that_mention_the_segment_with_line_numbers(tmp_path):
    out = tmp_path / "s.md"
    n = segments.cut([MD], "Diabetes Care", str(out))
    txt = out.read_text()
    assert n == 2                                    # both segment tables, nothing else
    assert "L7: | Diabetes Care | 7,624 |" in txt
    assert "L8: | Nutritionals |" in txt             # whole table, so the reader can see the column headers
    assert "L5: | (in millions) | 2025 |" in txt


def test_check_accepts_printed_numbers_and_rejects_invented_ones():
    # the reader may only type numbers printed on the cited line; anything else stays out of the model
    good = {"line": "revenue", "fy": 2025, "value": 7624, "raw": "7,624", "scale": 1, "file": MD, "line_no": 7}
    bad = dict(good, raw="7,700", value=7700)
    calc = dict(good, line="oi", value=2450, raw="2,450", line_no=7)       # not on line 7
    assert segments.check_entry(good) is None
    assert "not printed" in segments.check_entry(bad)
    assert "not printed" in segments.check_entry(calc)
    assert "line" in segments.check_entry(dict(good, line="ebitda"))       # not a segment line


def test_choose_newest_document_and_store_costs_negative():
    a = {"line": "cogs", "fy": 2023, "value": 100, "file": "/x/ABT 2023 10-K.md"}
    b = {"line": "cogs", "fy": 2023, "value": 110, "file": "/x/ABT 2025 10-K.md"}
    v, conflict = segments.choose([a, b])
    assert v["value"] == -110 and conflict                 # recast figure wins; costs negative like MOD


def test_caption_stops_at_the_previous_table(tmp_path):
    # Two segment tables a blank line apart: the second one's "caption" must not repeat the first table's rows,
    # or the reader sees the same figures twice (once under the wrong caption).
    md = tmp_path / "ABT 2025 10-K.md"
    md.write_text("Net sales by segment\n\n| Segment | 2025 |\n| Diabetes Care | 7,624 |\n\n"
                  "| Segment | Op. earnings |\n| Diabetes Care | 2,450 |\n")
    out = tmp_path / "s.md"
    assert segments.cut([str(md)], "Diabetes Care", str(out)) == 2
    assert out.read_text().count("| Diabetes Care | 7,624 |") == 1
