from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py"
MARKER = "STREAMING REPAIR COORDINATOR"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("Streaming verification refinement is already installed.")
        return 0

    text = replace_once(
        text,
        "from typing import Any\n",
        "from typing import Any, Callable\n",
        "typing import",
    )

    config_anchor = '''EXECUTION_MAX_TURNS = int(
    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_EXECUTION_TURNS", "24")
)
'''
    config_replacement = config_anchor + '''
STREAM_REPAIR_MAX_WORKERS = int(
    __import__("os").environ.get("RECONCILIATION_STREAM_REPAIR_MAX_WORKERS", "6")
)
STREAM_REPAIR_MODEL = (
    __import__("os").environ.get("RECONCILIATION_STREAM_REPAIR_MODEL", "sonnet").strip()
    or "sonnet"
)
'''
    text = replace_once(text, config_anchor, config_replacement, "stream config")

    signature_anchor = '''def run_specs(
    *,
    specs: list[AuditSpec],
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
    output_dir: Path,
    assignments: dict[str, str],
) -> list[dict[str, Any]]:
'''
    signature_replacement = '''def run_specs(
    *,
    specs: list[AuditSpec],
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
    output_dir: Path,
    assignments: dict[str, str],
    on_result: Callable[[AuditSpec, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
'''
    text = replace_once(text, signature_anchor, signature_replacement, "run_specs signature")

    first_success = '''            results_by_key[spec.key] = result
            base.save_new_json(output_dir / f"{spec.key}.json", result)
'''
    first_success_replacement = first_success + '''            if on_result is not None:
                on_result(spec, result)
'''
    text = replace_once(text, first_success, first_success_replacement, "first-wave callback")

    recovery_success = '''                    results_by_key[spec.key] = result
                    base.save_new_json(
                        output_dir / f"{spec.key}.json",
                        result,
                    )
'''
    recovery_success_replacement = recovery_success + '''                    if on_result is not None:
                        on_result(spec, result)
'''
    text = replace_once(text, recovery_success, recovery_success_replacement, "recovery callback")

    helper_anchor = '''# ============================================================
# SELECTIVE PASS 2
# ============================================================
'''
    helper_block = r'''# ============================================================
# STREAMING REPAIR COORDINATOR
# ============================================================


def _stream_delta_targets(delta: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    groups = (
        ("work_item", "work_items_upsert", "key"),
        ("non_code", "non_code_requirements_upsert", "title"),
        ("deferred", "deferred_or_excluded_upsert", "title"),
        ("question", "unresolved_questions_upsert", "question"),
    )
    removals = (
        ("work_item", "work_item_keys_remove"),
        ("non_code", "non_code_requirement_titles_remove"),
        ("deferred", "deferred_or_excluded_titles_remove"),
        ("question", "unresolved_question_texts_remove"),
    )

    for prefix, field, identifier in groups:
        for record in delta.get(field, []):
            value = str(record.get(identifier, "")).strip()
            if value:
                targets.add(f"{prefix}:{value}")
    for prefix, field in removals:
        for raw in delta.get(field, []):
            value = str(raw).strip()
            if value:
                targets.add(f"{prefix}:{value}")
    return targets


class StreamingRepairCoordinator:
    """Launch isolated repair proposals as auditors finish; apply none directly."""

    def __init__(
        self,
        *,
        source_candidate: Path,
        source_run_id: str,
        run_dir: Path,
    ) -> None:
        self.source_candidate = source_candidate
        self.source_run_id = source_run_id
        self.root = run_dir / "stream_repairs"
        self.root.mkdir(parents=True, exist_ok=False)
        self.executor = ThreadPoolExecutor(max_workers=max(1, STREAM_REPAIR_MAX_WORKERS))
        self.futures: dict[Any, tuple[AuditSpec, Path, dict[str, Any]]] = {}
        self.repairs: dict[str, dict[str, Any]] = {}
        self.conflict_report: dict[str, Any] | None = None
        self.manifest_path = run_dir / "STREAM_REPAIR_MANIFEST.json"
        self.conflict_path = run_dir / "STREAM_CONFLICT_REPORT.json"
        self.arbiter_path = run_dir / "STREAM_CONFLICT_ARBITER.json"
        self._collected = False

    def on_audit_result(self, spec: AuditSpec, audit: dict[str, Any]) -> None:
        local_merged = base.merge_findings([audit])
        local_findings = base.build_refiner_findings(local_merged)
        if not local_findings.get("findings"):
            return

        repair_dir = self.root / spec.key
        repair_dir.mkdir(parents=True, exist_ok=False)
        findings_path = repair_dir / "REFINER_FINDINGS.json"
        base.save_new_json(findings_path, local_findings)
        print(
            f"[STREAM] {spec.key} produced refiner-relevant findings; "
            "starting an isolated repair proposal now."
        )
        future = self.executor.submit(
            base.run_refiner,
            source_candidate=self.source_candidate,
            merged_findings_path=findings_path,
            source_run_id=self.source_run_id,
            model=STREAM_REPAIR_MODEL,
        )
        self.futures[future] = (spec, findings_path, local_findings)

    def collect(self) -> None:
        if self._collected:
            return
        try:
            for future in as_completed(self.futures):
                spec, _, local_findings = self.futures[future]
                envelope = future.result()
                delta = envelope["result"]
                base.validate_refiner_resolutions(delta, local_findings)
                self.repairs[spec.key] = envelope
                base.save_new_json(
                    self.root / spec.key / "PROPOSED_REPAIR_DELTA.json",
                    envelope,
                )
                print(f"[STREAM] Isolated repair proposal complete: {spec.key}")
        finally:
            self.executor.shutdown(wait=True)
            self._collected = True

        owners: dict[str, list[str]] = {}
        proposal_targets: dict[str, list[str]] = {}
        for key, envelope in sorted(self.repairs.items()):
            targets = sorted(_stream_delta_targets(envelope["result"]))
            proposal_targets[key] = targets
            for target in targets:
                owners.setdefault(target, []).append(key)

        direct_conflicts = {
            target: sorted(keys)
            for target, keys in sorted(owners.items())
            if len(keys) > 1
        }
        self.conflict_report = {
            "schema_version": "1.0",
            "proposal_count": len(self.repairs),
            "proposal_targets": proposal_targets,
            "direct_record_conflicts": direct_conflicts,
            "conflict_count": len(direct_conflicts),
            "policy": (
                "Direct conflict means multiple isolated repair proposals touch the "
                "same durable record identifier. The conflict arbiter must also detect "
                "semantic cross-record conflicts such as dependency cycles, ownership "
                "contradictions, incompatible locks, or duplicate responsibilities."
            ),
        }
        base.save_new_json(self.conflict_path, self.conflict_report)
        base.save_new_json(
            self.manifest_path,
            {
                "schema_version": "1.0",
                "repair_model": STREAM_REPAIR_MODEL,
                "repairs": [
                    {
                        "audit_key": key,
                        "requested_model": envelope.get("requested_model"),
                        "duration_seconds": envelope.get("duration_seconds"),
                        "delta": envelope.get("result"),
                    }
                    for key, envelope in sorted(self.repairs.items())
                ],
                "deterministic_conflict_report": self.conflict_report,
            },
        )

    def arbitrate(
        self,
        *,
        full_findings_path: Path,
        model: str,
    ) -> dict[str, Any]:
        self.collect()
        candidate_rel = self.source_candidate.relative_to(base.ROOT).as_posix()
        findings_rel = full_findings_path.relative_to(base.ROOT).as_posix()
        manifest_rel = self.manifest_path.relative_to(base.ROOT).as_posix()
        prompt = (
            "# No Safe Circle Streaming Repair Conflict Arbiter\n\n"
            "Independent verification auditors reviewed one immutable reconciliation "
            "candidate. As each auditor finished, an isolated repair worker proposed a "
            "delta against that ORIGINAL candidate. None of those proposals has been "
            "applied.\n\n"
            "Your job is to inspect the complete verifier finding set plus all early "
            "repair proposals, detect direct and semantic conflicts, and return ONE "
            "coherent REFINER_DELTA_SCHEMA delta relative to the ORIGINAL candidate.\n\n"
            "Authority: current GDD first, current repository second, verifier evidence "
            "third. Early repair proposals are suggestions only. Do not combine them "
            "blindly. If proposals conflict, discard incompatible portions and synthesize "
            "the correct replacement from the original candidate and evidence. Check "
            "cross-record conflicts including dependency cycles, owner/consumer "
            "contradictions, incompatible exclusive-resource locks, duplicated work, and "
            "execution-scope inconsistencies. Resolve every supplied finding exactly once "
            "in finding_resolutions. Preserve unresolved/human-review findings when the "
            "evidence is insufficient. Do not invent missing game design.\n\n"
            f"Original candidate: `{candidate_rel}`\n"
            f"Complete refiner findings: `{findings_rel}`\n"
            f"Early repair manifest/conflict report: `{manifest_rel}`\n"
        )
        envelope = base.invoke_read_only_agent(
            agent_name="Streaming Repair Conflict Arbiter",
            model=model,
            prompt=prompt,
            schema=base.REFINER_DELTA_SCHEMA,
            timeout_seconds=base.REFINER_TIMEOUT_SECONDS,
            max_turns=base.REFINER_MAX_TURNS,
        )
        base.save_new_json(self.arbiter_path, envelope)
        return envelope

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "repair_model": STREAM_REPAIR_MODEL,
            "repair_max_workers": STREAM_REPAIR_MAX_WORKERS,
            "proposal_count": len(self.repairs),
            "mechanical_conflict_count": (
                int(self.conflict_report.get("conflict_count", 0))
                if self.conflict_report is not None
                else 0
            ),
            "safety_policy": (
                "Early repair workers only propose deltas against the immutable source. "
                "Only the final conflict arbiter delta may be applied."
            ),
        }


''' + helper_anchor
    text = replace_once(text, helper_anchor, helper_block, "stream helper insertion")

    model_anchor = '''        refiner_model = base.choose_refiner_model(rng, {})

        model_assignments = {
'''
    model_replacement = '''        refiner_model = base.choose_refiner_model(rng, {})
        stream_repairs = (
            None
            if args.no_refine
            else StreamingRepairCoordinator(
                source_candidate=source_candidate,
                source_run_id=source_run_id,
                run_dir=paths["run_dir"],
            )
        )

        model_assignments = {
'''
    text = replace_once(text, model_anchor, model_replacement, "stream coordinator init")

    assignment_anchor = '''            "refiner": refiner_model,
            "pass2": pass2_assignments,
'''
    assignment_replacement = '''            "refiner": refiner_model,
            "stream_repair_model": (
                STREAM_REPAIR_MODEL if stream_repairs is not None else None
            ),
            "stream_repair_max_workers": (
                STREAM_REPAIR_MAX_WORKERS if stream_repairs is not None else 0
            ),
            "pass2": pass2_assignments,
'''
    text = replace_once(text, assignment_anchor, assignment_replacement, "model assignment stream fields")

    pass1_anchor = '''        pass1_audits = run_specs(
            specs=SPECS,
            candidate_path=source_candidate,
            source_run_id=source_run_id,
            pass_label="pass1",
            output_dir=paths["pass1_dir"],
            assignments=pass1_assignments,
        )

        merged1 = base.merge_findings(pass1_audits)
'''
    pass1_replacement = '''        pass1_audits = run_specs(
            specs=SPECS,
            candidate_path=source_candidate,
            source_run_id=source_run_id,
            pass_label="pass1",
            output_dir=paths["pass1_dir"],
            assignments=pass1_assignments,
            on_result=(
                stream_repairs.on_audit_result
                if stream_repairs is not None
                else None
            ),
        )
        if stream_repairs is not None:
            # Most repair proposals have already been running while slower auditors
            # finish. This only waits for whatever proposal work remains.
            stream_repairs.collect()

        merged1 = base.merge_findings(pass1_audits)
'''
    text = replace_once(text, pass1_anchor, pass1_replacement, "pass1 streaming callback")

    refiner_anchor = '''            refiner = base.run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )

            refiner_delta = refiner["result"]
'''
    refiner_replacement = '''            if stream_repairs is not None:
                print()
                print("=" * 72)
                print("STREAMING REPAIR CONFLICT / SYNTHESIS GATE")
                print("=" * 72)
                print(
                    f"Early repair proposals: {len(stream_repairs.repairs)}"
                )
                print(
                    "Mechanical direct conflicts: "
                    f"{stream_repairs.summary()['mechanical_conflict_count']}"
                )
                print("Final arbiter also checks semantic cross-record conflicts.")
                print("=" * 72)
                refiner = stream_repairs.arbitrate(
                    full_findings_path=paths["refiner_findings"],
                    model=refiner_model,
                )
            else:
                refiner = base.run_refiner(
                    source_candidate=source_candidate,
                    merged_findings_path=paths["refiner_findings"],
                    source_run_id=source_run_id,
                    model=refiner_model,
                )

            refiner_delta = refiner["result"]
'''
    text = replace_once(text, refiner_anchor, refiner_replacement, "arbiter replacement")

    summary_anchor = '''            "parallel_max_workers": PARALLEL_MAX_WORKERS,
            "model_assignments": {
'''
    summary_replacement = '''            "parallel_max_workers": PARALLEL_MAX_WORKERS,
            "streaming_refinement": (
                stream_repairs.summary()
                if stream_repairs is not None
                else {"enabled": False}
            ),
            "model_assignments": {
'''
    text = replace_once(text, summary_anchor, summary_replacement, "summary streaming metadata")

    note_anchor = '''                "Fifteen focused auditors are independently scoped and their findings "
                "are unioned, never voted. Pass 2 is selective unless --full-pass2 is used. "
                "A max-turn failure is retried without rerunning successful auditors."
'''
    note_replacement = '''                "Fifteen focused auditors are independently scoped and their findings "
                "are unioned, never voted. Completed pass-1 auditors may immediately "
                "launch isolated repair proposals against the immutable candidate. A final "
                "conflict arbiter consolidates proposals before selective pass 2. A max-turn "
                "failure is retried without rerunning successful auditors."
'''
    text = replace_once(text, note_anchor, note_replacement, "model assignment note")

    TARGET.write_text(text, encoding="utf-8")
    print(f"Installed streaming verification refinement in {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
