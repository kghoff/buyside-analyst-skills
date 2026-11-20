"""The labels write-pitch reads from other skills' tabs must still be written by those skills.

write-pitch finds every number by its label or header (never by address). Its own tests check the readers against
write-pitch's fixture, which is written to match the labels write-pitch expects, so a producer renaming a label (say
model-valuation's "IRR hurdle") would pass every write-pitch test and break only on a real model: the call would be
checked against the house hurdle with no warning, or a slide's table would silently go missing. These tests read the
producing skills' source and assert each label is still there. Plain substring search, so they do not depend on how
the producers are structured."""
import pathlib
import re

import pytest

import labels
import model_reads

SKILLS = pathlib.Path(__file__).resolve().parents[2]


def source(*skills):
    return "\n".join(p.read_text(encoding="utf-8") for s in skills
                     for p in sorted((SKILLS / s / "scripts").glob("*")) if p.suffix in (".py", ".mjs"))


def written_whole(label, text):
    """The label as a whole string literal ("IRR" must not pass because "IRR hurdle" exists)."""
    return any(f"{q}{label}{q}" in text for q in ('"', "'"))


# ------------------------------------------------------------------ labels.py: the call and the hurdles
VALUATION, SHORT = source("model-valuation"), source("model-short")


@pytest.mark.parametrize("label", [labels.VAL_VERDICT, *labels.HURDLE_LABELS.values()])
def test_valuation_labels_exist(label):
    # a renamed verdict reads as empty (= Hold); a renamed hurdle falls back to the house default
    assert written_whole(label, VALUATION), f"model-valuation no longer writes {label!r}"


@pytest.mark.parametrize("label", [labels.SHORT_AGENT, labels.SHORT_RULE])
def test_short_labels_exist(label):
    # a renamed short verdict reads as none, so a short call would be checked against nothing
    assert written_whole(label, SHORT), f"model-short no longer writes {label!r}"


# ------------------------------------------------------------------ model_reads.py: SUM's cap table and estimates
SUMMARY = source("model-summary")
# Labels model-summary builds at run time from a name in links.STREET_MAP (layout.py st_rows): no literal holds the
# whole label, so each fragment that builds it must be there.
COMPOSED = {
    "Street revenue": ['f"Street {nm}"', '("rev", "level", "revenue")'],
    "Street EPS": ['f"Street {nm}"', '("eps", "level", "EPS")'],
    "Revenue delta": ['f"{nm[0].upper()}{nm[1:]} delta (ours vs Street"', '("rev", "level", "revenue")'],
}
CAP_LABELS = sorted({(lab, exact) for _, lab, exact, _, _, _ in model_reads.CAP_ROWS}
                    | {(after, True) for _, _, _, after, _, _ in model_reads.CAP_ROWS if after})
BLOCK_HEADS = ["Cap table", "Internal estimates"]          # startswith in model_reads


@pytest.mark.parametrize("label, exact", CAP_LABELS + [(w, e) for w, e in model_reads.GRID_ROWS])
def test_summary_row_labels_exist(label, exact):
    # a renamed SUM row drops out of the deck's cap table or estimates grid with no error
    if label in COMPOSED:
        missing = [f for f in COMPOSED[label] if f not in SUMMARY]
        assert not missing, f"model-summary no longer builds {label!r}: {missing} not found"
    elif exact:
        assert written_whole(label, SUMMARY), f"model-summary no longer writes {label!r}"
    else:
        assert label in SUMMARY, f"model-summary no longer writes a label starting {label!r}"


@pytest.mark.parametrize("label", BLOCK_HEADS)
def test_summary_block_headers_exist(label):
    assert label in SUMMARY, f"model-summary no longer writes a block headed {label!r}"


# ------------------------------------------------------------------ model_reads.py: Multiples, Valuation, Px tabs
MULTIPLES = source("model-multiples")
PE_HEADS = ["WEEKLY DATA", "Week", "P/E", "P/E (GAAP)", "S&P 500 P/E", "Core-peer median P/E"]
LADDER_HEADS = ["Entry", "Reward", "Risk", "R/R"]
PRICE = source("model-price-history")
PRICE_HEADS = ["Date", "Full-results release date"]


@pytest.mark.parametrize("label", PE_HEADS)
def test_multiples_weekly_headers_exist(label):
    # the P/E history chart (and its basis) reads these; one renamed = no chart
    assert written_whole(label, MULTIPLES), f"model-multiples no longer writes {label!r}"


def test_valuation_ladder_block_exists():
    # model_reads.LADDER matches "<n><letter>. Reward / risk ladder ..." case-insensitively in column A
    titles = re.findall(r'"(\d+[a-z]?\.\s*Reward / risk ladder[^"]*)"', VALUATION, re.I)
    assert titles and all(model_reads.LADDER.match(t) for t in titles), "model-valuation's ladder title changed"


@pytest.mark.parametrize("label", LADDER_HEADS)
def test_valuation_ladder_headers_exist(label):
    assert written_whole(label, VALUATION), f"model-valuation no longer writes the ladder header {label!r}"


@pytest.mark.parametrize("label", PRICE_HEADS)
def test_price_history_headers_exist(label):
    # the deck's price chart and its release markers
    assert written_whole(label, PRICE), f"model-price-history no longer writes {label!r}"


def test_price_history_close_column_exists():
    # model_reads.price_history looks for "<T> close"
    assert 'f"{T} close"' in PRICE, "model-price-history no longer writes the '<T> close' column"


# ------------------------------------------------------------------ the lists above mirror the reader
@pytest.mark.parametrize("label", BLOCK_HEADS + PE_HEADS + LADDER_HEADS + PRICE_HEADS + ["Reward / risk ladder"])
def test_listed_headers_are_what_model_reads_reads(label):
    # if model_reads stops reading a header (or reads a new one), this list must change with it
    assert label.lower() in pathlib.Path(model_reads.__file__).read_text().lower()
