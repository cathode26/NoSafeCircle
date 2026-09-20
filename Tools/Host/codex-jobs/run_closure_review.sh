#!/usr/bin/env bash
# Cumulative closure review of a task-contract revision (templates/contract-closure-review-prompt.md).
# Usage: run_closure_review.sh <job> <TASK> <revision-commit> <previous-checked-commit> [extra repo paths changed in the same commit...]
#
# 2026-09-20 (Pipeline Maintainer): this called a bare `codex.exe`, which PATH resolves to
# 0.151.0 under .../Programs/OpenAI/Codex/bin. That build refuses the `gpt-6-astra` default in
# ~/.codex/config.toml with invalid_request_error and exits 1, writing no report - so the GER
# Agent's live contract check produced nothing. Three changes:
#   * resolve the binary by VERSION among bin folders that actually contain it, never by PATH
#     and never by a hardcoded hash folder (those change on every update, and at least one
#     sibling folder contains no codex.exe at all - the mtime trap ask_astra.py:260 documents);
#   * pass the model EXPLICITLY, so a config default cannot silently decide it;
#   * check the report is non-empty before claiming success - exit code alone is not evidence
#     (runbook rule 25).
JOB="$1"; TASK="$2"; COMMIT="$3"; PREV="$4"; shift 4
ROOT=C:/nscrev/codex-jobs; CLONE="$ROOT/$JOB"; PROMPT="$ROOT/$JOB.prompt.md"
REPO=C:/NSC/NSC/NoSafeCircle
MODEL="${NSC_CODEX_MODEL:-gpt-6-astra}"
BIN_ROOT="${NSC_CODEX_BIN_ROOT:-C:/Users/$USERNAME/AppData/Local/OpenAI/Codex/bin}"

# --- resolve the newest codex.exe by version, among folders that actually hold one ---
find_codex() {
  if [ -n "$NSC_CODEX_EXE" ]; then
    [ -x "$NSC_CODEX_EXE" ] || { echo "NSC_CODEX_EXE does not exist: $NSC_CODEX_EXE" >&2; return 1; }
    printf '%s\n' "$NSC_CODEX_EXE"; return 0
  fi
  local best="" best_key="" exe ver key
  for exe in "$BIN_ROOT"/*/codex.exe; do
    [ -f "$exe" ] || continue                      # skip hash folders with no binary
    ver="$("$exe" --version 2>/dev/null | head -1 | grep -oE '[0-9]+(\.[0-9]+)*' | head -1)"
    [ -n "$ver" ] || continue
    key="$(printf '%s' "$ver" | awk -F. '{printf "%05d%05d%05d", $1, $2, $3}')"
    if [ -z "$best_key" ] || [ "$key" \> "$best_key" ]; then best_key="$key"; best="$exe"; fi
  done
  [ -n "$best" ] || { echo "no codex.exe found under $BIN_ROOT" >&2; return 1; }
  printf '%s\n' "$best"
}

CODEX="$(find_codex)" || exit 2

[ -f "$PROMPT" ] || { echo "missing prompt $PROMPT"; exit 2; }
[ -e "$CLONE" ] && { echo "clone exists $CLONE"; exit 2; }
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true "$REPO" "$CLONE" || exit 2
git -C "$CLONE" checkout -q --detach "$COMMIT^" || exit 2
git -C "$REPO" show "$COMMIT:Tasks/$TASK.yaml" > "$CLONE/REVISED_CONTRACT.json" || exit 2
git -C "$REPO" show "$PREV:Tasks/$TASK.yaml" > "$CLONE/PREVIOUS_CONTRACT.json" || exit 2
for extra in "$@"; do git -C "$REPO" show "$COMMIT:$extra" > "$CLONE/REVISED_$(basename "$extra")" || exit 2; done

echo "[START] $JOB $(date -u +%FT%TZ) clone at $(git -C "$CLONE" rev-parse --short HEAD), revised $(git -C "$REPO" rev-parse --short "$COMMIT"), previous $(git -C "$REPO" rev-parse --short "$PREV")"
echo "[CODEX] $CODEX ($("$CODEX" --version 2>&1 | head -1)) model=$MODEL"

"$CODEX" exec --sandbox read-only --cd "$CLONE" --skip-git-repo-check \
  -m "$MODEL" -c model_reasoning_effort=high --color never \
  --output-last-message "$ROOT/$JOB.report.md" - < "$PROMPT" > "$ROOT/$JOB.log" 2>&1
rc=$?
echo "[DONE] $JOB exit $rc $(date -u +%FT%TZ)"

# Exit code alone is not evidence - require the artifact (runbook rule 25).
if [ ! -s "$ROOT/$JOB.report.md" ]; then
  echo "[FAILED] $JOB wrote no report. Last lines of the log:" >&2
  tail -5 "$ROOT/$JOB.log" >&2
  exit 3
fi

grep -i "Final recommendation" "$ROOT/$JOB.report.md"
