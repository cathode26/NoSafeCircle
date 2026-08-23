from __future__ import annotations

import argparse
import json
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import architecture_review as base


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_completed_result(path: Path, *, expected_agent: str) -> dict[str, Any] | None:
    """Return a reusable completed agent result, or None if it is absent/invalid."""
    if not path.exists():
        return None

    try:
        value = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(value, dict):
        return None
    if value.get("agent") != expected_agent:
        return None
    if not isinstance(value.get("result"), dict):
        return None
    return value


def record_failure_history(run_dir: Path, failures: list[str], stage: str) -> None:
    if not failures:
        return

    path = run_dir / "failure_history.json"
    history: list[dict[str, Any]] = []
    if path.exists():
        try:
            loaded = load_json(path)
            if isinstance(loaded, list):
                history = loaded
        except (OSError, json.JSONDecodeError):
            history = []

    history.append(
        {
            "recorded_at": base.utc_now(),
            "stage": stage,
            "failures": failures,
        }
    )
    base.safe_write_json(path, history)


def update_manifest(run_dir: Path, **changes: Any) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    manifest = load_json(path)
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Invalid architecture-review manifest: {path}")
    manifest.update(changes)
    base.safe_write_json(path, manifest)
    return manifest


def run_reviews_resumable(
    *,
    run_dir: Path,
    frozen_head: str,
    seed: int,
) -> list[dict[str, Any]]:
    review_dir = run_dir / "reviews"
    review_dir.mkdir(parents=True, exist_ok=True)

    assignments_path = run_dir / "model_assignments.json"
    if assignments_path.exists():
        assignments = load_json(assignments_path)
        if not isinstance(assignments, dict):
            raise RuntimeError(f"Invalid model assignments: {assignments_path}")
    else:
        assignments = base.assign_models(seed)
        base.safe_write_json(assignments_path, assignments)

    expected_keys = {role["key"] for role in base.ROLE_SPECS}
    if set(assignments) != expected_keys:
        raise RuntimeError(
            "Saved model assignments do not match the configured reviewer roles."
        )

    results: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []

    for role in base.ROLE_SPECS:
        path = review_dir / f"{role['key']}.json"
        completed = load_completed_result(path, expected_agent=role["name"])
        if completed is None:
            pending.append(role)
        else:
            print(f"Reusing completed reviewer: {role['name']}")
            results.append(completed)

    def run_one(role: dict[str, str]) -> dict[str, Any]:
        result = base.invoke_read_only_agent(
            agent_name=role["name"],
            model=str(assignments[role["key"]]),
            prompt=base.common_review_prompt(
                role_name=role["name"],
                role_focus=role["focus"],
                frozen_head=frozen_head,
            ),
            schema=base.REVIEW_SCHEMA,
            max_turns=base.REVIEW_MAX_TURNS,
        )
        base.safe_write_json(review_dir / f"{role['key']}.json", result)
        return result

    failures: list[str] = []
    if pending:
        max_workers = max(1, min(base.MAX_WORKERS, len(pending)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_one, role): role for role in pending}
            for future in as_completed(future_map):
                role = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    failures.append(f"{role['name']}: {exc}")

    if failures:
        record_failure_history(run_dir, failures, "independent_reviews")
        update_manifest(
            run_dir,
            status="partial_review_failure",
            last_failure_at=base.utc_now(),
            completed_review_count=len(results),
        )
        raise RuntimeError(
            "Architecture review stopped with preserved partial results.\n"
            "Resume this same run with --resume-run <run-id>.\n"
            + "\n".join(failures)
        )

    update_manifest(
        run_dir,
        status="reviews_complete",
        reviews_completed_at=base.utc_now(),
        completed_review_count=len(results),
    )
    return sorted(results, key=lambda item: item["agent"])


def create_new_run(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    if base.git_dirty() and not args.allow_dirty:
        raise RuntimeError(
            "Working tree is dirty. Commit/stash changes or pass --allow-dirty. "
            "A frozen clean commit is strongly preferred for architecture review."
        )

    frozen_head = base.git_head()
    seed = (
        args.seed
        if args.seed is not None
        else random.SystemRandom().randrange(1, 2**31)
    )
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    run_dir = base.provider_output_root() / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "provider_namespace": base.PROVIDER_NAMESPACE,
        "run_id": run_id,
        "started_at": base.utc_now(),
        "frozen_head": frozen_head,
        "dirty_worktree_allowed": bool(args.allow_dirty),
        "model_pool": base.MODEL_POOL,
        "synthesis_model": base.SYNTHESIS_MODEL,
        "adversary_model": base.ADVERSARY_MODEL,
        "seed": seed,
        "roles": [
            {"key": role["key"], "name": role["name"]}
            for role in base.ROLE_SPECS
        ],
        "status": "started",
    }
    base.safe_write_json(run_dir / "manifest.json", manifest)
    return run_dir, manifest


