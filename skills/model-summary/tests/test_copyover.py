"""The user owns the model: the build replaces it only if nobody saved it since the build started, and never while
Excel has it open. Then the record of what was written becomes the one the next rerun reads."""
import os
import shutil

import pytest

import copyover


def _setup(tmp_path, built):
    m = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(built[0], m)
    work = str(tmp_path / "w")
    os.makedirs(work)
    open(os.path.join(work, "inputs_written.next.json"), "w").write("{}")
    return m, work


def test_copies_and_promotes(tmp_path, built):
    m, work = _setup(tmp_path, built)
    copyover.run(m, built[0], copyover.sha256(m), work)
    assert os.path.exists(os.path.join(work, "inputs_written.json"))
    assert not os.path.exists(os.path.join(work, "inputs_written.next.json"))


def test_changed_model_stops(tmp_path, built):
    m, work = _setup(tmp_path, built)
    sha = copyover.sha256(m)
    open(m, "ab").write(b"x")                       # someone saved it meanwhile
    with pytest.raises(SystemExit, match="changed"):
        copyover.run(m, built[0], sha, work)


def test_open_in_excel_stops(tmp_path, built):
    m, work = _setup(tmp_path, built)
    open(str(tmp_path / "~$TEST_model.xlsx"), "w").write("")
    with pytest.raises(SystemExit, match="Excel"):
        copyover.run(m, built[0], copyover.sha256(m), work)
