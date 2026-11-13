"""User settings for the buyside skills: ~/.config/buyside-analyst/settings.json (BUYSIDE_SETTINGS overrides the path).

Command line: python3 settings.py research_dir  -> prints the expanded research folder.
(xbrl_cli: the edgar-xbrl-financials command line tool, used by model-industry.)
"""
import json
import os
import sys

DEFAULTS = {"sec_contact": "", "research_dir": "~/Desktop/Research", "alpha_vantage_keys": [],
            "chrome_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "xbrl_cli": "~/Desktop/edgar-xbrl-financials/bin/cli.js"}


def path():
    return os.path.expanduser(os.environ.get("BUYSIDE_SETTINGS", "~/.config/buyside-analyst/settings.json"))


def load():
    p = path()
    data = {}
    if os.path.exists(p):
        with open(p) as f:
            data = json.load(f)
    return {**DEFAULTS, **data}


def xbrl_cli():
    return os.path.expanduser(load()["xbrl_cli"])


def research_dir():
    return os.path.expanduser(load()["research_dir"])


if __name__ == "__main__":
    print(research_dir() if sys.argv[1:] == ["research_dir"] else json.dumps(load(), indent=1))
