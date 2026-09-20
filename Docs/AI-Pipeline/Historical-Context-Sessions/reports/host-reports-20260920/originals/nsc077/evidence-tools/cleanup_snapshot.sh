#!/usr/bin/env bash
# Remove the scratch snapshot script from a verification checkout and restore only line-ending-only churn.
# Usage: cleanup_snapshot.sh <checkout (bash path)>
set -u
CO="$1"
rm -rf "$CO/Assets/_NscEvidence" "$CO/Assets/_NscEvidence.meta"
cd "$CO" || exit 1
restored=0
while IFS= read -r line; do
  code="${line:0:2}"; path="${line:3}"
  if [ "$code" = " M" ] && git diff --ignore-cr-at-eol --quiet -- "$path"; then
    git checkout -- "$path" 2>/dev/null && restored=$((restored+1))
  fi
done < <(git status --porcelain --untracked-files=all)
echo "restored EOL-only: $restored"
echo "remaining:"; git status --porcelain --untracked-files=all
