from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REVIEW_ROOT = ROOT / "Pipeline" / "ArchitectureReview"
OUTPUT_ROOT = REVIEW_ROOT / "outputs"

MAX_WORKERS = int(os.environ.get("ARCH_REVIEW_MAX_WORKERS", "8"))
REVIEW_TIMEOUT = int(os.environ.get("ARCH_REVIEW_TIMEOUT_SECONDS", "1800"))
REVIEW_MAX_TURNS = int(os.environ.get("ARCH_REVIEW_MAX_TURNS", "32"))
SYNTHESIS_MAX_TURNS = int(os.environ.get("ARCH_REVIEW_SYNTHESIS_MAX_TURNS", "36"))
ADVERSARY_MAX_TURNS = int(os.environ.get("ARCH_REVIEW_ADVERSARY_MAX_TURNS", "30"))
MODEL_POOL = [
    x.strip()
    for x in os.environ.get("ARCH_REVIEW_MODELS", "opus,sonnet").split(",")
    if x.strip()
]
SYNTHESIS_MODEL = os.environ.get("ARCH_REVIEW_SYNTHESIS_MODEL", "opus").strip() or "opus"
ADVERSARY_MODEL = os.environ.get("ARCH_REVIEW_ADVERSARY_MODEL", "opus").strip() or "opus"

if not MODEL_POOL:
    raise RuntimeError("ARCH_REVIEW_MODELS must contain at least one model.")

CLAUDE_DISALLOWED_TOOLS = (
    "Edit,Write,NotebookEdit,Bash,WebFetch,WebSearch,Task,TaskOutput,"
    "EnterPlanMode,ExitPlanMode,AskUserQuestion"
)

ARCHITECTURE_DOCS = [
    "AI_PIPELINE.md",
    "Docs/AI-Pipeline/START_HERE.md",
    "Docs/AI-Pipeline/CURRENT_STATE.md",
    "Docs/AI-Pipeline/00_MASTER_CONTEXT.md",
    "Docs/AI-Pipeline/01_MILESTONE_TASK_GRAPH.md",
    "Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md",
    "Docs/AI-Pipeline/03_SUPERVISOR_GIT_GITHUB_CONTEXT.md",
    "Docs/AI-Pipeline/04_EXECUTION_GER_VALIDATION_CONTEXT.md",
    "Docs/AI-Pipeline/05_CONTINUOUS_AUTONOMY_CONTEXT.md",
    "Docs/AI-Pipeline/DECISIONS.md",
]

