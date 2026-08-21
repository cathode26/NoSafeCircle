from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "Pipeline" / "Reconciliation"
BASE = RECON / "verification_crew.py"
PARALLEL = RECON / "parallel_verification_crew.py"

MARKER = "VERIFIER EXECUTION HARDENING 2026-08-21"

NEW_RUN_SPECS = r'''def run_specs(
    *,
    specs: list[AuditSpec],
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
    output_dir: Path,
    assignments: dict[str, str],
    on_result: Callable[[AuditSpec, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """
    Run requested auditors without fail-fast loss and with immediate bounded recovery.

    At most PARALLEL_MAX_WORKERS auditor futures are active at once. If an auditor
    reaches max turns, its recovery attempt is submitted immediately into the slot
    that just opened, before another queued first-attempt auditor is dispatched.
    Successful auditor work is persisted as soon as it completes and is never rerun.
    """
    output_dir.mkdir(parents=True, exist_ok=False)

    results_by_key: dict[str, dict[str, Any]] = {}
    unrecovered: dict[str, tuple[AuditSpec, Exception]] = {}
    next_spec_index = 0

    def turns_for_attempt(spec: AuditSpec, attempt: int) -> int:
        return spec.max_turns + ((attempt - 1) * RECOVERY_TURN_BONUS)

    def invoke(
        spec: AuditSpec,
        *,
        attempt: int,
        max_turns: int,
    ) -> dict[str, Any]:
        is_recovery = attempt > 1
        agent_name = (
            f"{spec.agent_name} [recovery]"
            if is_recovery
            else spec.agent_name
        )
        attempt_pass_label = (
            f"{pass_label}-max-turn-recovery-{attempt - 1}"
            if is_recovery
            else pass_label
        )

        result = base.invoke_read_only_agent(
            agent_name=agent_name,
            model=assignments[spec.key],
            prompt=build_scoped_prompt(
                spec=spec,
                candidate_path=candidate_path,
                source_run_id=source_run_id,
                pass_label=attempt_pass_label,
            ),
            schema=spec.schema,
            timeout_seconds=base.VERIFY_TIMEOUT_SECONDS,
            max_turns=max_turns,
        )

        # Normalize recovery metadata so merge/final-pass replacement logic treats
        # a recovered result as the original auditor identity.
        result["agent"] = spec.agent_name
        result["verification_attempt"] = attempt
        result["max_turns_used"] = max_turns
        if is_recovery:
            result["recovered_from"] = "max_turns"
        return result

    max_workers = max(1, min(PARALLEL_MAX_WORKERS, len(specs)))
    pending: dict[Any, tuple[AuditSpec, int, int]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        def submit_attempt(spec: AuditSpec, attempt: int) -> None:
            max_turns = turns_for_attempt(spec, attempt)
            future = executor.submit(
                invoke,
                spec,
                attempt=attempt,
                max_turns=max_turns,
            )
            pending[future] = (spec, attempt, max_turns)

        def fill_first_attempt_slots() -> None:
            nonlocal next_spec_index
            while (
                len(pending) < max_workers
                and next_spec_index < len(specs)
            ):
                spec = specs[next_spec_index]
                next_spec_index += 1
                submit_attempt(spec, 1)

        fill_first_attempt_slots()

        while pending:
            done, _ = wait(
                tuple(pending),
                return_when=FIRST_COMPLETED,
            )

            # Recovery attempts are collected and submitted before unused slots are
            # filled with queued first attempts. This gives max-turn recovery true
            # immediate priority without exceeding the configured parallelism cap.
            immediate_retries: list[tuple[AuditSpec, int]] = []

            for future in done:
                spec, attempt, max_turns = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    base.save_new_json(
                        output_dir / f"{spec.key}.attempt{attempt}.failure.json",
                        _failure_payload(
                            spec=spec,
                            model=assignments[spec.key],
                            attempt=attempt,
                            max_turns=max_turns,
                            exc=exc,
                        ),
                    )

                    recovery_count_used = attempt - 1
                    can_recover = (
                        _is_max_turn_failure(exc)
                        and recovery_count_used < MAX_TURN_RECOVERY_ATTEMPTS
                    )

                    if can_recover:
                        retry_attempt = attempt + 1
                        retry_turns = turns_for_attempt(spec, retry_attempt)
                        print()
                        print("=" * 72)
                        print("MAX-TURN RECOVERY -- IMMEDIATE")
                        print("=" * 72)
                        print(
                            f"Retrying {spec.key} immediately: "
                            f"{max_turns} -> {retry_turns} turns"
                        )
                        print(
                            "The retry takes priority in the newly freed slot; "
                            "successful auditors are not rerun."
                        )
                        print("=" * 72)
                        immediate_retries.append((spec, retry_attempt))
                    else:
                        unrecovered[spec.key] = (spec, exc)
                        print(
                            "Auditor failed after bounded recovery or with a "
                            f"non-retriable error: {spec.agent_name} — {exc}"
                        )
                    continue

                results_by_key[spec.key] = result
                base.save_new_json(output_dir / f"{spec.key}.json", result)
                if on_result is not None:
                    on_result(spec, result)

            # Submit retries before any queued first-attempt work.
            for spec, retry_attempt in immediate_retries:
                submit_attempt(spec, retry_attempt)

            fill_first_attempt_slots()

    if unrecovered:
        details = "; ".join(
            f"{key}: {exc}"
            for key, (_, exc) in sorted(unrecovered.items())
        )
        raise RuntimeError(
            "Parallel verification preserved every successful auditor result, "
            "but one or more auditors still failed after bounded recovery. "
            + details
        )

    missing = [
        spec.key
        for spec in specs
        if spec.key not in results_by_key
    ]
    if missing:
        raise RuntimeError(
            "Parallel verification ended without results for: "
            + ", ".join(sorted(missing))
        )

    results = [
        results_by_key[spec.key]
        for spec in specs
    ]
    results.sort(key=lambda item: item["agent"])
    return results
'''


def patch_base_verifier() -> bool:
    text = BASE.read_text(encoding="utf-8")
    changed = False

    if "import builtins\n" not in text:
        text = text.replace("import argparse\n", "import argparse\nimport builtins\n", 1)
        changed = True
    if "import threading\n" not in text:
        text = text.replace("import subprocess\n", "import subprocess\nimport threading\n", 1)
        changed = True

    old_turns = '''VERIFY_MAX_TURNS = int(\n    os.environ.get("RECONCILIATION_VERIFY_MAX_TURNS", "30")\n)'''
    new_turns = '''VERIFY_MAX_TURNS = int(\n    os.environ.get("RECONCILIATION_VERIFY_MAX_TURNS", "32")\n)'''
    if old_turns in text:
        text = text.replace(old_turns, new_turns, 1)
        changed = True
    elif new_turns not in text:
        raise RuntimeError("Unable to locate base verifier max-turn default.")

    if MARKER not in text:
        anchor = '''if not MODEL_POOL:\n    raise RuntimeError("RECONCILIATION_VERIFIER_MODELS must contain a model.")\n'''
        if text.count(anchor) != 1:
            raise RuntimeError("Unable to locate verifier model-pool anchor.")
        block = f'''\n\n# {MARKER}\n_CONSOLE_PRINT_LOCK = threading.Lock()\n\n\ndef thread_safe_print(*args: Any, **kwargs: Any) -> None:\n    """Serialize console writes from parallel verifier threads."""\n    if "flush" not in kwargs:\n        kwargs["flush"] = True\n    with _CONSOLE_PRINT_LOCK:\n        builtins.print(*args, **kwargs)\n\n\n# All legacy print(...) calls in this module now resolve through the shared lock.\nprint = thread_safe_print\n'''
        text = text.replace(anchor, anchor + block, 1)
        changed = True

    if changed:
        BASE.write_text(text, encoding="utf-8")
    return changed


def patch_parallel_verifier() -> bool:
    text = PARALLEL.read_text(encoding="utf-8")
    changed = False

    old_import = "from concurrent.futures import ThreadPoolExecutor, as_completed\n"
    new_import = (
        "from concurrent.futures import "
        "FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait\n"
    )
    if old_import in text:
        text = text.replace(old_import, new_import, 1)
        changed = True
    elif new_import not in text:
        raise RuntimeError("Unable to locate concurrent.futures import.")

    if "print = base.thread_safe_print\n" not in text:
        anchor = "import verification_crew as base\n"
        if text.count(anchor) != 1:
            raise RuntimeError("Unable to locate verification_crew import.")
        text = text.replace(
            anchor,
            anchor
            + "\n# Share the base verifier console lock across every parallel print.\n"
            + "print = base.thread_safe_print\n",
            1,
        )
        changed = True

    replacements = {
        '''RECONCILIATION_PARALLEL_VERIFY_COVERAGE_TURNS", "24"''':
            '''RECONCILIATION_PARALLEL_VERIFY_COVERAGE_TURNS", "32"''',
        '''RECONCILIATION_PARALLEL_VERIFY_STRUCTURE_TURNS", "24"''':
            '''RECONCILIATION_PARALLEL_VERIFY_STRUCTURE_TURNS", "32"''',
        '''RECONCILIATION_PARALLEL_VERIFY_EXECUTION_TURNS", "24"''':
            '''RECONCILIATION_PARALLEL_VERIFY_EXECUTION_TURNS", "32"''',
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
        elif new not in text:
            raise RuntimeError(f"Unable to locate verifier turn default: {old}")

    start_marker = "def run_specs(\n"
    end_marker = (
        "\n\n# ============================================================\n"
        "# STREAMING REPAIR COORDINATOR\n"
        "# ============================================================\n"
    )
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise RuntimeError("Unable to locate run_specs function boundaries.")

    current_run_specs = text[start:end]
    if "MAX-TURN RECOVERY -- IMMEDIATE" not in current_run_specs:
        text = text[:start] + NEW_RUN_SPECS + text[end:]
        changed = True

    if changed:
        PARALLEL.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    changed = []
    if patch_base_verifier():
        changed.append(BASE.relative_to(ROOT).as_posix())
    if patch_parallel_verifier():
        changed.append(PARALLEL.relative_to(ROOT).as_posix())

    if changed:
        print("Installed verifier execution hardening:")
        for path in changed:
            print(f"  - {path}")
    else:
        print("Verifier execution hardening is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
