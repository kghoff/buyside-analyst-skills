from merge_data import coverage, coverage_table, fill_dates, merge, track

DATES = {"TEST 2023 10-K": "2024-02-10", "TEST 2024 10-K": "2025-02-10"}


def r(metric, period, value, source):
    return {"metric": metric, "period": period, "value": str(value), "unit": "", "source": source}


def test_on_a_conflict_the_newest_document_wins_and_the_conflict_is_listed():
    # restatements happen: the later filing is the better number, but the user must see the disagreement
    rows, conflicts = merge([], [r("Users", "FY2023", 2.0, "TEST 2023 10-K, p1"),
                                 r("Users", "FY2023", 2.2, "TEST 2024 10-K, p1")], DATES)
    assert rows[0]["value"] == "2.2" and len(conflicts) == 1


def test_the_model_wins_over_a_reader():
    rows, conflicts = merge([r("Rev", "FY2024", 100, "Model, MOD!H5")], [r("Rev", "FY2024", 101, "TEST 2024 10-K, p1")], DATES)
    assert rows[0]["source"] == "Model, MOD!H5" and len(conflicts) == 1


def test_equal_values_are_not_a_conflict():
    assert merge([], [r("U", "FY2023", 2.0, "TEST 2023 10-K, a"), r("U", "FY2023", 2.0, "TEST 2024 10-K, b")], DATES)[1] == []


def test_coverage_counts_years_and_names_gaps():
    # disclosure coverage decides which forecast build is possible
    rows = [r("Sensor rev", p, 1, "Model, x") for p in ("FY2019", "Q1 2020", "FY2022")]
    c = coverage(rows)["Sensor rev"]
    assert (c["first"], c["last"], c["years"], c["gaps"]) == (2019, 2022, 3, [2021])


def test_track_uses_the_first_guide_counts_revisions_and_scores_vs_initial_midpoint():
    g = [{"fiscal_year": "2024", "metric": "Revenue", "basis": "reported", "kind": "hard", "date": d, "low": lo,
          "high": hi, "actual": act, "source": "x"} for d, lo, hi, act in
         [("2024-02-10", "100", "110", ""), ("2024-05-01", "104", "110", ""), ("2025-02-10", "", "", "112")]]
    t = track(g)[0]
    assert (t["initial_low"], t["initial_high"], t["revisions"], t["actual"]) == ("100", "110", 1, "112")
    assert abs(t["vs_initial_mid"] - (112 / 105 - 1)) < 1e-9


def test_identical_reiterated_guidance_is_not_a_revision():
    g = [{"fiscal_year": "2024", "metric": "Revenue", "basis": "reported", "kind": "hard", "date": d, "low": "100",
          "high": "110", "actual": "", "source": "x"} for d in ("2024-02-10", "2024-05-01", "2024-08-01")]
    assert track(g)[0]["revisions"] == 0


def test_a_reader_metric_is_tagged_documents_even_with_an_uppercase_name():
    assert coverage([r("ARPU", "FY2023", 1, "TEST 2023 10-K, p1")])["ARPU"]["from"] == "documents"
    assert coverage([r("INCOME | Rev", "FY2023", 1, "Model, MOD!H5")])["INCOME | Rev"]["from"] == "model"


def test_guidance_without_an_iso_date_takes_its_document_date_so_the_initial_guide_sorts_right():
    docs = {"2025 Q2 DXCM call": "2025-07-31"}
    g = [{"date": "2025 Q2 call", "source": "2025 Q2 DXCM call, Q&A"},
         {"date": "2025-01-05", "source": "2025 Q2 DXCM call, Q&A"},
         {"date": "(date not stated)", "source": "unknown doc"}]
    rows, undated = fill_dates(g, docs)
    assert [x["date"] for x in rows] == ["2025-07-31", "2025-01-05", "(date not stated)"]
    assert undated == 1


def _cov(metric, n):
    return {metric: {"first": 2020, "last": 2020 + n - 1, "years": n, "gaps": [], "from": "documents"}}


def test_key_table_drops_metrics_disclosed_in_under_3_years_but_the_full_table_keeps_them():
    # agents read the key file; 1-2 year reader metrics are noise there, yet must stay in the full list
    cov = {**_cov("Two", 2), **_cov("Four", 4)}
    key, full = "\n".join(coverage_table(cov, min_years=3)), "\n".join(coverage_table(cov))
    assert "| Four |" in key and "| Two |" not in key
    assert "| Two |" in full


def test_pipe_in_a_metric_name_is_escaped_so_the_row_keeps_its_columns():
    rows = coverage_table(_cov("Rev | EMEA", 3))
    row = rows[-1]
    assert "Rev \\| EMEA" in row
    assert len(row.replace("\\|", "").split("|")) == len(rows[0].split("|"))
