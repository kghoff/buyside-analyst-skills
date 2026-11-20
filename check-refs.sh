#!/usr/bin/env bash
# Fails if the repo mentions things that must not be public or that tie it to one machine.
# README.md and LICENSE may carry the author's name.
# Personal terms (names, private paths) go one per line in .refs-blocklist, which is git-ignored and so never published.
R="$(cd "$(dirname "$0")" && pwd)"
PAT='\.claude/(skills|agents)|/Users/|phase-1|phase-2|Phase 1|Phase 2'
if [ -f "$R/.refs-blocklist" ]; then
  while IFS= read -r t; do [ -n "$t" ] && PAT="$PAT|$t"; done < "$R/.refs-blocklist"
fi
hits=$(grep -rInE "$PAT" "$R" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.brainstorm --exclude-dir=docs --exclude-dir=.claude-plugin \
  --exclude-dir=__pycache__ --exclude=README.md --exclude=LICENSE --exclude=check-refs.sh --exclude=.refs-blocklist \
  --exclude='*.xlsx' --exclude='*.pdf' --exclude='*.png' --exclude='*.json.gz')
fail=0
if [ -n "$hits" ]; then echo "check-refs: $(echo "$hits" | wc -l | tr -d ' ') hits"; echo "$hits" | head -40; fail=1; fi
# Inside tracked .xlsx files (zip of XML parts): same pattern, absPath, and personal Office user names.
xl=$(git -C "$R" ls-files '*.xlsx' 2>/dev/null | sed "s|^|$R/|"); [ -z "$xl" ] && xl=$(find "$R" -name '*.xlsx' -not -path '*/.git/*')
printf '%s\n' "$xl" | PAT="$PAT" python3 -c '
import os, re, sys, zipfile
pat = re.compile(os.environ["PAT"])
bad = 0
for f in filter(None, (l.strip() for l in sys.stdin)):
    with zipfile.ZipFile(f) as z:
        for n in z.namelist():
            if not n.endswith(".xml"): continue
            t = z.read(n).decode("utf-8", "replace")
            for what, rx in (("pattern", pat), ("absPath", re.compile("absPath"))):
                m = rx.search(t)
                if m: print(f"{f}: {n}: {what}: ...{t[max(0, m.start()-30):m.end()+30]}..."); bad += 1
            if n == "docProps/core.xml":
                for tag in ("dc:creator", "cp:lastModifiedBy"):
                    m = re.search(f"<{tag}[^>]*>([^<]+)</{tag}>", t)
                    if m: print(f"{f}: {n}: non-empty {tag}: {m.group(1)}"); bad += 1
sys.exit(1 if bad else 0)
' || fail=1
[ "$fail" = 1 ] && exit 1
echo "check-refs: clean"
