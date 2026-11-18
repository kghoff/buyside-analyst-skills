"""events.timing: the reaction day depends on when the release went out, read from the call time."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import events  # noqa: E402


def test_call_notice_after_long_tables_still_sets_same_day():
    # Abbott prints its "8 a.m. Central time" call notice after ~20k characters of padded tables. Missing it defaulted
    # 28 pre-market releases to "After close", which would measure each reaction on the wrong (next) day: ABT 2026-11-18.
    text = "Abbott Reports Third-Quarter Results\n" + "|  | 1,021 |  |\n" * 2000 + \
        "Abbott will live-webcast its earnings conference call at 8 a.m. Central time today.\n"
    assert len(text) > 20000
    assert events.timing(text, "After close") == ("Same day", "call at 8 a.m. Central")


def test_no_call_time_keeps_the_default():
    assert events.timing("Abbott announces a dividend.", "After close") == ("After close", None)


def test_a_call_at_the_open_is_same_day():
    # 8:30 a.m. Central = 9:30 ET, the open: the release went out before trading (ABT Q4 19, Q2 20, Q1 21, Q2 23, Q4 24).
    assert events.timing("conference call at 8:30 a.m. Central time today", "After close")[0] == "Same day"
