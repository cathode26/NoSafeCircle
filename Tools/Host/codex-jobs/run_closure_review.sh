#!/usr/bin/env bash
# Cumulative closure review of a task-contract revision (templates/contract-closure-review-prompt.md).
# Usage: run_closure_review.sh <job> <TASK> <revision-commit> <previous-checked-commit> [extra repo paths changed in the same commit...]
#
# 2026-09-20, Pipeline Maintainer. Three defects fixed, two of them found by audit
# Tools-Cleanup-Audit/20260920-143913 in the same day's first fix:
#
#   1. It called a bare `codex.exe`. PATH resolves that to an old build which refuses the
#      gpt-6-astra default in config.toml and exits 1 writing nothing, so the GER Agent's live
#      contract check produced no report at all. Now uses the tested resolver.
#   2. The first fix stored the provider status in `rc` and never rejected a nonzero value, and
#      the last command was a `grep`, so the SCRIPT's exit status was grep's. The audit
#      reproduced provider-status-7 plus a leftover report reading as SUCCESS (exit 0).
#      Now judged by the tested checker, which keeps three questions apart: did the process
#      succeed, is the artifact fresh, and what does it say.
#   3. The inline awk version key reduced 0.155.0-alpha.2.6 and 0.155.0-alpha.9.2 to the same
#      value and broke the tie by filesystem order. The resolver orders prereleases properly.
#
# Exit: 0 success; 2 setup refused; 3 no report; 4 provider failed; 5 stale report; 6 empty report.
set -u

JOB="$1"; TASK="$2"; COMMIT="$3"; PREV="$4"; shift 4
ROOT=C:/nscrev/codex-jobs; CLONE="$ROOT/$JOB"; PROMPT="$ROOT/$JOB.prompt.md"
REPO=C:/NSC/NSC/NoSafeCircle
REPORT="$ROOT/$JOB.report.md"
MODEL="${NSC_CODEX_MODEL:-gpt-6-astra}"

# Tracked helpers. Prefer the maintained location; the C:/nscrev junction is a fallback so this
# keeps working if the move is reversed. Both are tested (tools/jobs/tests).
HELPERS=""
for _h in "C:/NSC/tools/jobs" "C:/nscrev/job-tools"; do
  [ -f "$_h/resolve_codex.py" ] && { HELPERS="$_h"; break; }
done
[ -n "$HELPERS" ] || { echo "cannot find resolve_codex.py in C:/NSC/tools/jobs or C:/nscrev/job-tools" >&2; exit 2; }

CODEX="$(python -B "$HELPERS/resolve_codex.py")" || {
  echo "no usable codex binary; see above" >&2; exit 2; }

[ -f "$PROMPT" ] || { echo "missing prompt $PROMPT" >&2; exit 2; }
[ -e "$CLONE" ] && { echo "clone exists $CLONE" >&2; exit 2; }

git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true "$REPO" "$CLONE" || exit 2
git -C "$CLONE" checkout -q --detach "$COMMIT^" || exit 2
git -C "$REPO" show "$COMMIT:Tasks/$TASK.yaml" > "$CLONE/REVISED_CONTRACT.json" || exit 2
git -C "$REPO" show "$PREV:Tasks/$TASK.yaml" > "$CLONE/PREVIOUS_CONTRACT.json" || exit 2
for extra in "$@"; do
  git -C "$REPO" show "$COMMIT:$extra" > "$CLONE/REVISED_$(basename "$extra")" || exit 2
done

# Move any earlier report aside, so a leftover can never be mistaken for this run's output.
if [ -e "$REPORT" ]; then
  mv "$REPORT" "$REPORT.superseded-$(date -u +%Y%m%dT%H%M%SZ)"
fi
STARTED_AT="$(python -B -c 'import time; print(time.time())')"

echo "[START] $JOB $(date -u +%FT%TZ) clone at $(git -C "$CLONE" rev-parse --short HEAD), revised $(git -C "$REPO" rev-parse --short "$COMMIT"), previous $(git -C "$REPO" rev-parse --short "$PREV")"
echo "[CODEX] $CODEX ($("$CODEX" --version 2>&1 | head -1)) model=$MODEL"

"$CODEX" exec --sandbox read-only --cd "$CLONE" --skip-git-repo-check \
  -m "$MODEL" -c model_reasoning_effort=high --color never \
  --output-last-message "$REPORT" - < "$PROMPT" > "$ROOT/$JOB.log" 2>&1
rc=$?
echo "[DONE] $JOB provider exit $rc $(date -u +%FT%TZ)"

python -B "$HELPERS/check_job_result.py" \
  --rc "$rc" --report "$REPORT" --started-at "$STARTED_AT" \
  --verdict-grep "Final recommendation"
status=$?

if [ "$status" -ne 0 ]; then
  echo "[FAILED] $JOB - last lines of the log:" >&2
  tail -5 "$ROOT/$JOB.log" >&2
fi
exit "$status"
