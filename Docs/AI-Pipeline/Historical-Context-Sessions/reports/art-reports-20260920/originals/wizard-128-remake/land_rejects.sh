#!/usr/bin/env bash
# Land the NSC-095 rejected candidates on a local-only branch, per that contract's AC-002.
# Built with plumbing against a temporary index so canonical's worktree, index and HEAD are
# never touched, and never merged into main.
set -euo pipefail

GD=/c/NSC/NSC/NoSafeCircle/.git
SRC=/c/nscrev/reports/art-director/wizard-128-remake/staged-rejects
BRANCH=refs/heads/art-rejects/NSC-095
BASE=$(git --git-dir="$GD" rev-parse main)
MSG=/c/nscrev/reports/art-director/wizard-128-remake/rejects-commit-message.txt

if git --git-dir="$GD" show-ref --verify --quiet "$BRANCH"; then
  echo "ABORT: $BRANCH already exists; refusing to move it."
  exit 1
fi

export GIT_INDEX_FILE=/c/nscrev/reports/art-director/wizard-128-remake/.rejects-index
rm -f "$GIT_INDEX_FILE"
git --git-dir="$GD" read-tree "$BASE"

cd "$SRC"
count=0
while IFS= read -r f; do
  rel=${f#./}
  blob=$(git --git-dir="$GD" hash-object -w --path "$rel" "$f")
  git --git-dir="$GD" update-index --add --cacheinfo "100644,$blob,$rel"
  count=$((count + 1))
done < <(find . -type f | sort)
echo "staged $count files"

tree=$(git --git-dir="$GD" write-tree)
echo "tree $tree"

export GIT_AUTHOR_NAME="No Safe Circle Art Director Agent"
export GIT_AUTHOR_EMAIL="art-director@nosafecircle.invalid"
export GIT_COMMITTER_NAME="No Safe Circle Game Agent"
export GIT_COMMITTER_EMAIL="game-agent@nosafecircle.invalid"

commit=$(git --git-dir="$GD" commit-tree "$tree" -p "$BASE" -F "$MSG")
git --git-dir="$GD" update-ref "$BRANCH" "$commit"
rm -f "$GIT_INDEX_FILE"

echo "commit $commit on ${BRANCH#refs/heads/} (parent ${BASE:0:9})"
echo "--- diff against main ---"
git --git-dir="$GD" diff --stat "$BASE" "$commit" | tail -3
echo "--- identities ---"
git --git-dir="$GD" log -1 --format='author=%an <%ae> committer=%cn <%ce>' "$commit"
echo "--- main unmoved ---"
git --git-dir="$GD" rev-parse --short main