ROLE_SPECS = [
    {
        "key": "game_technical_director",
        "name": "Pragmatic Game Technical Director",
        "focus": (
            "Judge whether this architecture is a sound production approach for actually "
            "finishing No Safe Circle. Examine subsystem boundaries, engineering leverage, "
            "whether infrastructure is displacing game development, and what an experienced "
            "technical director would retain, replace, or build next."
        ),
    },
    {
        "key": "workflow_systems_architect",
        "name": "Workflow and Distributed-Systems Architect",
        "focus": (
            "Audit durable state ownership, immutable versus mutable state, idempotence, "
            "recovery, retries, lifecycle transitions, reconciliation-to-task deltas, "
            "Git/GitHub synchronization, concurrency assumptions, and duplicated sources "
            "of truth. Look for impossible or ambiguous state transitions."
        ),
    },
    {
        "key": "llm_reliability_engineer",
        "name": "LLM Reliability Engineer",
        "focus": (
            "Audit model boundaries, correlated failures, self-evaluation risks, prompt "
            "anchoring, verification independence, reconciliation instability as the GDD "
            "evolves, refinement loops, human authority, token/cost behavior, and whether "
            "deterministic checks are placed at the right boundaries."
        ),
    },
    {
        "key": "unity_production_engineer",
        "name": "Unity Production Engineer",
        "focus": (
            "Evaluate whether the architecture survives real Unity production: scenes, "
            "prefabs, .meta/GUIDs, serialized state, editor-only operations, runtime evidence, "
            "PlayMode/EditMode testing, batch mode, asset conflicts, worktrees, shared files, "
            "and human editor/integration requirements."
        ),
    },
    {
        "key": "yagni_complexity_critic",
        "name": "YAGNI and Complexity Critic",
        "focus": (
            "Assume every subsystem must earn its existence. Identify machinery that solves "
            "hypothetical rather than observed failures, overlapping abstractions, premature "
            "generalization, and the smallest architecture that could deliver most of the "
            "autonomy benefit without sacrificing correctness."
        ),
    },
    {
        "key": "autonomous_agent_architect",
        "name": "Autonomous-Agent Architect",
        "focus": (
            "Evaluate the proposed agent hierarchy and control loop: reconciliation, work graph, "
            "progressive decomposition, artifact authority, bounded workers, GER, supervisor, "
            "verification, and continuous autonomy. Determine whether these abstractions compose "
            "into a coherent autonomous development system or should be reorganized."
        ),
    },
    {
        "key": "adversarial_qa",
        "name": "Adversarial QA and Failure-Mode Reviewer",
        "focus": (
            "Try to break the architecture. Find paths that can corrupt state, silently omit work, "
            "approve incorrect work, deadlock, loop forever, drift from canon, lose recovery data, "
            "mis-handle GDD changes, or become confidently wrong. Prefer concrete failure sequences "
            "grounded in repository evidence."
        ),
    },
    {
        "key": "game_producer",
        "name": "Game Producer and Throughput Reviewer",
        "focus": (
            "Judge the architecture as an investment. Estimate where human intervention remains, "
            "which interventions are worth automating, whether this can turn weeks of development "
            "into days, what must be proven soon, and whether the next slice should be infrastructure "
            "or actual game production using the existing pipeline."
        ),
    },
]

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "architecture_summary": {"type": "string"},
        "overall_verdict": {
            "type": "string",
            "enum": [
                "sound_high_leverage",
                "sound_overbuilt",
                "partially_unsound",
                "fundamentally_wrong_approach",
                "insufficient_evidence",
            ],
        },
        "verdict_reason": {"type": "string"},
        "strong_decisions": {"type": "array", "items": {"type": "string"}},
        "structural_flaws": {"type": "array", "items": {"type": "string"}},
        "observed_failure_solutions": {"type": "array", "items": {"type": "string"}},
        "hypothetical_failure_solutions": {"type": "array", "items": {"type": "string"}},
        "overengineering": {"type": "array", "items": {"type": "string"}},
        "missing_components": {"type": "array", "items": {"type": "string"}},
        "state_and_authority_concerns": {"type": "array", "items": {"type": "string"}},
        "gdd_iteration_concerns": {"type": "array", "items": {"type": "string"}},
        "throughput_assessment": {"type": "string"},
        "human_intervention_points": {"type": "array", "items": {"type": "string"}},
        "next_slice": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "why": {"type": "string"},
                "deliverables": {"type": "array", "items": {"type": "string"}},
                "proof_of_value": {"type": "string"},
            },
            "required": ["title", "why", "deliverables", "proof_of_value"],
        },
        "do_not_build_yet": {"type": "array", "items": {"type": "string"}},
        "alternative_architecture": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "needed": {"type": "boolean"},
                "description": {"type": "string"},
                "why_better": {"type": "string"},
            },
            "required": ["needed", "description", "why_better"],
        },
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string"},
                    "observation": {"type": "string"},
                },
                "required": ["path", "observation"],
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "biggest_uncertainty": {"type": "string"},
    },
    "required": [
        "architecture_summary",
        "overall_verdict",
        "verdict_reason",
        "strong_decisions",
        "structural_flaws",
        "observed_failure_solutions",
        "hypothetical_failure_solutions",
        "overengineering",
        "missing_components",
        "state_and_authority_concerns",
        "gdd_iteration_concerns",
        "throughput_assessment",
        "human_intervention_points",
        "next_slice",
        "do_not_build_yet",
        "alternative_architecture",
        "evidence",
        "confidence",
        "biggest_uncertainty",
    ],
}

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_verdict": {"type": "string"},
        "architecture_classification": {
            "type": "string",
            "enum": [
                "sound_high_leverage",
                "sound_overbuilt",
                "partially_unsound",
                "fundamentally_wrong_approach",
                "insufficient_evidence",
            ],
        },
        "preserve": {"type": "array", "items": {"type": "string"}},
        "change_or_replace": {"type": "array", "items": {"type": "string"}},
        "defer_or_delete": {"type": "array", "items": {"type": "string"}},
        "major_disagreements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "issue": {"type": "string"},
                    "positions": {"type": "array", "items": {"type": "string"}},
                    "assessment": {"type": "string"},
                },
                "required": ["issue", "positions", "assessment"],
            },
        },
        "gdd_iteration_strategy": {"type": "string"},
        "minimum_viable_architecture": {"type": "string"},
        "recommended_next_slice": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "why": {"type": "string"},
                "deliverables": {"type": "array", "items": {"type": "string"}},
                "success_test": {"type": "string"},
            },
            "required": ["title", "why", "deliverables", "success_test"],
        },
        "expected_autonomy_and_throughput": {"type": "string"},
        "critical_risks": {"type": "array", "items": {"type": "string"}},
        "decision_rationale": {"type": "string"},
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "executive_verdict",
        "architecture_classification",
        "preserve",
        "change_or_replace",
        "defer_or_delete",
        "major_disagreements",
        "gdd_iteration_strategy",
        "minimum_viable_architecture",
        "recommended_next_slice",
        "expected_autonomy_and_throughput",
        "critical_risks",
        "decision_rationale",
        "evidence_gaps",
    ],
}

ADVERSARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "synthesis_weaknesses": {"type": "array", "items": {"type": "string"}},
        "strongest_counter_case": {"type": "string"},
        "hidden_assumptions": {"type": "array", "items": {"type": "string"}},
        "ignored_minority_arguments": {"type": "array", "items": {"type": "string"}},
        "failure_if_followed": {"type": "array", "items": {"type": "string"}},
        "better_next_step_if_any": {"type": "string"},
        "what_would_change_my_mind": {"type": "array", "items": {"type": "string"}},
        "final_assessment": {
            "type": "string",
            "enum": ["synthesis_holds", "synthesis_needs_revision", "synthesis_is_unsafe"],
        },
        "reason": {"type": "string"},
    },
    "required": [
        "synthesis_weaknesses",
        "strongest_counter_case",
        "hidden_assumptions",
        "ignored_minority_arguments",
        "failure_if_followed",
        "better_next_step_if_any",
        "what_would_change_my_mind",
        "final_assessment",
        "reason",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not resolve git HEAD.")
    return result.stdout.strip()


def git_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not read git status.")
    return bool(result.stdout.strip())


def invoke_read_only_agent(
    *,
    agent_name: str,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    max_turns: int,
) -> dict[str, Any]:
    command = [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--disallowedTools",
        CLAUDE_DISALLOWED_TOOLS,
        "--json-schema",
        json.dumps(schema, separators=(",", ":"), ensure_ascii=False),
        "--input-format",
        "text",
    ]

    started = time.monotonic()
    print(f"Starting: {agent_name} [{model}]")
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=REVIEW_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{agent_name} [{model}] timed out after {REVIEW_TIMEOUT}s.") from exc

    duration = round(time.monotonic() - started, 2)
    if process.returncode != 0:
        raise RuntimeError(
            f"{agent_name} [{model}] failed with exit code {process.returncode}:\n"
            f"{(process.stderr or process.stdout or '').strip()}"
        )

    try:
        envelope = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{agent_name} [{model}] returned invalid Claude JSON.") from exc

    structured = envelope.get("structured_output")
    if not isinstance(structured, dict):
        raise RuntimeError(f"{agent_name} [{model}] did not return structured_output.")

    print(f"Completed: {agent_name} [{model}] in {duration}s")
    return {
        "agent": agent_name,
        "model": model,
        "duration_seconds": duration,
        "result": structured,
    }


def common_review_prompt(*, role_name: str, role_focus: str, frozen_head: str) -> str:
    docs = "\n".join(f"- `{path}`" for path in ARCHITECTURE_DOCS)
    return f"""# No Safe Circle adversarial architecture review

You are the **{role_name}**.

Your specialization:
{role_focus}

## Mission

Independently evaluate whether the current No Safe Circle autonomous AI-development
architecture is fundamentally sound and whether it is likely to create enough leverage
to make game development materially faster.

This is NOT an approval exercise. The existing architecture, milestone ordering, ADRs,
and proposed next step are hypotheses. You may reject them.

The frozen repository commit for this review is:

`{frozen_head}`

Inspect the repository directly using Read/Glob/Grep. Architecture documents are claims
to verify against implementation and repository history, not unquestioned truth.

Start with these documents, then inspect implementation/tests/history where needed:

{docs}

Also inspect relevant material under:
- `Pipeline/Reconciliation/`
- `Assignment3AgentCrew/`, `DynamicContentPipeline/`, Assignment 5/6/7 areas if relevant
- Unity `Assets/` and tests where relevant to your specialty

## The actual decision we need

We want a more autonomous development pipeline that can help develop No Safe Circle in
days instead of weeks. But speed is not enough: if the architecture is unsound, we need
to consider a different solution.

Judge in this order:

1. Is the architecture fundamentally sound for autonomous Unity game development?
2. If not, what should be replaced or reorganized?
3. If sound, is it overbuilt or appropriately sized?
4. Does it plausibly create major near-term development leverage?
5. What is the single best next implementation slice?

Do NOT assume `Tasks/*.yaml`, the Work Graph Seeder, `taskcontrol`, or the current
milestone order is correct merely because repository docs say it is next.

A particularly important concern is that the GDD is iterative and will continue to
change while the game is built. Challenge whether reconciliation/verification is framed
correctly for a moving design target. Distinguish synchronization with evolving canon
from one-time bootstrap correctness.

Mandatory questions to answer in your analysis:
- Which mechanisms solve failures this project has actually experienced?
- Which mechanisms mostly protect against hypothetical future failures?
- Which state/authority boundaries are necessary, and which duplicate responsibility?
- What happens when the GDD changes after work has been planned or implemented?
- What human intervention will still be required?
- If forbidden to build more infrastructure for one development slice, what would break
  first when trying to advance a real gameplay feature with the current machinery?
- If you reject the current architecture, propose a materially different architecture
  covering state, planning, execution, validation, recovery, and Unity integration.

Do not vote with imagined reviewers. Give your own evidence-backed judgment.
"""


def synthesis_prompt(*, frozen_head: str, review_dir: Path) -> str:
    relative_dir = review_dir.relative_to(ROOT).as_posix()
    return f"""# Architecture review synthesis

You are the lead architecture synthesizer for No Safe Circle.

Frozen repository commit: `{frozen_head}`

Eight independent reviews are stored in:
`{relative_dir}/`

Read every `*.json` review in that directory and inspect the repository yourself where
needed.

Your job is NOT to count votes. These reviewers share model-family biases and repeated
claims are not independent proof. Evaluate arguments and repository evidence.

Determine:
- whether the current architecture is fundamentally sound;
- which boundaries should be preserved, changed, replaced, deferred, or deleted;
- whether reconciliation/verification has the right role when the GDD evolves
  iteratively;
- the minimum viable architecture that still gives strong safety and recovery;
- the shortest path to materially higher game-development throughput;
- the single next implementation slice and an explicit test proving it creates value.

A strong minority argument may defeat a shallow majority. Call out disagreements rather
than smoothing them over.

Do not assume the Work Graph Seeder / `Tasks/*.yaml` / `taskcontrol` is next. Recommend
it only if the evidence supports it.
"""


def adversary_prompt(*, frozen_head: str, synthesis_path: Path, review_dir: Path) -> str:
    synthesis_rel = synthesis_path.relative_to(ROOT).as_posix()
    review_rel = review_dir.relative_to(ROOT).as_posix()
    return f"""# Adversarial critique of architecture synthesis

Assume the synthesis recommendation is wrong and following it could waste the remaining
development window or lock No Safe Circle into a flawed autonomous-development design.

Frozen repository commit: `{frozen_head}`

Read:
- synthesis: `{synthesis_rel}`
- all independent reviews: `{review_rel}/`
- repository architecture and implementation evidence as needed

Build the strongest technical and production case AGAINST the synthesis.

Specifically look for:
- hidden assumptions;
- minority reviewer arguments the synthesis undervalued;
- state-model or authority flaws;
- bad assumptions about an evolving GDD;
- Unity realities the synthesis abstracted away;
- optimistic autonomy/throughput assumptions;
- a simpler or materially different architecture that would be safer or faster.

Then decide whether the synthesis still holds, needs revision, or is unsafe.
"""


def assign_models(seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    pool = MODEL_POOL[:]
    rng.shuffle(pool)
    assignments: dict[str, str] = {}
    for index, role in enumerate(ROLE_SPECS):
        assignments[role["key"]] = pool[index % len(pool)]
    return assignments


def run_reviews(*, run_dir: Path, frozen_head: str, seed: int) -> list[dict[str, Any]]:
    review_dir = run_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=False)
    assignments = assign_models(seed)
    safe_write_json(run_dir / "model_assignments.json", assignments)

    def run_one(role: dict[str, str]) -> dict[str, Any]:
        result = invoke_read_only_agent(
            agent_name=role["name"],
            model=assignments[role["key"]],
            prompt=common_review_prompt(
                role_name=role["name"],
                role_focus=role["focus"],
                frozen_head=frozen_head,
            ),
            schema=REVIEW_SCHEMA,
            max_turns=REVIEW_MAX_TURNS,
        )
        safe_write_json(review_dir / f"{role['key']}.json", result)
        return result

    results: list[dict[str, Any]] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(ROLE_SPECS)))) as executor:
        future_map = {executor.submit(run_one, role): role for role in ROLE_SPECS}
        for future in as_completed(future_map):
            role = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append(f"{role['name']}: {exc}")

    if failures:
        safe_write_json(run_dir / "failures.json", {"failures": failures})
        raise RuntimeError("Architecture review failed:\n" + "\n".join(failures))

    return sorted(results, key=lambda item: item["agent"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run independent adversarial architecture reviews, synthesis, and red-team critique."
    )
    parser.add_argument("--seed", type=int, default=None, help="Model-assignment seed.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running against a dirty working tree. Normally the review requires a frozen commit.",
    )
    args = parser.parse_args()

    if git_dirty() and not args.allow_dirty:
        raise RuntimeError(
            "Working tree is dirty. Commit/stash changes or pass --allow-dirty. "
            "A frozen clean commit is strongly preferred for architecture review."
        )

    frozen_head = git_head()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 2**31)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = OUTPUT_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "run_id": run_id,
        "started_at": utc_now(),
        "frozen_head": frozen_head,
        "dirty_worktree_allowed": bool(args.allow_dirty),
        "model_pool": MODEL_POOL,
        "synthesis_model": SYNTHESIS_MODEL,
        "adversary_model": ADVERSARY_MODEL,
        "seed": seed,
        "roles": [{"key": r["key"], "name": r["name"]} for r in ROLE_SPECS],
    }
    safe_write_json(run_dir / "manifest.json", manifest)

    review_results = run_reviews(run_dir=run_dir, frozen_head=frozen_head, seed=seed)
    review_dir = run_dir / "reviews"

    synthesis = invoke_read_only_agent(
        agent_name="Architecture Synthesis",
        model=SYNTHESIS_MODEL,
        prompt=synthesis_prompt(frozen_head=frozen_head, review_dir=review_dir),
        schema=SYNTHESIS_SCHEMA,
        max_turns=SYNTHESIS_MAX_TURNS,
    )
    synthesis_path = run_dir / "synthesis.json"
    safe_write_json(synthesis_path, synthesis)

    adversary = invoke_read_only_agent(
        agent_name="Adversarial Synthesis Critic",
        model=ADVERSARY_MODEL,
        prompt=adversary_prompt(
            frozen_head=frozen_head,
            synthesis_path=synthesis_path,
            review_dir=review_dir,
        ),
        schema=ADVERSARY_SCHEMA,
        max_turns=ADVERSARY_MAX_TURNS,
    )
    safe_write_json(run_dir / "adversarial_critique.json", adversary)

    manifest["completed_at"] = utc_now()
    manifest["status"] = "complete"
    manifest["review_count"] = len(review_results)
    safe_write_json(run_dir / "manifest.json", manifest)

    current = OUTPUT_ROOT / "current"
    current.mkdir(parents=True, exist_ok=True)
    safe_write_json(
        current / "LATEST.json",
        {"run_id": run_id, "run_path": run_dir.relative_to(ROOT).as_posix()},
    )
    safe_write_json(current / "synthesis.json", synthesis)
    safe_write_json(current / "adversarial_critique.json", adversary)

    print(f"Architecture review complete: {run_dir.relative_to(ROOT).as_posix()}")
    print(f"Synthesis: {synthesis_path.relative_to(ROOT).as_posix()}")
    print(
        "Adversarial critique: "
        f"{(run_dir / 'adversarial_critique.json').relative_to(ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
