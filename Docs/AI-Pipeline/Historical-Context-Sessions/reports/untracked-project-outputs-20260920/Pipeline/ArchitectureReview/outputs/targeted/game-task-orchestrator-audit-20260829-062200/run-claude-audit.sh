#!/usr/bin/env bash
set -euo pipefail
PROMPT_PATH="${1:?prompt path required}"
RESPONSE_PATH="${2:?response path required}"
MAX_TURNS="${3:?max turns required}"
BASE="${RESPONSE_PATH%.json}"
claude --version > "${BASE}.claude-version.txt"
claude -p \
  --safe-mode \
  --model "claude-fable-5" \
  --effort "max" \
  --max-turns "$MAX_TURNS" \
  --permission-mode dontAsk \
  --input-format text \
  --output-format json \
  --no-session-persistence \
  --no-chrome \
  --disable-slash-commands \
  --tools "Read,Glob,Grep" \
  --allowedTools Read Glob Grep \
  --disallowedTools Bash Edit Write NotebookEdit WebSearch WebFetch "mcp__*" \
  < "$PROMPT_PATH" > "$RESPONSE_PATH" 2> "${BASE}.stderr.log"
