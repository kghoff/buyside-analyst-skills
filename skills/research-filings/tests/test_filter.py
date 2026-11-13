import os
import subprocess
import sys

from fixtures import make_src
from filter import History, blocks, filter_doc, run
from inventory import build
from common import save, work_dir

RISK = "We depend on a single supplier for our sensors and any disruption could hurt our revenue and margins."
RISK2 = "We depend on two suppliers for our sensors and any disruption could hurt our revenue and margins badly."
NEW = "In 2025 we opened a new plant in Malaysia that doubles our sensor capacity over the next three years."
TABLE = "| Item | 2024 |\n|---|---|\n| Revenue | 100 |"


def test_exact_repeat_is_dropped_with_a_marker_naming_the_earlier_filing():
    h = History()
    filter_doc(RISK, h, "TEST 2023 10-K", near=True)
    out, st = filter_doc(RISK, h, "TEST 2024 10-K", near=True)
    assert RISK not in out and "unchanged since TEST 2023 10-K" in out
    assert st["dropped"] == 1


def test_reworded_paragraph_is_kept_with_the_changed_words_marked():
    # reworded risk factors are exactly what an analyst must not miss
    h = History()
    filter_doc(RISK, h, "TEST 2023 10-K", near=True)
    small = RISK.replace("a single supplier", "two suppliers")  # a small edit, so a compact diff
    out, st = filter_doc(small, h, "TEST 2024 10-K", near=True)
    assert "changed since TEST 2023 10-K" in out
    assert "~~[- a single supplier -]~~" in out or "~~[- a single -]~~" in out
    assert "**[+" in out and "two" in out
    assert st["changed"] == 1


def test_new_paragraphs_and_all_tables_are_kept_in_full():
    h = History()
    filter_doc(TABLE + "\n\n" + RISK, h, "A", near=True)
    out, _ = filter_doc(TABLE + "\n\n" + NEW, h, "B", near=True)
    assert TABLE in out and NEW in out


def test_first_document_of_a_group_is_kept_whole():
    out, st = filter_doc(RISK + "\n\n" + NEW, History(), "A", near=True)
    assert RISK in out and NEW in out and st["dropped"] == 0


def test_calls_lose_only_exact_boilerplate_not_near_repeats():
    h = History()
    filter_doc(RISK, h, "Q1 call", near=False)
    out, _ = filter_doc(RISK2, h, "Q2 call", near=False)
    assert RISK2 in out and "changed since" not in out


def test_headings_and_short_lines_always_survive():
    h = History()
    filter_doc("## Risk Factors\n\nShort line.", h, "A", near=True)
    out, _ = filter_doc("## Risk Factors\n\nShort line.", h, "B", near=True)
    assert "## Risk Factors" in out and "Short line." in out


def test_blocks_split_tables_from_text():
    kinds = [k for k, _ in blocks("Intro text here.\n" + TABLE + "\nAfter text.")]
    assert kinds == ["text", "table", "text"]


def test_a_10q_is_compared_with_the_earlier_10k(tmp_path):
    src = make_src(str(tmp_path), [
        ("10-K:2024-12-31", "10-Ks", "TEST 2024 10-K", RISK, "found"),
        ("10-Q:2025-03-31", "10-Qs", "TEST 2025 Q1 10-Q", RISK + "\n\n" + NEW, "found"),
    ])
    docs, _, _ = build(src)
    save(os.path.join(work_dir(src), "inventory.json"), docs)
    stats = run(src)
    q = open(os.path.join(work_dir(src), stats["TEST 2025 Q1 10-Q"]["filtered"]), encoding="utf-8").read()
    assert "unchanged since TEST 2024 10-K" in q and NEW in q
    k = open(os.path.join(work_dir(src), stats["TEST 2024 10-K"]["filtered"]), encoding="utf-8").read()
    assert RISK in k


