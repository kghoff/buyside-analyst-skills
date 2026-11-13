#!/usr/bin/env bash
# Runs every skill's tests, then the reference check. Ends with ALL PASS or exits non-zero.
set -u
R="$(cd "$(dirname "$0")" && pwd)"
export BUYSIDE_SETTINGS="$R/tests/settings.test.json"
fail=0
for d in "$R"/skills/*/; do
  s=$(basename "$d")
  if [ -f "$d/package.json" ] && grep -q '"test"' "$d/package.json"; then
    out=$(cd "$d" && npm test --silent 2>&1); rc=$?
    echo "$s (node): $(echo "$out" | grep -E 'Tests +[0-9]' | tail -1)"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
  fi
  if [ -d "$d/tests" ]; then
    out=$(cd "$d" && python3 -m pytest -q -p no:cacheprovider 2>&1); rc=$?
    echo "$s (python): $(echo "$out" | tail -1)"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
  fi
done
if [ -d "$R/tests" ] && ls "$R"/tests/test_*.py >/dev/null 2>&1; then
  out=$(cd "$R" && python3 -m pytest -q -p no:cacheprovider tests 2>&1); rc=$?
  echo "lib (python): $(echo "$out" | tail -1)"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
fi
if ls "$R"/tests/*.test.mjs >/dev/null 2>&1; then
  out=$(cd "$R" && node --test tests/*.test.mjs 2>&1); rc=$?
  echo "lib (node): $(echo "$out" | grep -E '^(# |ℹ )(pass|fail)' | tr '\n' ' ')"; [ $rc -eq 0 ] || { echo "$out" | tail -30; fail=1; }
fi
[ -x "$R/check-refs.sh" ] && { "$R/check-refs.sh" || fail=1; }
[ $fail -eq 0 ] && echo "ALL PASS" || { echo "FAILED"; exit 1; }
