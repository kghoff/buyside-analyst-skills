from repeat_check import check

P = ("Revenue per customer fell every year from 2022 to 2025 because the mix moved to pharmacy and type 2 users "
     "with lower prices, while the base of active customers kept growing in the mid teens through the whole period.")


def test_a_paragraph_said_again_in_another_section_is_flagged(tmp_path):
    # the first DXCM report repeated itself across writers; each fact should have one home
    (tmp_path / "03-economics.md").write_text("## 03\n\n" + P + "\n")
    (tmp_path / "05-key-drivers.md").write_text("## 05\n\nAs noted, " + P + " [Calc, drivers_math X]\n")
    r = check(str(tmp_path))
    assert r["flagged"]["05-key-drivers.md"][0]["also_in"] == "03-economics.md"


def test_the_summary_may_restate_the_report(tmp_path):
    (tmp_path / "01-summary.md").write_text("## 01\n\n" + P + "\n")
    (tmp_path / "03-economics.md").write_text("## 03\n\n" + P + "\n")
    assert check(str(tmp_path))["flagged"] == {}


def test_glossary_lines_may_repeat(tmp_path):
    g = "**Terms:** CGM = continuous glucose monitor; CMS = Centers for Medicare and Medicaid Services; DME = durable medical equipment; PBM = pharmacy benefit manager; GM = gross margin."
    (tmp_path / "03-economics.md").write_text("## 03\n\n" + g + "\n")
    (tmp_path / "05-key-drivers.md").write_text("## 05\n\n" + g + "\n")
    assert check(str(tmp_path))["flagged"] == {}
