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
# Exit: 0 success; 2 setup refused; 3 no result; 4 provider failed; 5 stale result;
#       6 empty result; 7 the result is fresh and non-empty but is not a finished
#       closure review - malformed JSON, a declared incomplete, or a review of a
#       different task or a different contract than the host supplied;
#       8 the contract file changed after this script selected it;
#       9 the provider refused the call - a usage or rate limit. Reserved, not
#         returned here: only the Claude launcher can observe it, and the number
#         is held so one code never means two things across the two launchers;
#      10 the review finished but its evidence could not be recorded under this
#         job name. Also reserved rather than returned: this script refuses
#         existing evidence before it launches, so it cannot reach the case.
#
# 2 carries a promise the other codes do not: NOTHING WAS LAUNCHED. Every site
# that returns it is above the `codex exec` line, so a caller reading 2 knows the
# job name is free and nothing was spent. Do not add a 2 below that line.
#
# 2026-09-21: the reviewer now declares its verdict in one JSON object rather
# than in prose. $JOB.result.json is what the provider wrote and the only
# decision source; $JOB.report.md is derived from it after validation, for
# people. Nothing falls back to the Markdown recogniser, which lives on as
# jobs/legacy_closure_markdown.py for reading reports written before today.
set -u

JOB="$1"; TASK="$2"; COMMIT="$3"; PREV="$4"; shift 4
MODEL="${NSC_CODEX_MODEL:-gpt-6-astra}"

# Where this script itself is. Both layouts put jobs/ and codex-jobs/ side by side
# - <repo>/Tools/Host/ tracked, <workspace>/tools/ deployed - so the helpers and the
# resolver are reachable relatively, and this script works from any root. The two
# absolute paths stay on as a fallback: losing the helper lookup is how this script
# silently produced no report for three days.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || { echo "cannot locate myself" >&2; exit 2; }

# The helpers are the ones beside THIS script, and only those. The two absolute
# fallbacks that used to follow - C:/NSC/tools/jobs and C:/nscrev/job-tools - are
# removed: a launcher that reaches a different installation's Python for its
# checks is exactly the "old-path fallback" the protocol forbids, and under the
# new record it could pair a new runner with a validator that has never heard of
# a job record. The matching family or nothing.
HELPERS="$HERE/../jobs"
[ -f "$HELPERS/resolve_codex.py" ] || {
  echo "cannot find resolve_codex.py beside this script at $HELPERS; this launcher" >&2
  echo "runs only against its own checkout or deployment, never a stale one" >&2
  exit 2; }
HELPERS="$(cd "$HELPERS" && pwd)"

# Roots from the shared resolver rather than spelled here. It derives them from where
# the tools are installed, so deploying under a different root moves them along.
PATHS="$HELPERS/../nsc_paths.py"
[ -f "$PATHS" ] || { echo "cannot find nsc_paths.py beside $HELPERS" >&2; exit 2; }
ROOT="$(python -B "$PATHS" --get work)/codex-jobs" || { echo "cannot resolve the work root" >&2; exit 2; }
REPO="$(python -B "$PATHS" --get canonical)" || { echo "cannot resolve the canonical checkout" >&2; exit 2; }
CLONE="$ROOT/$JOB"; PROMPT="$ROOT/$JOB.prompt.md"; REPORT="$ROOT/$JOB.report.md"
# The reviewer's own output is now one JSON object, and it is the only decision
# source. RESULT holds it verbatim. REPORT is DERIVED from it after validation -
# a human view, written by the checker, that no tool reads a verdict out of.
RESULT="$ROOT/$JOB.result.json"

CODEX="$(python -B "$HELPERS/resolve_codex.py")" || {
  echo "no usable codex binary; see above" >&2; exit 2; }

[ -f "$PROMPT" ] || { echo "missing prompt $PROMPT" >&2; exit 2; }
[ -e "$CLONE" ] && { echo "clone exists $CLONE" >&2; exit 2; }

# The clone check above reserves the working DIRECTORY. It says nothing about the
# previous run's evidence, and this script used to `mv` a stale result and report
# aside and then let the checker overwrite the record - so a second run on the
# same job name replaced a completed `revise` with a `commit_contract` and left
# nothing saying it had happened (Astra MJ-P3-03-C, reproduced here against the
# unedited script). Refuse instead, before anything is created, through the same
# function the Claude launcher uses rather than a second implementation in Bash.
python -B "$HELPERS/closure_record.py" --refuse-existing "$RESULT" || exit 2

