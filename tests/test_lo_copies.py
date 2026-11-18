"""Every skill's lo.recalc copies the user's model to a temp folder before LibreOffice converts it. That copy is a
backup copy of the user's model, which the house rules forbid keeping: recalc must delete it, even when LibreOffice
fails."""
import glob, importlib.util, os, shutil, tempfile
import pytest

COPIES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "skills", "*", "scripts", "lo.py")))


def _load(path):
    spec = importlib.util.spec_from_file_location("lo_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _leftovers(tmp):
    return [n for n in os.listdir(tmp) if n.endswith("_recalc_") or "_recalc_" in n]


@pytest.mark.parametrize("path", COPIES, ids=lambda p: p.split(os.sep)[-3])
@pytest.mark.parametrize("lo_fails", [False, True], ids=["ok", "lo-fails"])
def test_recalc_leaves_no_copy_of_the_model(path, lo_fails, tmp_path, monkeypatch):
    lo = _load(path)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    os.makedirs(tempfile.tempdir)

    def fake_run(args, outdir):          # stands in for LibreOffice: "converts" by copying into outdir
        if lo_fails:
            raise RuntimeError("LibreOffice crashed")
        os.makedirs(outdir, exist_ok=True)
        shutil.copy2(args[-1], outdir)
    monkeypatch.setattr(lo, "_run", fake_run)

    model = tmp_path / "model.xlsx"
    model.write_bytes(b"not really a workbook")
    out = tmp_path / "out"
    if lo_fails:
        with pytest.raises(RuntimeError):
            lo.recalc(str(model), str(out))
    else:
        assert open(lo.recalc(str(model), str(out)), "rb").read() == b"not really a workbook"
    assert _leftovers(tempfile.tempdir) == []


def test_every_copy_is_covered():
    assert len(COPIES) >= 8
