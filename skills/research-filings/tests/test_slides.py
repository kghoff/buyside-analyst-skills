import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

from slides import grab, sheets


def deck(path, n=7):
    with PdfPages(path) as pdf:
        for i in range(n):
            fig = plt.figure(figsize=(10, 5.6))
            fig.text(0.5, 0.5, f"Slide {i + 1}", ha="center", fontsize=40)
            pdf.savefig(fig)
            plt.close(fig)
    return path


def test_contact_sheets_hold_six_labeled_slides_each(tmp_path):
    # agents pick screenshots by eye from these, so every slide must be on a sheet
    n = sheets(deck(str(tmp_path / "d.pdf")), str(tmp_path / "out"))
    assert n == 7 and sorted(os.listdir(tmp_path / "out")) == ["pg", "sheet-01.jpg", "sheet-02.jpg"]


def test_grab_renders_one_slide_and_crops_by_fraction(tmp_path):
    p = deck(str(tmp_path / "d.pdf"), 3)
    full = Image.open(grab(p, 2, str(tmp_path / "full.png"), dpi=100))
    half = Image.open(grab(p, 2, str(tmp_path / "half.png"), dpi=100, crop=(0, 0, 0.5, 1)))
    assert abs(half.size[0] - full.size[0] / 2) <= 1 and half.size[1] == full.size[1]


def test_grab_rejects_a_page_outside_the_deck_and_a_bad_crop(tmp_path):
    import pytest
    p = deck(str(tmp_path / "d.pdf"), 3)
    with pytest.raises(ValueError, match="page 9"):
        grab(p, 9, str(tmp_path / "x.png"))
    with pytest.raises(ValueError, match="crop"):
        grab(p, 1, str(tmp_path / "x.png"), crop=(0.6, 0, 0.4, 1))