git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true "$REPO" "$CLONE" || exit 2
git -C "$CLONE" checkout -q --detach "$COMMIT^" || exit 2
git -C "$REPO" show "$COMMIT:Tasks/$TASK.yaml" > "$CLONE/REVISED_CONTRACT.json" || exit 2
git -C "$REPO" show "$PREV:Tasks/$TASK.yaml" > "$CLONE/PREVIOUS_CONTRACT.json" || exit 2

# The bytes THIS script chose, hashed before any provider can see them. Without
# it the checker hashed whatever was on disk afterwards, so a provider that
# rewrote the fixture and reviewed its own version produced a self-consistent
# approval of a contract nobody selected (Astra MJ-P3-03-B). Hashed by the same
# helper the record uses, so there is one implementation of "the sha256 of these
# exact bytes" rather than a shell version beside it.
CONTRACT_SHA="$(python -B "$HELPERS/closure_record.py" --sha256 "$CLONE/REVISED_CONTRACT.json")" \
  || { echo "cannot hash the selected contract" >&2; exit 2; }
for extra in "$@"; do
  git -C "$REPO" show "$COMMIT:$extra" > "$CLONE/REVISED_$(basename "$extra")" || exit 2
done

STARTED_AT="$(python -B -c 'import time; print(time.time())')"

echo "[START] $JOB $(date -u +%FT%TZ) clone at $(git -C "$CLONE" rev-parse --short HEAD), revised $(git -C "$REPO" rev-parse --short "$COMMIT"), previous $(git -C "$REPO" rev-parse --short "$PREV")"
echo "[CODEX] $CODEX ($("$CODEX" --version 2>&1 | head -1)) model=$MODEL"

"$CODEX" exec --sandbox read-only --cd "$CLONE" --skip-git-repo-check \
  -m "$MODEL" -c model_reasoning_effort=high --color never \
  --output-last-message "$RESULT" - < "$PROMPT" > "$ROOT/$JOB.log" 2>&1
rc=$?
echo "[DONE] $JOB provider exit $rc $(date -u +%FT%TZ)"

# Guards the RESULT now, not the derived view: provider exit status, freshness
# and emptiness are properties of what the provider actually wrote. Provider
# failure still wins even when the bytes happen to be valid JSON.
python -B "$HELPERS/check_job_result.py" \
  --rc "$rc" --report "$RESULT" --started-at "$STARTED_AT" \
  --verdict-grep '"recommendation"'
status=$?

if [ "$status" -ne 0 ]; then
  echo "[FAILED] $JOB - last lines of the log:" >&2
  tail -5 "$ROOT/$JOB.log" >&2
  exit "$status"
fi

# The generic checker answers whether this run produced a fresh artifact, and it
# answers correctly. It does not know what a CLOSURE review has to contain, and
# should not - its contract is deliberately narrower. So a fresh, non-empty report
# reading "I could not review this task. Please retry later." satisfied every check
# above and this script called it a success. Reproduced by Main-Commit-Review
# 20260920-180652, finding 2.
#
# A `revise` recommendation still exits 0: the review ran and reached a negative
# conclusion. Treating a rejection as a failed run is how a verdict gets retried
# like a timeout.
# --contract binds the verdict to the exact bytes the reviewer was given.
# Without it any 16 hex characters satisfied the identity line, so a review of a
# DIFFERENT revision read as a clean pass (Astra release review of 17cf1f4c5).
# --provider/--exit-code/--started-at make this the boundary that publishes the
# job record, LAST, after every check and after the view is written. The record
# is what a downstream consumer reads to know this job finished; without it,
# apply_contract refuses the review rather than assuming it was hand-carried.
# None of those checks is repeated in Bash.
python -B "$HELPERS/check_closure_report.py" --result "$RESULT" \
  --contract "$CLONE/REVISED_CONTRACT.json" --contract-sha256 "$CONTRACT_SHA" \
  --task "$TASK" --report-out "$REPORT" \
  --provider codex --exit-code "$rc" --started-at "$STARTED_AT"
closure=$?
if [ "$closure" -eq 8 ]; then
  echo "[TAMPERED] $JOB - the contract changed after this script selected it" >&2
  exit 8
fi
if [ "$closure" -eq 2 ]; then
  # The checker refuses an unreadable input, a bad argument combination or an
  # existing record with 2, which is correct when a person runs it directly. By
  # the time THIS script calls it the provider has run, and exiting 2 here would
  # tell a caller nothing was launched and the job name is free - so a retry
  # would pay for a second call and then collide. Translated, not renumbered:
  # the checker's own contract is fine.
  echo "[UNRECORDED] $JOB - the provider ran, but the checker refused its inputs" >&2
  exit 10
fi
if [ "$closure" -ne 0 ]; then
  echo "[INCOMPLETE] $JOB - the provider succeeded but did not finish the review" >&2
  exit "$closure"
fi
exit 0
