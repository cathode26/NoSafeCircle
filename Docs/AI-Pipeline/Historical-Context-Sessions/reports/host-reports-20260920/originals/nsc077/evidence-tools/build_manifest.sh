#!/usr/bin/env bash
# After a builder run in a verification checkout: restore EOL-only churn, then write the status and a
# SHA-256 manifest of every remaining changed/added path (deleted paths recorded as DELETED).
# Usage: build_manifest.sh <checkout (bash path)> <out prefix (bash path)>
set -u
CO="$1"; OUT="$2"
cd "$CO" || exit 1
restored=0
while IFS= read -r line; do
  code="${line:0:2}"; path="${line:3}"
  if [ "$code" = " M" ] && git diff --ignore-cr-at-eol --quiet -- "$path"; then
    git checkout -- "$path" 2>/dev/null && restored=$((restored+1))
  fi
done < <(git status --porcelain --untracked-files=all)
git status --porcelain --untracked-files=all > "$OUT-status.txt"
: > "$OUT-hashes.txt"
while IFS= read -r line; do
  code="${line:0:2}"; path="${line:3}"
  if [ "$code" = " D" ]; then
    echo "DELETED  $path" >> "$OUT-hashes.txt"
  else
    sha256sum "$path" | sed 's/^\\//' >> "$OUT-hashes.txt"
  fi
done < "$OUT-status.txt"
echo "restored EOL-only: $restored; remaining paths: $(wc -l < "$OUT-status.txt")"
