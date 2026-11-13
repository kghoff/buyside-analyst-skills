import os

import repeat_check
from fixtures import P1_REPORT, make_src

P1 = repeat_check.runs(repeat_check.words(P1_REPORT))


def test_paragraph_copied_from_phase1_is_flagged_even_with_new_citations():
    para = ("The company said the base grew in the mid-to-upper teens and that pricing is stabilising in the US "
            "market according to the chief financial officer on the third quarter call this year [Filings research, §10.1].")
    out = repeat_check.flagged(para, P1)
    assert len(out) == 1 and out[0]["share"] >= 0.5


def test_new_view_is_not_flagged_and_short_lines_ignored():
    para = ("J.P. Morgan argues the 2027 PBM rebate step-up will cut US revenue per customer by more than the company "
            "implies, because CVS Caremark moved Libre to preferred status and Aetna followed within the same quarter.")
    assert repeat_check.flagged(para, P1) == []
    assert repeat_check.flagged("## 03 Drivers\n\nShort line.", P1) == []


def test_main_counts_words_without_appendix(tmp_path):
    src = make_src(str(tmp_path))
    sec = os.path.join(src, "Street Research", "sections")
    os.makedirs(sec)
    open(os.path.join(sec, "03-drivers.md"), "w").write("word " * 100)
    open(os.path.join(sec, "10-appendix.md"), "w").write("word " * 5000)
    report = os.path.join(src, "Filings Research", "2026-11-08 DXCM Filings Research Report.md")
    res = repeat_check.check(sec, report)
    assert res["words"] == 100 and res["flagged"] == {}


P1_LONG = ("Management said on the call that the active customer base grew in the mid to upper teens during the year "
           "while pricing stabilised in the United States and gross margin guidance was lowered because of the new "
           "manufacturing lines coming online in Malaysia and Ireland over the next two years of heavy capital spending.")


def test_lightly_edited_copy_is_flagged_but_restated_table_column_is_not():
    p1 = repeat_check.runs(repeat_check.words(P1_LONG))
    ws = P1_LONG.split()
    edited = " ".join("zzz%d" % i if i % 12 == 11 else w for i, w in enumerate(ws))
    assert len(repeat_check.flagged(edited, p1)) == 1             # every 12th word changed still repeats the filings research
    table = ("| Topic | Company view | Outside view |\n|---|---|---|\n"
             f"| Pricing | {P1_LONG} | Brokers disagree and expect a much sharper decline next year because rebates "
             "rise and payers move share toward rivals in every channel they control today, while analysts at three other "
             "firms see volume holding up better than price, which would leave revenue per customer falling more slowly "
             "than the bears fear but still below the level the company implies in its long range plan |\n")
    assert repeat_check.flagged(table, p1) == []


def test_appendix_and_cover_are_never_checked(tmp_path):
    p1 = tmp_path / "p1.md"
    p1.write_text(P1_LONG)
    sec = tmp_path / "sections"
    sec.mkdir()
    (sec / "10-appendix.md").write_text(P1_LONG)
    (sec / "00-cover.md").write_text(P1_LONG)
    assert repeat_check.check(str(sec), str(p1)) == {"words": 0, "flagged": {}}
