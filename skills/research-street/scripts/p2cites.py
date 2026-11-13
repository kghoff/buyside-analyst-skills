"""Citation helpers: make the street research citations checkable with research-filings' tools.

research-filings' checkers split a citation on ';' and match a source by its label prefix. So:
  - a sell-side label containing ';' is rewritten with ' /' (safe_label), in the text and in the source list alike;
  - a web citation part '<Author or Firm>, <date>, <url>' becomes '<url>, web', so the URL is the source label."""
import re

CITE = re.compile(r"\[([^\[\]\n]+?)\](?!\()")
URL = re.compile(r"https?://[^\s;\]]+")
WEB_DATE = re.compile(r"(\d{4}-\d{2}-\d{2}|undated)\s*,\s*(https?://[^\s;\]]+)")


def safe_label(label):
    return label.replace(";", " /")


def _clean(url):
    while True:
        u = url.rstrip(".,")
        if u.endswith(")") and u.count(")") > u.count("("):
            u = u[:-1]
        if u == url:
            return u
        url = u


def canon(url):
    return _clean(url.strip()).rstrip("/")


def normalize(text, labels=()):
    for label in sorted(labels, key=len, reverse=True):
        if ";" in label:
            text = text.replace(label, safe_label(label))

    def fix(m):
        parts = []
        for p in m.group(1).split(";"):
            u = URL.search(p)
            parts.append(f" {canon(u.group(0))}, web" if u else p)
        return "[" + ";".join(parts).strip() + "]"

    return CITE.sub(fix, text)


def cited_urls(text):
    return {canon(u) for m in CITE.finditer(text) for u in URL.findall(m.group(1))}


def web_dates(text):
    """[(date or 'undated', url)] for every web citation part, in order."""
    return [(d, canon(u)) for m in CITE.finditer(text) for d, u in WEB_DATE.findall(m.group(1))]