def open_resumed_run(run_id: str) -> tuple[Path, dict[str, Any]]:
    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise RuntimeError("--resume-run must be a run ID, not a path.")

    run_dir = base.provider_output_root() / "runs" / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Architecture-review run not found: {run_id}")

    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Invalid architecture-review manifest: {manifest_path}")

    provider_namespace = manifest.get("provider_namespace")
    if provider_namespace != base.PROVIDER_NAMESPACE:
        raise RuntimeError(
            "Cannot resume an ArchitectureReview run owned by a different provider "
            f"namespace: manifest={provider_namespace!r}, configured={base.PROVIDER_NAMESPACE!r}."
        )

    frozen_head = str(manifest.get("frozen_head", ""))
    current_head = base.git_head()
    if not frozen_head:
        raise RuntimeError("Saved run manifest has no frozen_head.")
    if current_head != frozen_head:
        raise RuntimeError(
            "Cannot resume against a different repository commit.\n"
            f"Run commit:     {frozen_head}\n"
            f"Current commit: {current_head}\n"
            "Switch back to the frozen commit before resuming so all reviewers "
            "evaluate identical evidence."
        )

    print(f"Resuming architecture review: {run_id}")
    return run_dir, manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run or resume independent adversarial architecture reviews, "
            "synthesis, and red-team critique."
        )
    )
    parser.add_argument("--seed", type=int, default=None, help="Model-assignment seed.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "Allow a new run against a dirty working tree. Resume still requires "
            "the same Git commit recorded by the run."
        ),
    )
    parser.add_argument(
        "--resume-run",
        metavar="RUN_ID",
        help=(
            "Resume an existing run. Completed reviewers, synthesis, and critique "
            "are reused; only missing or invalid stages run again."
        ),
    )
    args = parser.parse_args()

    if args.resume_run:
        if args.seed is not None:
            parser.error("--seed cannot be combined with --resume-run.")
        run_dir, manifest = open_resumed_run(args.resume_run)
    else:
        run_dir, manifest = create_new_run(args)

    frozen_head = str(manifest["frozen_head"])
    seed = int(manifest["seed"])
    run_id = str(manifest["run_id"])
    base.configure_invocation_run_root(run_dir)

    review_results = run_reviews_resumable(
        run_dir=run_dir,
        frozen_head=frozen_head,
        seed=seed,
    )
    review_dir = run_dir / "reviews"

    synthesis_path = run_dir / "synthesis.json"
    synthesis = load_completed_result(
        synthesis_path,
        expected_agent="Architecture Synthesis",
    )
    if synthesis is None:
        try:
            synthesis = base.invoke_read_only_agent(
                agent_name="Architecture Synthesis",
                model=str(manifest.get("synthesis_model", base.SYNTHESIS_MODEL)),
                prompt=base.synthesis_prompt(
                    frozen_head=frozen_head,
                    review_dir=review_dir,
                ),
                schema=base.SYNTHESIS_SCHEMA,
                max_turns=base.SYNTHESIS_MAX_TURNS,
            )
            base.safe_write_json(synthesis_path, synthesis)
        except Exception as exc:
            record_failure_history(run_dir, [str(exc)], "synthesis")
            update_manifest(
                run_dir,
                status="synthesis_failure",
                last_failure_at=base.utc_now(),
            )
            raise RuntimeError(
                "Synthesis failed after all reviewer outputs were preserved.\n"
                f"Resume with --resume-run {run_id}.\n{exc}"
            ) from exc
    else:
        print("Reusing completed synthesis.")

    update_manifest(
        run_dir,
        status="synthesis_complete",
        synthesis_completed_at=base.utc_now(),
    )

    adversary_path = run_dir / "adversarial_critique.json"
    adversary = load_completed_result(
        adversary_path,
        expected_agent="Adversarial Synthesis Critic",
    )
    if adversary is None:
        try:
            adversary = base.invoke_read_only_agent(
                agent_name="Adversarial Synthesis Critic",
                model=str(manifest.get("adversary_model", base.ADVERSARY_MODEL)),
                prompt=base.adversary_prompt(
                    frozen_head=frozen_head,
                    synthesis_path=synthesis_path,
                    review_dir=review_dir,
                ),
                schema=base.ADVERSARY_SCHEMA,
                max_turns=base.ADVERSARY_MAX_TURNS,
            )
            base.safe_write_json(adversary_path, adversary)
        except Exception as exc:
            record_failure_history(run_dir, [str(exc)], "adversarial_critique")
            update_manifest(
                run_dir,
                status="adversarial_critique_failure",
                last_failure_at=base.utc_now(),
            )
            raise RuntimeError(
                "Adversarial critique failed after reviews and synthesis were preserved.\n"
                f"Resume with --resume-run {run_id}.\n{exc}"
            ) from exc
    else:
        print("Reusing completed adversarial critique.")

    update_manifest(
        run_dir,
        completed_at=base.utc_now(),
        status="complete",
        review_count=len(review_results),
    )

    base.publish_latest(
        run_dir=run_dir, run_id=run_id, frozen_head=frozen_head,
        synthesis=synthesis, adversary=adversary,
    )

    print(f"Architecture review complete: {run_dir.relative_to(base.ROOT).as_posix()}")
    print(f"Synthesis: {synthesis_path.relative_to(base.ROOT).as_posix()}")
    print(
        "Adversarial critique: "
        f"{adversary_path.relative_to(base.ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
