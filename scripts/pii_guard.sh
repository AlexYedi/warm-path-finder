#!/usr/bin/env bash
# Block commits that would publish personal data.
#   scripts/pii_guard.sh --staged   (pre-commit: staged files only)
#   scripts/pii_guard.sh            (CI: every tracked file)
# Allowed: example.com / example.org addresses and noreply addresses.
set -euo pipefail

if [[ "${1:-}" == "--staged" ]]; then
  files=$(git diff --cached --name-only --diff-filter=ACM)
else
  files=$(git ls-files)
fi
[[ -z "$files" ]] && exit 0

fail=0

if echo "$files" | grep -q '^data/real/'; then
  echo "pii-guard: data/real/ must never be committed:"
  echo "$files" | grep '^data/real/' | sed 's/^/  /'
  fail=1
fi

email='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
allowed='@example\.(com|org)|noreply@'
profile='linkedin\.com/in/'

while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  hits=$( (grep -nEI "$email" "$f" | grep -vE "$allowed"; grep -nEI "$profile" "$f") | sort -u || true)
  if [[ -n "$hits" ]]; then
    echo "pii-guard: possible personal data in $f:"
    echo "$hits" | sed 's/^/  /'
    fail=1
  fi
done <<< "$files"

if [[ $fail -ne 0 ]]; then
  echo "pii-guard: blocked. Remove the data, or move real exports to data/real/ (gitignored)."
  exit 1
fi
