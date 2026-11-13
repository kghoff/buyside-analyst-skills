from slices import plan


def doc(label, cat, date, sha="a"):
    return {"label": label, "category": cat, "date": date, "md": f"{cat}/_md/{label}.md", "pdf": None,
            "bytes": 100, "sha": sha}


def stats_for(docs, size):
    return {d["label"]: {"filtered_bytes": size, "filtered": f"filtered/{d['category']}/{d['label']}.md"} for d in docs}


def test_every_file_is_in_exactly_one_slice_and_slices_never_mix_types():
    docs = [doc(f"K{i}", "10-Ks", f"201{i}-12-31") for i in range(6)] + [doc("C1", "Earnings Calls", "2020-02-01")]
    sl = plan(docs, stats_for(docs, 100), budget=250)
    labels = [f["label"] for s in sl for f in s["files"]]
    assert sorted(labels) == sorted(d["label"] for d in docs)
    assert all(len({d["category"] for d in docs if d["label"] in [f["label"] for f in s["files"]]}) == 1 for s in sl)


def test_slices_stay_within_budget_and_are_named_by_era():
    docs = [doc(f"K{i}", "10-Ks", f"201{i}-12-31") for i in range(6)]
    sl = plan(docs, stats_for(docs, 100), budget=250)
    assert [len(s["files"]) for s in sl] == [2, 2, 2]
    assert sl[0]["title"] == "10-Ks 2010–2011"


def test_an_oversized_document_gets_its_own_slice():
    docs = [doc("A", "10-Qs", "2020-03-31"), doc("B", "10-Qs", "2020-06-30")]
    st = stats_for(docs, 100)
    st["A"]["filtered_bytes"] = 999
    assert [len(s["files"]) for s in plan(docs, st, budget=250)] == [1, 1]


def test_slice_hash_changes_only_when_one_of_its_files_changes():
    # a rerun reuses a reader's work unless its documents changed
    docs = [doc("A", "10-Ks", "2020-12-31", "x"), doc("B", "Earnings Calls", "2021-01-01", "y")]
    h1 = [s["hash"] for s in plan(docs, stats_for(docs, 10))]
    docs[1]["sha"] = "z"
    h2 = [s["hash"] for s in plan(docs, stats_for(docs, 10))]
    assert h1[0] == h2[0] and h1[1] != h2[1]


def test_pdf_only_documents_are_assigned_their_pdf():
    d = {**doc("Deck", "Investor Decks", "2024-03-31"), "md": None, "pdf": "Investor Decks/Deck.pdf"}
    s = plan([d], {})[0]
    assert s["files"][0]["read"] == "Investor Decks/Deck.pdf"


def test_investor_events_get_a_smaller_budget_than_other_types():
    ev = [doc(f"E{i}", "Investor Events", f"202{i}-03-01") for i in range(3)]
    ks = [doc(f"K{i}", "10-Ks", f"201{i}-12-31") for i in range(3)]
    assert len(plan(ev, stats_for(ev, 60_000))) == 3
    assert len(plan(ks, stats_for(ks, 60_000))) == 1
