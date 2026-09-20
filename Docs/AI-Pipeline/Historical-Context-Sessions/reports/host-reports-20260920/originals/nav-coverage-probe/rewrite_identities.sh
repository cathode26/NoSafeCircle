#!/usr/bin/env bash
# Rebuild the leash-fix chain with clean committer identities. Two commits carry Vincent's real
# outlook address as committer (a rebase leak); this replaces only that field, preserving every
# tree, message, author identity and both dates. Plumbing only - no checkout is touched.
set -euo pipefail

cd /c/nscrev/branch-verify
BRANCH=fix/melee-leash-and-spawns-20260917
OLD_TIP=$(git rev-parse HEAD)
BASE=$(git rev-parse main)
WORK=/c/nscrev/reports/nav-coverage-probe/rewrite

mkdir -p "$WORK"

# Keep the pre-rewrite tip reachable before moving anything.
git update-ref "refs/archive/${BRANCH//\//-}-pre-identity-rewrite" "$(git rev-parse "$BRANCH")"
git update-ref "refs/archive/${BRANCH//\//-}-pre-identity-rewrite-head" "$OLD_TIP"

parent=$BASE
i=0
for c in $(git rev-list --reverse "$BASE..$OLD_TIP"); do
  i=$((i + 1))
  tree=$(git rev-parse "$c^{tree}")
  git log -1 --format=%B "$c" > "$WORK/msg-$i.txt"

  GIT_AUTHOR_NAME=$(git log -1 --format=%an "$c")
  GIT_AUTHOR_EMAIL=$(git log -1 --format=%ae "$c")
  GIT_AUTHOR_DATE=$(git log -1 --format=%aD "$c")
  GIT_COMMITTER_DATE=$(git log -1 --format=%cD "$c")
  old_committer_email=$(git log -1 --format=%ce "$c")
  old_committer_name=$(git log -1 --format=%cn "$c")

  # Preserve an already-clean committer; substitute only a leaked one.
  case "$old_committer_email" in
    *.invalid)
      GIT_COMMITTER_NAME=$old_committer_name
      GIT_COMMITTER_EMAIL=$old_committer_email
      ;;
    *)
      GIT_COMMITTER_NAME="No Safe Circle Game Agent"
      GIT_COMMITTER_EMAIL="game-agent@nosafecircle.invalid"
      echo "  rewriting committer of ${c:0:9}: $old_committer_email -> $GIT_COMMITTER_EMAIL"
      ;;
  esac

  export GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_AUTHOR_DATE
  export GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL GIT_COMMITTER_DATE

  parent=$(git commit-tree "$tree" -p "$parent" -F "$WORK/msg-$i.txt")
  echo "  ${c:0:9} -> ${parent:0:9}"
done

NEW_TIP=$parent
echo "new tip $NEW_TIP"

# Content must be byte-identical to what was verified.
if ! git diff --quiet "$OLD_TIP" "$NEW_TIP"; then
  echo "ABORT: rewritten tip differs in content from the verified tip"
  git diff --stat "$OLD_TIP" "$NEW_TIP" | tail -5
  exit 1
fi
echo "content identical to the verified tip: OK"

git branch -f "$BRANCH" "$NEW_TIP"
git checkout -q "$BRANCH"

echo "--- chain now ---"
git log --format='%h | %ce | %an | %s' "$BASE..$BRANCH"
echo "--- distinct committer emails ---"
git log --format='%ce' "$BASE..$BRANCH" | sort -u
echo "--- distinct author emails ---"
git log --format='%ae' "$BASE..$BRANCH" | sort -u
echo "--- churn preserved: $(git status --porcelain | grep -c '^ M') modified, $(git status --porcelain | grep -c '^??') untracked"
