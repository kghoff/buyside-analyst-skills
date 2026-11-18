#!/usr/bin/env bash
# Runs every skill's tests, then the reference check. Ends with ALL PASS or exits non-zero.
# Default: skips the tests marked slow (they start LibreOffice); each line says how many were skipped ("deselected").
# --full: every test. Run it before any merge.
set -u
R="$(cd "$(dirname "$0")" && pwd)"
export BUYSIDE_SETTINGS="$R/tests/settings.test.json"
SEL=(-m "not slow")
[ "${1:-}" = "--full" ] && SEL=()
# A private temp folder: LibreOffice profiles never clash with another run, and every temp copy is deleted at the end.
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/buyside-tests.XXXXXX")"
export TMPDIR
trap 'rm -rf "${TMPDIR:?}"' EXIT
summary() { echo "$1" | grep -E '[0-9]+ (passed|failed|error)' | tail -1; }
fail=0
for d in "$R"/skills/*/; do
  s=$(basename "$d")
  if [ -f "$d/package.json" ] && grep -q '"test"' "$d/package.json"; then
    out=$(cd "$d" && npm test --silent 2>&1); rc=$?
    echo "$s (node): $(echo "$out" | grep -E 'Tests +[0-9]|^ℹ (pass|fail)' | tr '\n' ' ')"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
  fi
  if [ -d "$d/tests" ]; then
    out=$(cd "$d" && python3 -m pytest -q -p no:cacheprovider ${SEL[@]+"${SEL[@]}"} 2>&1); rc=$?
    [ $rc -eq 5 ] && echo "$out" | grep -q deselected && rc=0   # every test in the suite is slow and was skipped
    echo "$s (python): $(summary "$out")"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
  fi
done
if [ -d "$R/tests" ] && ls "$R"/tests/test_*.py >/dev/null 2>&1; then
  out=$(cd "$R" && python3 -m pytest -q -p no:cacheprovider tests 2>&1); rc=$?
  echo "lib (python): $(summary "$out")"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
fi
if ls "$R"/tests/*.test.mjs >/dev/null 2>&1; then
  out=$(cd "$R" && node --test tests/*.test.mjs 2>&1); rc=$?
  echo "lib (node): $(echo "$out" | grep -E '^(# |ℹ )(pass|fail)' | tr '\n' ' ')"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
fi
[ -x "$R/check-refs.sh" ] && { "$R/check-refs.sh" || fail=1; }
[ $fail -eq 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }
