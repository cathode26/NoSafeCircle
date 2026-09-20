#!/usr/bin/env bash
# Codex contract check, per C:\NSC\nsc-ger-orchestrator-guide.md "The contract check" recipe.
# Usage: run_contract_check.sh <job-name> <task-id> <revision-commit>
set -euo pipefail
JOB="$1"; TASK="$2"; COMMIT="$3"
ROOT=C:/nscrev/codex-jobs
CLONE="$ROOT/$JOB"
PROMPT="$ROOT/$JOB.prompt.md"
[ -f "$PROMPT" ] || { echo "missing prompt $PROMPT"; exit 2; }
[ -e "$CLONE" ] && { echo "clone already exists: $CLONE"; exit 2; }
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true C:/NSC/NSC/NoSafeCircle "$CLONE"
git -C "$CLONE" checkout -q --detach "$COMMIT^"
git -C C:/NSC/NSC/NoSafeCircle show "$COMMIT:Tasks/$TASK.yaml" > "$CLONE/REVISED_CONTRACT.json"
echo "[START] $JOB $(date -u +%FT%TZ) clone at $(git -C "$CLONE" rev-parse --short HEAD), revised from $COMMIT"
"C:/Users/VincentLiguori/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe" exec --sandbox read-only --cd "$CLONE" \
  --skip-git-repo-check -c model_reasoning_effort=high --color never \
  --output-last-message "$ROOT/$JOB.report.md" - < "$PROMPT" > "$ROOT/$JOB.log" 2>&1
STATUS=$?
echo "[DONE] $JOB exit $STATUS $(date -u +%FT%TZ)"
grep -i "Final recommendation" "$ROOT/$JOB.report.md" || echo "[WARN] no final recommendation line"
