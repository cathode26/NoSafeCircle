#!/usr/bin/env bash
set -euo pipefail

MODEL='claude-fable-5'
OUT='/workspace/Pipeline/ArchitectureReview/outputs/targeted/generic-get-work-20260829-191512'

run_agent() {
    local prompt_path="$1"
    local json_path="$2"
    local markdown_path="$3"
    local max_turns="$4"
    local stderr_path="${json_path%.json}.stderr.log"

    echo
    echo "============================================================"
    echo "Claude Fable 5 review: $(basename "$markdown_path")"
    echo "============================================================"

    if ! claude -p \
        --model "$MODEL" \
        --max-turns "$max_turns" \
        --permission-mode dontAsk \
        --input-format text \
        --output-format json \
        --allowedTools "Read,Glob,Grep" \
        --disallowedTools "Bash,Edit,Write,NotebookEdit,WebSearch,WebFetch" \
        < "$prompt_path" \
        > "$json_path" \
        2> "$stderr_path"; then
        cat "$stderr_path" >&2
        exit 1
    fi

    jq -e '.result | type == "string" and length > 0' "$json_path" >/dev/null
    jq -r '.result' "$json_path" > "$markdown_path"
    echo "Completed: $(basename "$markdown_path")"
}

run_agent "$OUT/01-authority.prompt.md" "$OUT/01-authority.json" "$OUT/01-authority.md" 80
run_agent "$OUT/02-concurrency.prompt.md" "$OUT/02-concurrency.json" "$OUT/02-concurrency.md" 80
run_agent "$OUT/03-operator.prompt.md" "$OUT/03-operator.json" "$OUT/03-operator.md" 70
run_agent "$OUT/04-adversary.prompt.md" "$OUT/04-adversary.json" "$OUT/04-adversary.md" 80
run_agent "$OUT/05-synthesis.prompt.md" "$OUT/05-synthesis.json" "$OUT/FINAL-SYNTHESIS.md" 110

echo
echo "FINAL_SYNTHESIS=$OUT/FINAL-SYNTHESIS.md"