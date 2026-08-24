from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from conformance_records import CANON_PATH, EVIDENCE_ROOT, GitRepository, canonical_text_sha256, semantic_json_sha256
from current_conformance import evaluate_current_conformance
from record_delivery import hash_object_as_committed
from validate_draft_evidence import DraftEvidenceError, ValidationResult, validate_draft_evidence

TASK_ID = "NSC-950"
TASK_PATH = f"Tasks/{TASK_ID}.yaml"
SURFACE_A = "Assets/Foo/A.cs"
SURFACE_B = "Assets/Foo/B.cs"


def run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if check and result.returncode:
        raise AssertionError(f"{' '.join(args)} failed:\n{result.stderr}")
    return result


def git(root: Path, *args: str) -> str:
    return run(root, "git", *args).stdout.strip()


def write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def write_bytes(root: Path, path: str, data: bytes) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def write_json(root: Path, path: str, value: dict) -> None:
    write(root, path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


def stage(root: Path, *paths: str) -> None:
    git(root, "add", "-f", "--", *paths)


def task_contract(revision: int = 1, gate_ids: tuple[str, ...] = ("VAL-001", "VAL-002")) -> dict:
    return {
        "schema_version": "2.0",
        "id": TASK_ID,
        "contract_revision": revision,
        "contract_disposition": "active",
        "title": "Synthetic draft-evidence task",
        "reconciliation_key": "synthetic-draft-evidence",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "completion_gates": [
            {"gate_id": gate_id, "reference": "test", "requirement": f"{gate_id} passes"}
            for gate_id in gate_ids
        ],
    }


def init_repo(root: Path, *, gate_ids: tuple[str, ...] = ("VAL-001", "VAL-002"), gitignore: str = "", revision: int = 1) -> str:
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.email", "draft-validate-test@example.invalid")
    run(root, "git", "config", "user.name", "Draft Validate Test User")
    write_json(root, TASK_PATH, task_contract(revision=revision, gate_ids=gate_ids))
    write(root, CANON_PATH, "# Canon\n\nRules.\n")
    write(root, SURFACE_A, "surface a v1\n")
    write(root, SURFACE_B, "surface b v1\n")
    if gitignore:
        write(root, ".gitignore", gitignore)
    return commit(root, "validated implementation")


def _tamper_hex(value: str) -> str:
    flipped = "0" if value[0] != "0" else "1"
    return flipped + value[1:]


@dataclass
class Fixture:
    root: Path
    validated: str
    tree: str
    record: dict
    record_path: str
    artifact_paths: dict[str, str] = field(default_factory=dict)
    artifact_bytes: dict[str, bytes] = field(default_factory=dict)


def build_delivery_fixture(root: Path, validated: str, *, revision: int = 1) -> Fixture:
    """Build (but do not write) a self-consistent, schema-valid delivery record and its artifacts.

    Artifact bytes are written to the working tree immediately (so tests control staging
    explicitly); the record JSON itself is only written by write_record(), so callers may
    tamper with the record dict first.
    """
    repo = GitRepository(root)
    tree = repo.tree(validated)
    short = validated[:12]

    xml_bytes = b"<test-run/>\n"
    log_bytes = b"Unity log line\n"
    human_bytes = "I watched the mana bar drain and refill.\n".encode("utf-8")

    xml_path = f"{EVIDENCE_ROOT}/{TASK_ID}/artifacts/PlayModeTests-{short}.xml"
    log_path = f"{EVIDENCE_ROOT}/{TASK_ID}/artifacts/PlayModeTests-{short}.log"
    human_path = f"{EVIDENCE_ROOT}/{TASK_ID}/artifacts/HumanValidation-{short}.txt"

    write_bytes(root, xml_path, xml_bytes)
    write_bytes(root, log_path, log_bytes)
    write_bytes(root, human_path, human_bytes)

    xml_sha = hash_object_as_committed(root, xml_path, xml_bytes)
    log_sha = hash_object_as_committed(root, log_path, log_bytes)
    human_sha = hash_object_as_committed(root, human_path, human_bytes)

    surface_a_sha = repo.blob(validated, SURFACE_A)
    surface_b_sha = repo.blob(validated, SURFACE_B)

    contract_raw = repo.read(validated, TASK_PATH)
    contract_sha = semantic_json_sha256(contract_raw)
    canon_raw = repo.read(validated, CANON_PATH)
    canon_sha = canonical_text_sha256(canon_raw)

    gate_results = [
        {
            "gate_id": "VAL-001",
            "result": "pass",
            "evidence": [
                {"path": xml_path, "blob_sha": xml_sha},
                {"path": log_path, "blob_sha": log_sha},
            ],
            "notes": "automated",
        },
        {
            "gate_id": "VAL-002",
            "result": "pass",
            "evidence": [
                {"path": xml_path, "blob_sha": xml_sha},
                {"path": human_path, "blob_sha": human_sha},
            ],
            "notes": "human-observed",
        },
    ]

    record_id = f"DEL-{TASK_ID}-{short}"
    record_path = f"{EVIDENCE_ROOT}/{TASK_ID}/records/{record_id}.json"
    record = {
        "schema_version": "1.0",
        "record_type": "delivery",
        "record_id": record_id,
        "task_id": TASK_ID,
        "task_contract": {"path": TASK_PATH, "revision": revision, "sha256": contract_sha},
        "canon": {"path": CANON_PATH, "sha256": canon_sha},
        "validated_state": {"commit": validated, "tree": tree},
        "conformance_surfaces": [
            {"path": SURFACE_A, "blob_sha": surface_a_sha, "role": "owner"},
            {"path": SURFACE_B, "blob_sha": surface_b_sha, "role": "indicator"},
        ],
        "gate_results": gate_results,
        "human_approval": {"required": True, "decision": "approved", "approved_by": "A Human", "notes": "reviewed"},
        "recorded_at": "2026-08-24T00:00:00Z",
        "delivery": {
            "base_commit": validated,
            "candidate_commit": validated,
            "integrated_commit": validated,
            "integrated_tree": tree,
        },
    }

    return Fixture(
        root=root,
        validated=validated,
        tree=tree,
        record=record,
        record_path=record_path,
        artifact_paths={"xml": xml_path, "log": log_path, "human": human_path},
        artifact_bytes={"xml": xml_bytes, "log": log_bytes, "human": human_bytes},
    )


def build_non_delivery_record(root: Path, validated: str, record_type: str) -> tuple[dict, str]:
    """Build (but do not write) a schema-valid baseline or revalidation record."""
    repo = GitRepository(root)
    tree = repo.tree(validated)
    short = validated[:12]
    contract_raw = repo.read(validated, TASK_PATH)
    contract_sha = semantic_json_sha256(contract_raw)
    canon_raw = repo.read(validated, CANON_PATH)
    canon_sha = canonical_text_sha256(canon_raw)
    surface_a_sha = repo.blob(validated, SURFACE_A)
    surface_b_sha = repo.blob(validated, SURFACE_B)

    prefix = {"baseline": "BASE", "revalidation": "REV"}[record_type]
    record_id = f"{prefix}-{TASK_ID}-{short}"
    record_path = f"{EVIDENCE_ROOT}/{TASK_ID}/records/{record_id}.json"
    record: dict = {
        "schema_version": "1.0",
        "record_type": record_type,
        "record_id": record_id,
        "task_id": TASK_ID,
        "task_contract": {"path": TASK_PATH, "revision": 1, "sha256": contract_sha},
        "canon": {"path": CANON_PATH, "sha256": canon_sha},
        "validated_state": {"commit": validated, "tree": tree},
        "conformance_surfaces": [
            {"path": SURFACE_A, "blob_sha": surface_a_sha, "role": "owner"},
            {"path": SURFACE_B, "blob_sha": surface_b_sha, "role": "indicator"},
        ],
        "gate_results": [
            {"gate_id": "VAL-001", "result": "pass", "evidence": [], "notes": ""},
            {"gate_id": "VAL-002", "result": "pass", "evidence": [], "notes": ""},
        ],
        "human_approval": {"required": False, "decision": "not_required", "approved_by": "", "notes": ""},
        "recorded_at": "2026-08-24T00:00:00Z",
    }
    if record_type == "baseline":
        record["baseline"] = {
            "reason_type": "pre_evidence_existing_implementation",
            "summary": "Pre-existing implementation predating evidence tooling.",
        }
    else:
        record["revalidation"] = {
            "basis_record_id": f"DEL-{TASK_ID}-{short}",
            "reason_type": "manual",
            "summary": "Synthetic revalidation for draft-validator scope test.",
        }
    return record, record_path


def write_record(fixture: Fixture) -> None:
    write_json(fixture.root, fixture.record_path, fixture.record)


def stage_full_draft(fixture: Fixture) -> None:
    write_record(fixture)
    stage(fixture.root, fixture.record_path, *fixture.artifact_paths.values())


def assert_invalid(result: ValidationResult, *codes: str) -> None:
    assert result.status == "invalid", result.findings
    found = {finding.code for finding in result.findings}
    for code in codes:
        assert code in found, (code, found, [f.message for f in result.findings])


def fresh(callback, *args) -> None:
    with tempfile.TemporaryDirectory(prefix="draft-evidence-test-") as temp:
        callback(Path(temp), *args)


# 1: happy path.
def scenario_happy_path(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert result.status == "valid", result.findings
    assert result.task_id == TASK_ID
    assert result.record_path == fixture.record_path
    assert result.evidence_references_checked == 4  # xml referenced twice + log + human
    assert result.referenced_artifacts_present == 4
    assert result.unrelated_staged_paths == ()
    assert result.findings == ()


# 2/3: the central NSC-005 regression: an ignored .log artifact referenced by the record
# but absent from the staged index must fail with an exact, safe fix, and running that
# exact fix must make the validator pass.
def scenario_nsc005_ignored_log_regression(root: Path) -> None:
    validated = init_repo(root, gitignore="*.log\n")
    fixture = build_delivery_fixture(root, validated)
    write_record(fixture)
    # Stage everything except the gitignored .log artifact -- exactly the NSC-005 failure.
    stage(root, fixture.record_path, fixture.artifact_paths["xml"], fixture.artifact_paths["human"])

    status = git(root, "status", "--porcelain", "--ignored", "--untracked-files=all")
    assert f"!! {fixture.artifact_paths['log']}" in status, status

    result = validate_draft_evidence(fixture.record_path, root)

    assert result.status == "invalid"
    missing = [f for f in result.findings if f.code == "artifact_missing_from_would_be_commit"]
    assert len(missing) == 1, result.findings
    finding = missing[0]
    assert fixture.artifact_paths["log"] in finding.message
    assert "exists in the working tree" in finding.message
    assert "neither staged nor already committed" in finding.message
    assert "ignored by .gitignore" in finding.message

    expected_fix = f"git add -f -- '{fixture.artifact_paths['log']}'"
    assert expected_fix in result.suggested_commands, result.suggested_commands

    # Execute the validator's exact printed fix command, then rerun: it must now pass.
    command = shlex.split(expected_fix)
    run(root, *command)
    result2 = validate_draft_evidence(fixture.record_path, root)
    assert result2.status == "valid", result2.findings


# 4: a referenced artifact absent from the index, HEAD, and the working tree fails without
# ever inventing a fake staging command for it.
def scenario_missing_artifact_absent_everywhere(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    write_record(fixture)
    stage(root, fixture.record_path, fixture.artifact_paths["xml"], fixture.artifact_paths["human"])
    (root / fixture.artifact_paths["log"]).unlink()

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "artifact_missing_from_would_be_commit")
    finding = next(f for f in result.findings if f.code == "artifact_missing_from_would_be_commit")
    assert "genuinely missing" in finding.message
    assert not any(fixture.artifact_paths["log"] in cmd for cmd in result.suggested_commands)


# 5: a staged artifact whose blob SHA differs from the record fails.
def scenario_staged_artifact_hash_mismatch(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    write_record(fixture)
    stage(root, fixture.record_path, fixture.artifact_paths["xml"], fixture.artifact_paths["human"])
    write_bytes(root, fixture.artifact_paths["log"], b"tampered content, different bytes\n")
    stage(root, fixture.artifact_paths["log"])

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "artifact_blob_mismatch")


# 6: the record exists in the working tree but was never staged.
def scenario_record_not_staged(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    write_record(fixture)
    stage(root, *fixture.artifact_paths.values())  # record itself intentionally not staged

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "record_not_staged")
    finding = next(f for f in result.findings if f.code == "record_not_staged")
    assert "has not been staged" in finding.message


# 7: a draft attempts to modify an already-committed evidence record.
def scenario_modify_committed_record(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)
    commit(root, "record delivery evidence")

    mutated = dict(fixture.record)
    mutated["human_approval"] = dict(mutated["human_approval"])
    mutated["human_approval"]["notes"] = "mutated after commit"
    write_json(root, fixture.record_path, mutated)
    git(root, "add", "--", fixture.record_path)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "record_already_committed")


# 8: a staged deletion of an already-committed evidence record.
def scenario_delete_committed_record(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)
    commit(root, "record delivery evidence")

    git(root, "rm", "--", fixture.record_path)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "record_already_committed")


