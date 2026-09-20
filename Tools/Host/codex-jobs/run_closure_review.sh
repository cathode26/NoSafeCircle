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
MODEL="${NSC_CODEX_MODEL:-gpt-6-astra}"

# Where this script itself is. Both layouts put jobs/ and codex-jobs/ side by side
# - <repo>/Tools/Host/ tracked, <workspace>/tools/ deployed - so the helpers and the
# resolver are reachable relatively, and this script works from any root. The two
# absolute paths stay on as a fallback: losing the helper lookup is how this script
# silently produced no report for three days.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || { echo "cannot locate myself" >&2; exit 2; }

HELPERS=""
for _h in "$HERE/../jobs" "C:/NSC/tools/jobs" "C:/nscrev/job-tools"; do
  [ -f "$_h/resolve_codex.py" ] && { HELPERS="$(cd "$_h" && pwd)"; break; }
done
[ -n "$HELPERS" ] || { echo "cannot find resolve_codex.py in $HERE/../jobs, C:/NSC/tools/jobs or C:/nscrev/job-tools" >&2; exit 2; }

# Roots from the shared resolver rather than spelled here. It derives them from where
# the tools are installed, so deploying under a different root moves them along.
PATHS="$HELPERS/../nsc_paths.py"
[ -f "$PATHS" ] || { echo "cannot find nsc_paths.py beside $HELPERS" >&2; exit 2; }
ROOT="$(python -B "$PATHS" --get work)/codex-jobs" || { echo "cannot resolve the work root" >&2; exit 2; }
REPO="$(python -B "$PATHS" --get canonical)" || { echo "cannot resolve the canonical checkout" >&2; exit 2; }
CLONE="$ROOT/$JOB"; PROMPT="$ROOT/$JOB.prompt.md"; REPORT="$ROOT/$JOB.report.md"

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
