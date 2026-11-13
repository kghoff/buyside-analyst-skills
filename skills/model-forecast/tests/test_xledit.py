from xledit import set_cells


def test_replace_overwrites_only_when_asked():
    # The user's history must never be overwritten by accident; the forecast build replaces their experiments on purpose
    xml = '<worksheet><dimension ref="A1:B2"/><sheetData><row r="2"><c r="B2"><v>0.127</v></c></row></sheetData></worksheet>'
    kept, skipped = set_cells(xml, {"B2": ("n", 0.14, 0)})
    assert skipped == ["B2"] and "0.127" in kept
    new, skipped = set_cells(xml, {"B2": ("n", 0.14, 0)}, replace=True)
    assert skipped == [] and "0.14" in new and "0.127" not in new
