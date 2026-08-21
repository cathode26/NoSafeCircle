from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import architecture_review as base


# Preserve the shared prompt builder before configure_base_runner replaces it.
_shared_common_review_prompt = base.common_review_prompt


# Codex/ChatGPT defaults. The shared architecture-review schemas, prompts,
# orchestration, output layout, and anti-anchoring rules remain in
# architecture_review.py so the Claude and Codex runners evaluate the same
# architecture contract.
MODEL_POOL = [
    value.strip()
    for value in os.environ.get("ARCH_REVIEW_MODELS", "gpt-5.6-sol").split(",")
    if value.strip()
]
SYNTHESIS_MODEL = (
    os.environ.get("ARCH_REVIEW_SYNTHESIS_MODEL", "gpt-5.6-sol").strip()
    or "gpt-5.6-sol"
)
ADVERSARY_MODEL = (
    os.environ.get("ARCH_REVIEW_ADVERSARY_MODEL", "gpt-5.6-sol").strip()
    or "gpt-5.6-sol"
)

REVIEW_REASONING_EFFORT = (
    os.environ.get("ARCH_REVIEW_REASONING_EFFORT", "high").strip() or "high"
)
SYNTHESIS_REASONING_EFFORT = (
    os.environ.get("ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT", "xhigh").strip()
    or "xhigh"
)
ADVERSARY_REASONING_EFFORT = (
    os.environ.get("ARCH_REVIEW_ADVERSARY_REASONING_EFFORT", "xhigh").strip()
    or "xhigh"
)

VALID_REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}

if not MODEL_POOL:
    raise RuntimeError("ARCH_REVIEW_MODELS must contain at least one model.")

for name, value in {
    "ARCH_REVIEW_REASONING_EFFORT": REVIEW_REASONING_EFFORT,
    "ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT": SYNTHESIS_REASONING_EFFORT,
    "ARCH_REVIEW_ADVERSARY_REASONING_EFFORT": ADVERSARY_REASONING_EFFORT,
}.items():
    if value not in VALID_REASONING_EFFORTS:
        raise RuntimeError(
            f"{name} must be one of {sorted(VALID_REASONING_EFFORTS)}, got {value!r}."
        )


def reasoning_effort_for(agent_name: str) -> str:
    if agent_name == "Architecture Synthesis":
        return SYNTHESIS_REASONING_EFFORT
    if agent_name == "Adversarial Synthesis Critic":
        return ADVERSARY_REASONING_EFFORT
    return REVIEW_REASONING_EFFORT


def codex_common_review_prompt(*, role_name: str, role_focus: str, frozen_head: str) -> str:
    prompt = _shared_common_review_prompt(
        role_name=role_name,
        role_focus=role_focus,
        frozen_head=frozen_head,
    )
    return prompt.replace(
        "Inspect the repository directly using Read/Glob/Grep.",
        "Inspect the repository directly using read-only shell/file inspection commands such as cat, sed, find, rg, and git show/log/diff as needed.",
    )


def invoke_codex_agent(
    *,
    agent_name: str,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    max_turns: int,
) -> dict[str, Any]:
    """Run one isolated Codex exec against the Docker-enforced read-only repo.

    `max_turns` is retained only for interface compatibility with the original
    Claude runner. Codex exec does not expose Claude's max-turn control; the
    outer subprocess timeout remains the hard runtime bound.
    """

    _ = max_turns
    effort = reasoning_effort_for(agent_name)

    with tempfile.TemporaryDirectory(prefix="nsc-arch-review-") as temp_dir_text:
        temp_dir = Path(temp_dir_text)
        schema_path = temp_dir / "schema.json"
        final_path = temp_dir / "final.json"
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False),
            encoding="utf-8",
        )

        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "danger-full-access",
            "--model",
            model,
            "-c",
            f"model_reasoning_effort={effort}",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(final_path),
            "--color",
            "never",
            "-",
        ]

        started = time.monotonic()
        print(f"Starting: {agent_name} [{model}, reasoning={effort}]")

        try:
            process = subprocess.run(
                command,
                cwd=base.ROOT,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=base.REVIEW_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{agent_name} [{model}] timed out after {base.REVIEW_TIMEOUT}s."
            ) from exc

        duration = round(time.monotonic() - started, 2)

        if process.returncode != 0:
            diagnostics = (process.stderr or process.stdout or "").strip()
            raise RuntimeError(
                f"{agent_name} [{model}] failed with exit code {process.returncode}:\n"
                f"{diagnostics[-12000:]}"
            )

        if not final_path.exists():
            diagnostics = (process.stderr or process.stdout or "").strip()
            raise RuntimeError(
                f"{agent_name} [{model}] completed without writing its final message.\n"
                f"{diagnostics[-12000:]}"
            )

        final_text = final_path.read_text(encoding="utf-8", errors="replace").strip()
        try:
            structured = json.loads(final_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{agent_name} [{model}] returned invalid structured JSON:\n"
                f"{final_text[:4000]}"
            ) from exc

        if not isinstance(structured, dict):
            raise RuntimeError(
                f"{agent_name} [{model}] structured output was not a JSON object."
            )

    print(f"Completed: {agent_name} [{model}] in {duration}s")
    return {
        "agent": agent_name,
        "provider": "openai-codex-chatgpt",
        "model": model,
        "reasoning_effort": effort,
        "duration_seconds": duration,
        "result": structured,
    }


def configure_base_runner() -> None:
    # Keep all shared orchestration identical while swapping only provider/model
    # execution details and the one Claude-specific repository-inspection phrase.
    base.MODEL_POOL = MODEL_POOL
    base.SYNTHESIS_MODEL = SYNTHESIS_MODEL
    base.ADVERSARY_MODEL = ADVERSARY_MODEL
    base.common_review_prompt = codex_common_review_prompt
    base.invoke_read_only_agent = invoke_codex_agent


configure_base_runner()


if __name__ == "__main__":
    raise SystemExit(base.main())
