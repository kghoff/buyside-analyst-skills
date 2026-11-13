import json, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import p2charts
import p2preflight
from fixtures import make_src
from p2common import write_csv


def test_heatmap_and_gap_chart_write_pngs(tmp_path):
    out = str(tmp_path / "fig")
    mat = [{"topic": "driver2", "holder_type": "sell-side", "stance": "differs", "count": "2"},
           {"topic": "driver2", "holder_type": "buy-side", "stance": "agrees", "count": "1"},
           {"topic": "industry", "holder_type": "sell-side", "stance": "agrees", "count": "3"}]
    p = p2charts.heatmap(mat, out)
    gaps = [{"n": "1", "group": "Driver 1", "status": "closed-fact"}, {"n": "2", "group": "Driver 1", "status": "open"},
            {"n": "3", "group": "Driver 2", "status": "estimate-only"}]
    g = p2charts.gap_chart(gaps, out)
    assert os.path.getsize(p) > 5000 and os.path.getsize(g) > 5000


def test_lean_is_share_of_non_agreeing_marks():
    assert p2charts.lean({"agrees": 1, "differs": 2, "adds": 1}) == 0.75
    assert p2charts.lean({}) is None


def test_all_draws_price_chart_from_phase1_prices_and_grabs_sellside_page(tmp_path):
    src = make_src(str(tmp_path))
    p2preflight.run("DXCM", src, "2026-11-09")
    w = os.path.join(src, "Street Research", "_work")
    label = "2026-10-29 JPM earnings recap - Good 3Q"
    pdf = os.path.join(src, "Sellside Research", label + ".pdf")
    fig, ax = plt.subplots()
    ax.plot([1, 2])
    fig.savefig(pdf)
    plt.close(fig)
    write_csv(os.path.join(w, "stance_matrix.csv"), ["topic", "holder_type", "stance", "count"],
              [{"topic": "driver2", "holder_type": "sell-side", "stance": "differs", "count": "1"}])
    write_csv(os.path.join(w, "gap_status.csv"), ["n", "group", "title", "status", "best_tier", "sources"],
              [{"n": "1", "group": "Driver 1", "title": "t", "status": "open", "best_tier": "", "sources": ""}])
    json.dump([{"id": "px_views", "kind": "price", "title": "Stock and outside views", "source": "price.csv",
                "events": [["2024-07-25", "JPM: buy the dip"]]}], open(os.path.join(w, "charts.json"), "w"))
    json.dump([{"file": label, "page": 1, "out": "ss_jpm.png", "crop": None, "caption": "c"}],
              open(os.path.join(w, "grabs.json"), "w"))
    errors = p2charts.draw_all(src)
    fig_dir = os.path.join(src, "Street Research", "fig")
    assert errors == [] and sorted(os.listdir(fig_dir)) == ["gap_status.png", "px_views.png", "ss_jpm.png", "stance_heatmap.png"]


def test_series_kinds_rejected(tmp_path):
    src = make_src(str(tmp_path))
    p2preflight.run("DXCM", src, "2026-11-09")
    w = os.path.join(src, "Street Research", "_work")
    json.dump([{"id": "x", "kind": "line", "title": "t", "source": "s"}], open(os.path.join(w, "charts.json"), "w"))
    assert any("series" in e for e in p2charts.draw_all(src))


def test_no_rows_draws_nothing(tmp_path):
    out = str(tmp_path / "fig")
    assert p2charts.heatmap([], out) is None and p2charts.gap_chart([], out) is None
    assert p2charts.heatmap([{"topic": "gap", "holder_type": "sell-side", "stance": "gap-closed", "count": "1"}], out) is None
    assert not os.path.exists(out)
