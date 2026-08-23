from __future__ import annotations

import os
from pathlib import Path
import tempfile

# Keep the live smoke test intentionally cheap while exercising the exact
# structured-output invocation used by the real architecture reviewers.
os.environ.setdefault("ARCH_REVIEW_REASONING_EFFORT", "low")

import architecture_review_codex as codex_review


SMOKE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "goal": {"type": "string"},
    },
    "required": ["ok", "goal"],
}


def main() -> int:
    if os.environ.get("NSC_RUN_OPENAI_CODEX_SMOKE") != "1":
        print("codex_provider_live_smoke_test: SKIP (set NSC_RUN_OPENAI_CODEX_SMOKE=1)")
        return 0
    codex_review.base.OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="live-smoke-", dir=codex_review.base.OUTPUT_ROOT) as text:
        codex_review.configure_invocation_run_root(Path(text))
        result = codex_review.invoke_codex_agent(
            agent_name="Codex Provider Live Smoke Test",
            model=codex_review.MODEL_POOL[0],
            prompt=(
                "Read AI_PIPELINE.md and, if needed, Docs/AI-Pipeline/START_HERE.md. "
                "Return ok=true and a one-sentence description of the pipeline goal."
            ),
            schema=SMOKE_SCHEMA,
            max_turns=1,
        )

    structured = result["result"]
    assert structured["ok"] is True
    assert isinstance(structured["goal"], str)
    assert structured["goal"].strip()
    assert result["provider"] == "openai-codex"
    assert result["reasoning_effort"] == "low"

    print("codex_provider_live_smoke_test: PASS")
    print(structured["goal"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