def _para(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_a_paragraph_repeated_inside_one_filing_is_not_dropped_against_itself():
    # a document is only compared with EARLIER documents
    out, st = filter_doc(RISK + "\n\n" + RISK, History(), "A", near=True)
    assert out.count(RISK) == 2 and "unchanged" not in out and st["dropped"] == 0


def test_the_diff_is_against_the_newest_similar_version():
    a = _para(30)
    a2 = a.replace("w5 ", "x5 ")
    a3 = a.replace("w5 ", "y5 ")
    h = History()
    filter_doc(a, h, "2022", near=True)
    filter_doc(a2, h, "2023", near=True)
    out, _ = filter_doc(a3, h, "2024", near=True)
    assert "changed since 2023" in out


S1 = "Dexcom sells continuous glucose monitors to people with diabetes in many countries around the world."
S2 = "We estimate that between 5.0 and 6.0 million people with Type 2 diabetes could use our products."
S3 = "Reimbursement from insurers and government payers remains the main driver of how fast we can grow."


def test_a_one_number_change_shows_the_whole_sentence_with_marks_and_dots_around_it():
    h = History()
    filter_doc(" ".join([S1, S2, S3]), h, "A", near=True)
    s2 = S2.replace("between 5.0 and 6.0", "greater than 6")
    out, _ = filter_doc(" ".join([S1, s2, S3]), h, "B", near=True)
    assert "~~[- between 5.0 and 6.0 -]~~ **[+ greater than 6 +]** million people with Type 2 diabetes could use our products." in out
    assert "Dexcom" not in out and "Reimbursement" not in out
    body = out.split("]* ", 1)[1].strip()
    assert body.startswith("…") and body.endswith("…")


def test_a_deletion_at_the_very_end_shows_the_last_sentence():
    h = History()
    filter_doc(" ".join([S1, S2, S3 + " Competition is a risk."]), h, "A", near=True)
    out, _ = filter_doc(" ".join([S1, S2, S3]), h, "B", near=True)
    assert "Reimbursement" in out and "~~[- Competition is a risk. -]~~" in out
    assert "Dexcom" not in out


def test_a_heavily_rewritten_paragraph_is_kept_in_full_marked_revised():
    old = _para(20)
    new = " ".join([f"w{i}" for i in range(13)] + [f"n{i}" for i in range(7)])
    h = History()
    filter_doc(old, h, "A", near=True)
    out, st = filter_doc(new, h, "B", near=True)
    assert "revised since A" in out and new in out and "~~" not in out
    assert st["revised"] == 1


def _seen_in(n, para):
    h = History()
    for i in range(n):
        filter_doc(para, h, f"release {i + 1}", near=False)
    return h


def test_a_paragraph_in_only_two_earlier_releases_is_kept_on_the_third():
    # an unchanged guidance range being reaffirmed is meaningful, not boilerplate
    out, st = filter_doc(RISK, _seen_in(2, RISK), "release 3", near=False)
    assert RISK in out and st["dropped"] == 0


def test_a_paragraph_in_three_earlier_releases_is_dropped_as_boilerplate():
    out, st = filter_doc(RISK, _seen_in(3, RISK), "release 4", near=False)
    assert RISK not in out and "unchanged since release 1" in out and st["dropped"] == 1


def test_a_10k_paragraph_is_still_dropped_on_its_first_repeat():
    h = History()
    filter_doc(RISK, h, "10-K 1", near=True)
    out, st = filter_doc(RISK, h, "10-K 2", near=True)
    assert RISK not in out and st["dropped"] == 1


def test_output_does_not_depend_on_the_python_hash_seed():
    # same inputs must give the same filtered files on every run
    code = (
        "import sys; sys.path.insert(0, 'scripts')\n"
        "from filter import History, filter_doc\n"
        "def doc(v): return '\\n\\n'.join(' '.join(('x%d_%d' % (v, i)) if v and i % 7 == 3 else 'p%dw%d' % (p, i) for i in range(70)) for p in range(40))\n"
        "h = History()\n"
        "for n, v in enumerate((0, 1, 2)):\n"
        "    print(filter_doc(doc(v), h, 'D%d' % n, near=True))\n"
    )
    outs = [subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": seed}).stdout for seed in ("1", "2", "3")]
    assert outs[0] == outs[1] == outs[2] and "changed since" in outs[0]