# 8b: staged deletion of a committed evidence *artifact* is caught by the broader
# immutability check even when the --record target is a different, valid new draft.
def scenario_delete_committed_artifact_while_validating_other_draft(root: Path) -> None:
    validated = init_repo(root)
    fixture1 = build_delivery_fixture(root, validated)
    stage_full_draft(fixture1)
    commit(root, "record delivery evidence")

    write(root, SURFACE_A, "surface a v2\n")
    validated2 = commit(root, "surface change")
    fixture2 = build_delivery_fixture(root, validated2)
    stage_full_draft(fixture2)

    git(root, "rm", "--", fixture1.artifact_paths["log"])

    result = validate_draft_evidence(fixture2.record_path, root)

    assert_invalid(result, "evidence_immutability_violation")


# 9: an unrelated staged file outside the task's evidence root fails and is reported.
def scenario_unrelated_staged_path(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)
    write(root, "Assets/Unrelated/Stray.cs", "oops\n")
    stage(root, "Assets/Unrelated/Stray.cs")

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "unrelated_staged_path")
    assert "Assets/Unrelated/Stray.cs" in result.unrelated_staged_paths


# 10: a referenced artifact already committed at HEAD (unmodified, untouched by this
# draft's staged diff) may satisfy the record without being re-staged.
def scenario_artifact_already_committed_at_head(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage(root, fixture.artifact_paths["log"])
    commit(root, "pre-existing committed artifact")

    write_record(fixture)
    stage(root, fixture.record_path, fixture.artifact_paths["xml"], fixture.artifact_paths["human"])
    # fixture.artifact_paths["log"] intentionally not re-staged: it is already committed.

    result = validate_draft_evidence(fixture.record_path, root)

    assert result.status == "valid", result.findings
    assert result.referenced_artifacts_present == result.evidence_references_checked


# 11: a false task-contract hash fails.
def scenario_false_task_contract_hash(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    fixture.record["task_contract"]["sha256"] = _tamper_hex(fixture.record["task_contract"]["sha256"])
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "recorded_contract_hash_mismatch")


# 12: a false canon hash fails.
def scenario_false_canon_hash(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    fixture.record["canon"]["sha256"] = _tamper_hex(fixture.record["canon"]["sha256"])
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "recorded_canon_hash_mismatch")


# 13: a false conformance-surface blob fails.
def scenario_false_surface_blob(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    fixture.record["conformance_surfaces"][0]["blob_sha"] = _tamper_hex(fixture.record["conformance_surfaces"][0]["blob_sha"])
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "surface_blob_mismatch_at_validated_commit")


# 14: a surface changed at current HEAD (after the validated commit) fails.
def scenario_surface_changed_at_head(root: Path) -> None:
    validated = init_repo(root)
    write(root, SURFACE_A, "surface a v2\n")
    commit(root, "surface change")  # HEAD now ahead of validated

    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "surface_changed_at_head")


