import openpyxl


def test_fixture_layout(mod_path):
    ws = openpyxl.load_workbook(mod_path)["MOD"]
    assert ws["D2"].value == "Q1 21" and ws["H2"].value == 2021 and ws["I2"].value is None
    assert ws["V2"].value == "Q1 24" and ws["X2"].value == "Q3 24E" and ws["Z2"].value == "2024E" and ws["AB2"].value == "2025E"
    assert ws["B4"].value == "Revenue:" and ws["D4"].value == 42.0 and ws["X4"].value is None
    assert ws["D5"].value < 0 and ws["N24"].value == -1.19
