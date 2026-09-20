#!/usr/bin/env bash
set -euo pipefail

claude -p \
  --safe-mode \
  --model 'claude-fable-5' \
  --max-turns 80 \
  --permission-mode dontAsk \
  --input-format text \
  --output-format json \
  --no-session-persistence \
  --setting-sources user,project \
  --tools Read,Glob,Grep \
  --allowedTools Read Glob Grep \
  --disallowedTools Bash,Edit,Write,NotebookEdit,WebSearch,WebFetch \
  < '/workspace/Pipeline/ArchitectureReview/outputs/targeted/nsc020-downstream-debug-20260829-013513/prompt.txt' \
  > '/workspace/Pipeline/ArchitectureReview/outputs/targeted/nsc020-downstream-debug-20260829-013513/claude-response.json'