# 15: a completion-gate set mismatch (record gates != current contract gates) fails.
def scenario_gate_set_mismatch(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    fixture.record["gate_results"].append({
        "gate_id": "VAL-999",
        "result": "pass",
        "evidence": [{"path": fixture.artifact_paths["xml"], "blob_sha": fixture.record["gate_results"][0]["evidence"][0]["blob_sha"]}],
        "notes": "",
    })
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "completion_gate_set_mismatch")


# 16: required human approval with a blank approved_by fails.
def scenario_approval_required_blank(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    fixture.record["human_approval"] = {"required": True, "decision": "approved", "approved_by": "", "notes": ""}
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "human_approval_insufficient")


# 17: a contradictory not-required approval fails.
def scenario_approval_contradictory(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    fixture.record["human_approval"] = {"required": False, "decision": "approved", "approved_by": "", "notes": ""}
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "human_approval_contradictory")


# 18: a validated-state tree mismatch fails.
def scenario_validated_tree_mismatch(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    bad_tree = _tamper_hex(fixture.record["validated_state"]["tree"])
    fixture.record["validated_state"]["tree"] = bad_tree
    fixture.record["delivery"]["integrated_tree"] = bad_tree
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "validated_tree_mismatch")


# 19: a validated commit that is not an ancestor of (nor equal to) HEAD fails.
def scenario_validated_commit_not_ancestor(root: Path) -> None:
    validated = init_repo(root)

    run(root, "git", "checkout", "--orphan", "unrelated")
    run(root, "git", "rm", "-rf", "--cached", ".")
    write(root, "unrelated.txt", "unrelated\n")
    alien = commit(root, "unrelated root")
    run(root, "git", "checkout", "main")
    alien_tree = git(root, "rev-parse", f"{alien}^{{tree}}")

    fixture = build_delivery_fixture(root, validated)
    fixture.record["validated_state"] = {"commit": alien, "tree": alien_tree}
    fixture.record["delivery"] = {
        "base_commit": alien, "candidate_commit": alien, "integrated_commit": alien, "integrated_tree": alien_tree,
    }
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "validated_commit_not_ancestor")


