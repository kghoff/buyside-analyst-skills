# skills/model-summary/scripts/copyover.py
"""Copy the verified build over the user's model only if the model is unchanged since the build started (its
shasum) and Excel does not have it open; then promote inputs_written.next.json. No backup copy is kept.

usage: python3 copyover.py --model M --built W/out.xlsx --sha SHA256 --work W"""
import argparse
import hashlib
import os
import shutil


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run(model, built, sha, work):
    lock = os.path.join(os.path.dirname(model), "~$" + os.path.basename(model))
    if os.path.exists(lock):
        raise SystemExit("model-summary: Excel has the model open. Close it, then rerun this step.")
    if sha256(model) != sha:
        raise SystemExit("model-summary: the model changed since the build started (it was saved). Nothing was "
                         "copied; rerun /model-summary.")
    shutil.copyfile(built, model)
    nxt = os.path.join(work, "inputs_written.next.json")
    if os.path.exists(nxt):
        os.replace(nxt, os.path.join(work, "inputs_written.json"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("--model", "--built", "--sha", "--work"):
        ap.add_argument(k, required=True)
    a = ap.parse_args()
    run(a.model, a.built, a.sha, a.work)
    print("copied")


if __name__ == "__main__":
    main()
