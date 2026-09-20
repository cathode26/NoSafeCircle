#!/usr/bin/env bash
# Pipeline Maintainer Agent: host Codex adversarial review (nsc-codex-jobs-guide.md section 4.2, host recipe).
# Usage: run-codex-review.sh <job-name> <source-clone> <head-sha> <author-report>
set -u
JOB="$1"; SRC="$2"; HEAD_SHA="$3"; REPORT="$4"
ROOT=C:/nscrev/codex-jobs
CLONE="$ROOT/$JOB"
PROMPT="$ROOT/$JOB.prompt.md"
LOG="$ROOT/$JOB.log"
CODEX="C:/Users/VincentLiguori/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe"
test -f "$PROMPT" || { echo "missing prompt $PROMPT"; exit 2; }
test ! -e "$CLONE" || { echo "job clone exists: $CLONE"; exit 2; }
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true "$SRC" "$CLONE" || exit 1
git -C "$CLONE" remote set-url --push origin DISABLED
git -C "$CLONE" checkout -q --detach "$HEAD_SHA" || exit 1
cp "$ROOT/templates/verdict.schema.json" "$CLONE/CODEX_VERDICT_SCHEMA.json"
cp "$REPORT" "$CLONE/CODEX_AUTHOR_REPORT.md"
printf '/CODEX_VERDICT_SCHEMA.json\n/CODEX_AUTHOR_REPORT.md\n/CODEX_VERDICT.json\n/codex-tmp/\n' >> "$CLONE/.git/info/exclude"
mkdir -p "$CLONE/codex-tmp"
echo "[start] $(date -u +%FT%TZ) job=$JOB head=$HEAD_SHA" > "$LOG"
TEMP="$CLONE/codex-tmp" TMP="$CLONE/codex-tmp" "$CODEX" exec --sandbox workspace-write --cd "$CLONE" --skip-git-repo-check \
  -c model_reasoning_effort=high --color never \
  --output-schema "$CLONE/CODEX_VERDICT_SCHEMA.json" --output-last-message "$CLONE/CODEX_VERDICT.json" - \
  < "$PROMPT" >> "$LOG" 2>&1
rc=$?
echo "[end] $(date -u +%FT%TZ) rc=$rc" >> "$LOG"
echo "rc=$rc verdict_file=$CLONE/CODEX_VERDICT.json"
python -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print('VERDICT', d.get('verdict'), '| findings', len(d.get('findings',[])))" "$CLONE/CODEX_VERDICT.json" 2>/dev/null || echo "no valid verdict"