# 20: delivery.base_commit not an ancestor of validated_state.commit fails.
def scenario_base_commit_not_ancestor(root: Path) -> None:
    validated = init_repo(root)

    run(root, "git", "checkout", "--orphan", "unrelated")
    run(root, "git", "rm", "-rf", "--cached", ".")
    write(root, "unrelated.txt", "unrelated\n")
    alien = commit(root, "unrelated root")
    run(root, "git", "checkout", "main")

    fixture = build_delivery_fixture(root, validated)
    fixture.record["delivery"]["base_commit"] = alien
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "base_commit_not_ancestor")


# 21: delivery.candidate_commit neither an ancestor of nor equal to validated_state.commit fails.
def scenario_candidate_commit_not_ancestor(root: Path) -> None:
    validated = init_repo(root)

    run(root, "git", "checkout", "-b", "side", validated)
    write(root, "side.txt", "side\n")
    side = commit(root, "side branch commit")
    run(root, "git", "checkout", "main")

    fixture = build_delivery_fixture(root, validated)
    fixture.record["delivery"]["candidate_commit"] = side
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "candidate_commit_not_ancestor")


# 22/23: the validator itself never stages or commits anything, on either a valid or an
# invalid draft.
def scenario_no_side_effects(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    before_head = git(root, "rev-parse", "HEAD")
    before_staged = git(root, "diff", "--cached", "--name-status")
    before_log_count = len(git(root, "log", "--format=%H").splitlines())

    result_valid = validate_draft_evidence(fixture.record_path, root)
    assert result_valid.status == "valid"

    write(root, "Assets/Unrelated/Stray.cs", "oops\n")
    stage(root, "Assets/Unrelated/Stray.cs")
    result_invalid = validate_draft_evidence(fixture.record_path, root)
    assert result_invalid.status == "invalid"
    git(root, "reset", "--", "Assets/Unrelated/Stray.cs")  # undo test setup, not a validator side effect

    after_head = git(root, "rev-parse", "HEAD")
    after_staged = git(root, "diff", "--cached", "--name-status")
    after_log_count = len(git(root, "log", "--format=%H").splitlines())

    assert before_head == after_head
    assert before_staged == after_staged
    assert before_log_count == after_log_count


# 24: --json returns a stable, machine-readable summary (both via the Python API and the CLI).
def scenario_json_output(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["status"] == "valid"
    assert payload["task_id"] == TASK_ID
    assert payload["record_path"] == fixture.record_path
    assert isinstance(payload["evidence_references_checked"], int)
    assert isinstance(payload["referenced_artifacts_present"], int)
    assert payload["unrelated_staged_paths"] == []
    assert payload["findings"] == []
    assert isinstance(payload["suggested_commands"], list)

    script = Path(__file__).resolve().parent / "validate_draft_evidence.py"
    cli = run(root, "python3", str(script), "--record", fixture.record_path, "--root", str(root), "--json")
    cli_payload = json.loads(cli.stdout)
    assert cli_payload == payload


# 25: end-to-end -- a validator PASS corresponds to the intended normal evidence workflow:
# once actually committed, the existing current-conformance evaluator derives conformant.
def scenario_end_to_end_conformant(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)
    assert result.status == "valid", result.findings

    commit(root, f"Record {TASK_ID} delivery evidence")

    state = evaluate_current_conformance(root, TASK_ID)
    assert state.state == "conformant", state.to_dict()
    assert state.selected_record_id == fixture.record["record_id"]


# 26: a referenced artifact that is already committed at HEAD but staged for deletion must not
# be counted as present in the would-be commit, even though the existing immutability rule
# independently flags the deletion too.
def scenario_staged_deleted_referenced_artifact(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage(root, fixture.artifact_paths["log"])
    commit(root, "pre-existing committed artifact")

    write_record(fixture)
    stage(root, fixture.record_path, fixture.artifact_paths["xml"], fixture.artifact_paths["human"])
    git(root, "rm", "--", fixture.artifact_paths["log"])

    result = validate_draft_evidence(fixture.record_path, root)

    assert result.status == "invalid", result.findings
    codes = {f.code for f in result.findings}
    assert "artifact_missing_from_would_be_commit" in codes, result.findings
    missing = next(f for f in result.findings if f.code == "artifact_missing_from_would_be_commit")
    assert fixture.artifact_paths["log"] in missing.message
    assert "staged for deletion" in missing.message
    assert result.evidence_references_checked == 4
    assert result.referenced_artifacts_present == 3  # the deleted log must not be counted as present


# 26b: an additional new file staged under the same task's records/ directory must fail, even
# though the supplied --record is itself entirely valid, because TaskGraph's
# load_committed_records() would load and validate that extra file too after commit.
def scenario_extra_staged_record_rejected(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    extra_path = f"{EVIDENCE_ROOT}/{TASK_ID}/records/EXTRA.json"
    write_json(root, extra_path, {"not": "a real record"})
    stage(root, extra_path)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "extra_staged_record")
    finding = next(f for f in result.findings if f.code == "extra_staged_record")
    assert extra_path in finding.message
    assert fixture.record_path in finding.message

    # Reset only the extra test-setup path; the main record remains valid on its own.
    git(root, "reset", "--", extra_path)
    (root / extra_path).unlink()
    result2 = validate_draft_evidence(fixture.record_path, root)
    assert result2.status == "valid", result2.findings


# 26c: same as above, but the extra staged file is malformed/non-JSON -- TaskGraph would reject
# it after commit too, so this validator must not say VALID while it is staged.
def scenario_extra_staged_malformed_record_rejected(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)

    extra_path = f"{EVIDENCE_ROOT}/{TASK_ID}/records/EXTRA.txt"
    write(root, extra_path, "not json at all\n")
    stage(root, extra_path)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "extra_staged_record")
    finding = next(f for f in result.findings if f.code == "extra_staged_record")
    assert extra_path in finding.message

    git(root, "reset", "--", extra_path)
    (root / extra_path).unlink()
    result2 = validate_draft_evidence(fixture.record_path, root)
    assert result2.status == "valid", result2.findings


# 27: a draft record staged at a repository path previously used by an evidence record that was
# committed and later deleted must be rejected: TaskGraph's load_committed_records() rejects any
# immutable record whose path history has more than one creation/modification event, so this
# would-be commit would produce a record TaskGraph could never load.
def scenario_recreated_historical_record_path(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    stage_full_draft(fixture)
    commit(root, "record delivery evidence")

    git(root, "rm", "--", fixture.record_path)
    commit(root, "delete delivery record")
    assert not (root / fixture.record_path).exists()

    new_fixture = build_delivery_fixture(root, validated)
    assert new_fixture.record_path == fixture.record_path  # same validated commit -> same deterministic path
    write_record(new_fixture)
    stage(root, new_fixture.record_path)

    result = validate_draft_evidence(new_fixture.record_path, root)

    assert_invalid(result, "record_path_previously_used")


# 28/29: baseline and revalidation records must never receive VALID from this delivery-only tool,
# since it does not validate the revalidation basis graph they require.
def scenario_baseline_record_type_unsupported(root: Path) -> None:
    validated = init_repo(root)
    record, record_path = build_non_delivery_record(root, validated, "baseline")
    write_json(root, record_path, record)
    stage(root, record_path)

    result = validate_draft_evidence(record_path, root)

    assert_invalid(result, "unsupported_record_type")


def scenario_revalidation_record_type_unsupported(root: Path) -> None:
    validated = init_repo(root)
    record, record_path = build_non_delivery_record(root, validated, "revalidation")
    write_json(root, record_path, record)
    stage(root, record_path)

    result = validate_draft_evidence(record_path, root)

    assert_invalid(result, "unsupported_record_type")


# 30: a conformance surface whose path resolves to a committed directory/tree (not a blob) at the
# validated commit must be rejected, even if the record's declared blob_sha equals that tree's SHA.
def scenario_directory_conformance_surface_rejected(root: Path) -> None:
    validated = init_repo(root)
    fixture = build_delivery_fixture(root, validated)
    dir_path = "Assets/Foo"
    dir_sha = git(root, "rev-parse", f"{validated}:{dir_path}")
    fixture.record["conformance_surfaces"].append({"path": dir_path, "blob_sha": dir_sha, "role": "owner"})
    stage_full_draft(fixture)

    result = validate_draft_evidence(fixture.record_path, root)

    assert_invalid(result, "surface_not_a_blob_at_validated_commit")


# Fatal (non-record-level) failure: not a Git repository at all.
def scenario_not_a_git_repository(root: Path) -> None:
    (root / "Pipeline" / "TaskGraph" / "evidence" / TASK_ID / "records").mkdir(parents=True)
    try:
        validate_draft_evidence(f"{EVIDENCE_ROOT}/{TASK_ID}/records/DEL-{TASK_ID}-x.json", root)
    except DraftEvidenceError:
        return
    raise AssertionError("Expected DraftEvidenceError for a non-Git directory.")


def main() -> int:
    fresh(scenario_happy_path)
    fresh(scenario_nsc005_ignored_log_regression)
    fresh(scenario_missing_artifact_absent_everywhere)
    fresh(scenario_staged_artifact_hash_mismatch)
    fresh(scenario_record_not_staged)
    fresh(scenario_modify_committed_record)
    fresh(scenario_delete_committed_record)
    fresh(scenario_delete_committed_artifact_while_validating_other_draft)
    fresh(scenario_unrelated_staged_path)
    fresh(scenario_artifact_already_committed_at_head)
    fresh(scenario_false_task_contract_hash)
    fresh(scenario_false_canon_hash)
    fresh(scenario_false_surface_blob)
    fresh(scenario_surface_changed_at_head)
    fresh(scenario_gate_set_mismatch)
    fresh(scenario_approval_required_blank)
    fresh(scenario_approval_contradictory)
    fresh(scenario_validated_tree_mismatch)
    fresh(scenario_validated_commit_not_ancestor)
    fresh(scenario_base_commit_not_ancestor)
    fresh(scenario_candidate_commit_not_ancestor)
    fresh(scenario_no_side_effects)
    fresh(scenario_json_output)
    fresh(scenario_end_to_end_conformant)
    fresh(scenario_staged_deleted_referenced_artifact)
    fresh(scenario_extra_staged_record_rejected)
    fresh(scenario_extra_staged_malformed_record_rejected)
    fresh(scenario_recreated_historical_record_path)
    fresh(scenario_baseline_record_type_unsupported)
    fresh(scenario_revalidation_record_type_unsupported)
    fresh(scenario_directory_conformance_surface_rejected)
    fresh(scenario_not_a_git_repository)
    print("validate_draft_evidence_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
