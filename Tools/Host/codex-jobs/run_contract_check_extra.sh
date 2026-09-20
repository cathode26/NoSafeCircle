#!/usr/bin/env bash
# Like run_contract_check.sh, plus: every extra repo path given after the commit is exported from the commit
# into the clone as REVISED_<basename> so the checker sees files changed in the same commit.
JOB="$1"; TASK="$2"; COMMIT="$3"; shift 3
ROOT=C:/nscrev/codex-jobs; CLONE="$ROOT/$JOB"; PROMPT="$ROOT/$JOB.prompt.md"
[ -f "$PROMPT" ] || { echo "missing prompt $PROMPT"; exit 2; }
[ -e "$CLONE" ] && { echo "clone exists $CLONE"; exit 2; }
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true C:/NSC/NSC/NoSafeCircle "$CLONE" || exit 2
git -C "$CLONE" checkout -q --detach "$COMMIT^" || exit 2
git -C C:/NSC/NSC/NoSafeCircle show "$COMMIT:Tasks/$TASK.yaml" > "$CLONE/REVISED_CONTRACT.json" || exit 2
for extra in "$@"; do git -C C:/NSC/NSC/NoSafeCircle show "$COMMIT:$extra" > "$CLONE/REVISED_$(basename "$extra")" || exit 2; done
echo "[START] $JOB $(date -u +%FT%TZ) clone at $(git -C "$CLONE" rev-parse --short HEAD), revised from $(git -C C:/NSC/NSC/NoSafeCircle rev-parse "$COMMIT")"
codex.exe exec --sandbox read-only --cd "$CLONE" --skip-git-repo-check -c model_reasoning_effort=high --color never --output-last-message "$ROOT/$JOB.report.md" - < "$PROMPT" > "$ROOT/$JOB.log" 2>&1
echo "[DONE] $JOB exit $? $(date -u +%FT%TZ)"
grep -i "Final recommendation" "$ROOT/$JOB.report.md"
