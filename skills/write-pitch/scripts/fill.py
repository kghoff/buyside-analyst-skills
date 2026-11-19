# skills/write-pitch/scripts/fill.py
"""fill(text, numbers): put each {key} placeholder's `numbers[key]["shown"]` into the text (a key that is not in
numbers raises KeyError("no number named ... in plan numbers"): a broken plan must not print a raw placeholder). label(key) gives a readable name for a key.
usage: from fill import fill, label"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I

HOLDER = re.compile(r"\{(\w+)\}")


def fill(text, numbers):
    """text with every {key} replaced by numbers[key]['shown']."""
    if not isinstance(text, str):
        return text
    def one(m):
        if m.group(1) not in numbers:
            raise KeyError(f"no number named {m.group(1)} in plan numbers")
        return str(numbers[m.group(1)]["shown"])
    return HOLDER.sub(one, text)


def label(key):
    """price -> Price; eps_27_ours -> EPS 27 ours; irr_3y -> IRR 3y."""
    caps = {"eps", "irr", "pe", "ev", "fcf", "ebitda", "rr", "ntm", "ltm"}
    words = [w.upper() if w in caps else w for w in key.split("_")]
    s = " ".join(words)
    return s[0].upper() + s[1:]
