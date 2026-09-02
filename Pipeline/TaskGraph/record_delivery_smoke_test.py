from __future__ import annotations

import io
import json
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from conformance_records import CANON_PATH, GitRepository
from current_conformance import evaluate_current_conformance
from record_delivery import (
    DeliveryResult,
    PublicationFailure,
    RecordDeliveryError,
    create_delivery_package,
    hash_object_as_committed,
    hash_object_raw,
    print_human_report,
)
from taskcontrol import command_state
from validate_draft_evidence import validate_draft_evidence

TASK_ID = "NSC-900"
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


def write_json(root: Path, path: str, value: dict) -> None:
    write(root, path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def commit(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


def task_contract(revision: int = 1, gate_ids: tuple[str, ...] = ("VAL-002", "VAL-001")) -> dict:
    return {
        "schema_version": "2.0",
        "id": TASK_ID,
        "contract_revision": revision,
        "contract_disposition": "active",
        "title": "Synthetic delivery task",
        "reconciliation_key": "synthetic-delivery",
        "kind": "implementation",
        "execution_scope": "single_agent",
        "completion_gates": [
            {"gate_id": gate_id, "reference": "test", "requirement": f"{gate_id} passes"}
            for gate_id in gate_ids
        ],
    }


def init_repo(
    root: Path, *, gate_ids: tuple[str, ...] = ("VAL-002", "VAL-001"), gitignore: str = "", gitattributes: str = "",
) -> str:
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.email", "delivery-test@example.invalid")
    run(root, "git", "config", "user.name", "Delivery Test User")
    write_json(root, TASK_PATH, task_contract(gate_ids=gate_ids))
    write(root, CANON_PATH, "# Canon\n\nRules.\n")
    write(root, SURFACE_A, "surface a v1\n")
    write(root, SURFACE_B, "surface b v1\n")
    if gitignore:
        write(root, ".gitignore", gitignore)
    if gitattributes:
        write(root, ".gitattributes", gitattributes)
    return commit(root, "validated implementation")


def unity_xml(*, result: str = "Passed", total: int = 3, passed: int = 3, failed: int = 0, skipped: int = 0) -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<test-run id="1" result="{result}" total="{total}" passed="{passed}" '
        f'failed="{failed}" skipped="{skipped}" inconclusive="0">\n'
        f'  <test-suite name="Suite" result="{result}"/>\n'
        f"</test-run>\n"
    )


def base_spec(validated: str, *, base: str | None = None, candidate: str | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "task_id": TASK_ID,
        "validated_commit": validated,
        "base_commit": base or validated,
        "candidate_commit": candidate or validated,
        "surfaces": [
            {"path": SURFACE_A, "role": "owner"},
            {"path": SURFACE_B, "role": "indicator"},
        ],
        "artifacts": [
            {"id": "playmode_results", "type": "unity_test_results", "source_path": "", "name": "PlayModeTests"},
            {"id": "unity_log", "type": "unity_log", "source_path": "", "name": "PlayModeTests"},
            {"id": "human_validation", "type": "human_validation", "source_path": "", "name": "HumanValidation"},
        ],
        "gates": [
            {"gate_id": "VAL-001", "evidence": ["playmode_results", "unity_log"], "notes": "automated"},
            {"gate_id": "VAL-002", "evidence": ["playmode_results", "human_validation"], "notes": "human-observed"},
        ],
        "human_approval": {"required": True, "decision": "approved", "approved_by": "", "notes": "reviewed live"},
    }


def write_external_sources(external: Path, *, xml_content: str | None = None, log_content: str = "Unity log line\n",
                            human_content: str = "I watched the mana bar drain and refill.\n") -> dict:
    external.mkdir(parents=True, exist_ok=True)
    xml_path = external / "test-results.xml"
    log_path = external / "unity.log"
    human_path = external / "human-validation.txt"
    xml_path.write_text(unity_xml() if xml_content is None else xml_content, encoding="utf-8")
    log_path.write_bytes(log_content.encode("utf-8"))
    human_path.write_text(human_content, encoding="utf-8")
    return {"playmode_results": xml_path, "unity_log": log_path, "human_validation": human_path}


def wire_sources(spec: dict, sources: dict[str, Path]) -> None:
    for artifact in spec["artifacts"]:
        artifact["source_path"] = str(sources[artifact["id"]])


def write_spec(root: Path, spec: dict, name: str = "spec.json") -> Path:
    # Written outside the Git working tree so it never dirties the repository.
    path = root.parent / name
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def expect_error(callback, message_fragment: str | None = None) -> None:
    try:
        callback()
    except RecordDeliveryError as exc:
        if message_fragment and message_fragment not in str(exc):
            raise AssertionError(f"Expected fragment {message_fragment!r} in error, got: {exc}")
        return
    raise AssertionError("Expected RecordDeliveryError, none was raised.")


def fresh(callback, *args) -> None:
    with tempfile.TemporaryDirectory(prefix="record-delivery-test-") as temp:
        callback(Path(temp), *args)


def token_usage_metric(*, total_tokens: int = 30) -> dict:
    supervisor_total = 20
    crew_total = total_tokens - supervisor_total

    def source(run_id: str, source_path: str, input_tokens: int, output_tokens: int, total: int) -> dict:
        return {
            "run_id": run_id,
            "source": source_path,
            "complete": True,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
            "reported_input_tokens": input_tokens,
            "reported_output_tokens": output_tokens,
            "reported_total_tokens": total,
            "invocation_count": 1,
            "usage_available_invocation_count": 1,
            "missing_usage_invocation_count": 0,
            "errors": [],
        }

    supervisor_run = source(
        "supervisor-run",
        f"{TASK_ID}/supervisor-run/progress.jsonl",
        10,
        5,
        supervisor_total,
    )
    crew_run = source(
        "crew-run",
        "Pipeline/ExecutionCrew/outputs/crew-run/crew_result.json",
        3,
        4,
        crew_total,
    )

    def breakdown(run: dict) -> dict:
        return {
            "status": "complete",
            "complete": True,
            "input_tokens": run["input_tokens"],
            "output_tokens": run["output_tokens"],
            "total_tokens": run["total_tokens"],
            "reported_input_tokens": run["input_tokens"],
            "reported_output_tokens": run["output_tokens"],
            "reported_total_tokens": run["total_tokens"],
            "run_count": 1,
            "invocation_count": 1,
            "usage_available_invocation_count": 1,
            "missing_usage_invocation_count": 0,
            "runs": [run],
            "errors": [],
        }

    return {
        "schema_version": "1.0",
        "task_id": TASK_ID,
        "scope": "through_delivery_evidence",
        "status": "complete",
        "complete": True,
        "input_tokens": 13,
        "output_tokens": 9,
        "total_tokens": total_tokens,
        "reported_input_tokens": 13,
        "reported_output_tokens": 9,
        "reported_total_tokens": total_tokens,
        "breakdown": {
            "supervisor": breakdown(supervisor_run),
            "execution_crew": breakdown(crew_run),
        },
    }


def write_token_usage(path: Path, *, total_tokens: int = 30) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(token_usage_metric(total_tokens=total_tokens), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


# 1/2/3/4/5/6/7/8: happy path, computed hashes, blob shas, validated commit/tree,
# artifact hashes, record shape valid, gate order, unity totals reported.
def scenario_happy_path(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    result = create_delivery_package(spec_path, root)

    assert result.validated_commit == validated
    assert result.validated_tree == git(root, "rev-parse", f"{validated}^{{tree}}")
    assert result.record_path == f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/DEL-{TASK_ID}-{validated[:12]}.json"
    assert len(result.created_paths) == 4
    assert not (root / ".git" / "index.lock").exists()

    record_full_path = root / result.record_path
    record = json.loads(record_full_path.read_text(encoding="utf-8"))

    # Task/canon hashes computed from committed validated state.
    from conformance_records import canonical_text_sha256, semantic_json_sha256
    repo = GitRepository(root)
    assert record["task_contract"]["sha256"] == semantic_json_sha256(repo.read(validated, TASK_PATH))
    assert record["canon"]["sha256"] == canonical_text_sha256(repo.read(validated, CANON_PATH))
    assert record["validated_state"] == {"commit": validated, "tree": result.validated_tree}

    # Surface Git blob SHAs correct.
    surfaces_by_path = {s["path"]: s for s in record["conformance_surfaces"]}
    assert surfaces_by_path[SURFACE_A]["blob_sha"] == repo.blob(validated, SURFACE_A)
    assert surfaces_by_path[SURFACE_B]["blob_sha"] == repo.blob(validated, SURFACE_B)

    # Artifact Git hashes correct (path-aware filtered hash of the exact published bytes,
    # i.e. what `git add -f` will actually store once the printed stage command runs).
    import record_delivery as rd
    for gate in record["gate_results"]:
        for evidence in gate["evidence"]:
            published_bytes = (root / evidence["path"]).read_bytes()
            assert evidence["blob_sha"] == rd.hash_object_as_committed(root, evidence["path"], published_bytes)

    # Record shape passes the existing authoritative validator.
    from conformance_records import validate_record_shape
    validate_record_shape(record, result.record_path)

    # Completion gate order follows the task contract (VAL-002 then VAL-001).
    assert [g["gate_id"] for g in record["gate_results"]] == ["VAL-002", "VAL-001"]

    # Unity totals reported.
    assert len(result.unity_reports) == 1
    _, report = result.unity_reports[0]
    assert (report.result, report.total, report.passed, report.failed, report.skipped) == ("Passed", 3, 3, 0, 0)

    # Human approval fell back to git user.name.
    assert record["human_approval"]["approved_by"] == "Delivery Test User"

    # Nothing staged or committed by the tool itself: every created path is untracked.
    status_lines = git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    untracked = {line[3:] for line in status_lines if line.startswith("??")}
    assert set(result.created_paths) <= untracked, (result.created_paths, status_lines)
    assert git(root, "diff", "--cached", "--name-only") == ""
    assert git(root, "rev-parse", "HEAD") == validated

    # Stage command uses git add -f and enumerates exactly the generated files.
    assert result.stage_command[:3] == ("git", "add", "-f")
    assert set(result.stage_command[4:]) == set(result.created_paths)

    # Validate-draft command targets the exact generated record path.
    assert result.validate_command == (
        "python", "Pipeline/TaskGraph/validate_draft_evidence.py", "--record", result.record_path,
    )


# 9: failed Unity XML rejected.
def scenario_failed_unity_xml(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(
        external,
        xml_content=unity_xml(result="Failed", total=3, passed=2, failed=1, skipped=0),
    )
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "not 'Passed'")


# 10: malformed Unity XML rejected.
def scenario_malformed_unity_xml(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external, xml_content="<not-xml unterminated")
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "Malformed")


# 11: missing artifact source file rejected.
def scenario_missing_artifact(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["artifacts"][1]["source_path"] = str(root.parent / "does-not-exist.log")
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "regular file")


# 12: empty human validation rejected.
def scenario_empty_human_validation(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external, human_content="   \n\n  ")
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "meaningful text")


# 13: missing surface rejected (surface path not a committed blob).
def scenario_missing_surface(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["surfaces"].append({"path": "Assets/Foo/DoesNotExist.cs", "role": "missing"})
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root))


# 14: duplicate surface rejected.
def scenario_duplicate_surface(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["surfaces"].append({"path": SURFACE_A, "role": "duplicate"})
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "Duplicate")


# 15: unknown/duplicate/missing gate rejected.
def scenario_gate_mismatch(root: Path, mode: str) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    if mode == "unknown":
        spec["gates"].append({"gate_id": "VAL-999", "evidence": ["playmode_results"], "notes": ""})
    elif mode == "missing":
        spec["gates"] = [spec["gates"][0]]
    elif mode == "duplicate":
        spec["gates"].append(dict(spec["gates"][0]))
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root))


# 16: unknown artifact reference rejected.
def scenario_unknown_artifact_reference(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["gates"][0]["evidence"].append("does_not_exist")
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "unknown artifact")


# 17: dirty repository rejected.
def scenario_dirty_repo(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    write(root, "uncommitted.txt", "dirty\n")
    expect_error(lambda: create_delivery_package(spec_path, root), "clean")


# 18: HEAD != validated_commit rejected.
def scenario_head_mismatch(root: Path) -> None:
    validated = init_repo(root)
    write(root, "later.txt", "later\n")
    commit(root, "later commit")
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "HEAD")


# 19: base_commit not an ancestor rejected.
def scenario_base_not_ancestor(root: Path) -> None:
    validated = init_repo(root)
    run(root, "git", "checkout", "--orphan", "unrelated")
    run(root, "git", "rm", "-rf", "--cached", ".")
    write(root, "unrelated.txt", "unrelated\n")
    unrelated = commit(root, "unrelated root")
    run(root, "git", "checkout", "main")
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated, base=unrelated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "base_commit")


# 20: candidate_commit not ancestor/equal rejected.
def scenario_candidate_not_ancestor(root: Path) -> None:
    validated = init_repo(root)
    run(root, "git", "checkout", "-b", "side", validated)
    write(root, "side.txt", "side\n")
    side = commit(root, "side branch commit")
    run(root, "git", "checkout", "main")
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated, candidate=side)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "candidate_commit")


# 21: existing destination artifact rejected.
def scenario_existing_artifact(root: Path) -> None:
    # The colliding stray file is placed after the validated commit and matched by a
    # static (sha-independent) .gitignore pattern, so it never dirties the working tree
    # yet must still be caught by the tool's own filesystem overwrite guard.
    validated = init_repo(root, gitignore="Pipeline/TaskGraph/evidence/*/artifacts/PlayModeTests-*.xml\n")
    collide = root / f"Pipeline/TaskGraph/evidence/{TASK_ID}/artifacts/PlayModeTests-{validated[:12]}.xml"
    collide.parent.mkdir(parents=True, exist_ok=True)
    collide.write_text("pre-existing\n", encoding="utf-8")
    assert git(root, "status", "--porcelain") == ""
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "overwrite")


# 22: existing record ID rejected.
def scenario_existing_record(root: Path) -> None:
    validated = init_repo(root, gitignore=f"Pipeline/TaskGraph/evidence/*/records/DEL-{TASK_ID}-*.json\n")
    record_path = root / f"Pipeline/TaskGraph/evidence/{TASK_ID}/records/DEL-{TASK_ID}-{validated[:12]}.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text("{}", encoding="utf-8")
    assert git(root, "status", "--porcelain") == ""
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "overwrite")


# 23: unknown spec fields rejected.
def scenario_unknown_field(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["unexpected_field"] = "surprise"
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "differ from the delivery-spec schema")


# 24/25: ignored .log artifact is not omitted from the stage command, which uses -f
# and enumerates exact generated files.
def scenario_ignored_log_not_omitted(root: Path) -> None:
    validated_dummy_root = init_repo(root)
    write(root, ".gitignore", "*.log\n")
    validated = commit(root, "add gitignore")
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    result = create_delivery_package(spec_path, root)

    log_paths = [path for path in result.created_paths if path.endswith(".log")]
    assert len(log_paths) == 1, result.created_paths
    log_path = log_paths[0]

    status = git(root, "status", "--porcelain", "--ignored", "--untracked-files=all")
    assert f"!! {log_path}" in status, status  # proves git itself is ignoring the file
    assert log_path in result.stage_command, result.stage_command  # tool still lists it
    assert result.stage_command[:3] == ("git", "add", "-f")
    assert set(result.stage_command[4:]) == set(result.created_paths)


# 26/27: the tool does not stage or commit anything automatically.
def scenario_no_auto_stage_or_commit(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    create_delivery_package(spec_path, root)

    staged = git(root, "diff", "--cached", "--name-only")
    assert staged == "", f"Tool staged files automatically: {staged!r}"
    assert git(root, "rev-parse", "HEAD") == validated, "Tool committed automatically."
    log_count = len(git(root, "log", "--format=%H").splitlines())
    assert log_count == 1


# 28: a failed preflight leaves the repository unchanged.
def scenario_failed_preflight_no_side_effects(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["gates"].append({"gate_id": "VAL-999", "evidence": ["playmode_results"], "notes": ""})
    spec_path = write_spec(root, spec)

    before_head = git(root, "rev-parse", "HEAD")
    before_status = git(root, "status", "--porcelain")
    before_listing = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if ".git" not in p.parts)

    expect_error(lambda: create_delivery_package(spec_path, root))

    after_head = git(root, "rev-parse", "HEAD")
    after_status = git(root, "status", "--porcelain")
    after_listing = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if ".git" not in p.parts)
    assert before_head == after_head
    assert before_status == after_status
    assert before_listing == after_listing


# 29: after executing the printed staging command and committing, the existing
# current-conformance evaluator derives conformant for the synthetic task.
def scenario_end_to_end_conformant(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    result = create_delivery_package(spec_path, root)

    run(root, *result.stage_command)
    staged = set(git(root, "diff", "--cached", "--name-only").splitlines())
    assert staged == set(result.created_paths)

    commit(root, f"Record {TASK_ID} delivery evidence")

    state = evaluate_current_conformance(root, TASK_ID)
    assert state.state == "conformant", state.to_dict()
    assert state.selected_record_id == result.record_id
    assert state.total_tokens_used is None
    assert state.token_usage_complete is None
    assert state.token_usage_status == "unavailable"


# 30: synthetic Git clean-filter/EOL normalization regression. Proves the recorded
# blob_sha is the one Git will actually store once the printed stage command runs
# (not a raw hash-object of the copied bytes), that the working-tree artifact keeps the
# exact source bytes, and that the committed package still derives conformant.
def scenario_filtered_hash_matches_committed_blob(root: Path) -> None:
    validated = init_repo(root, gitattributes="*.txt text eol=lf\n")
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    crlf_bytes = b"I watched the mana bar drain and refill.\r\n"
    sources["human_validation"].write_bytes(crlf_bytes)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    result = create_delivery_package(spec_path, root)

    record = json.loads((root / result.record_path).read_text(encoding="utf-8"))
    human_evidence = next(
        evidence
        for gate in record["gate_results"]
        for evidence in gate["evidence"]
        if evidence["path"].startswith(f"Pipeline/TaskGraph/evidence/{TASK_ID}/artifacts/HumanValidation-")
    )

    # 1. The published working-tree artifact still contains the exact CRLF source bytes.
    published_bytes = (root / human_evidence["path"]).read_bytes()
    assert published_bytes == crlf_bytes

    # 2. Raw `git hash-object --stdin` differs from the filtered/path-aware hash here.
    raw_hash = hash_object_raw(root, published_bytes)
    filtered_hash = hash_object_as_committed(root, human_evidence["path"], published_bytes)
    assert raw_hash != filtered_hash, "fixture did not actually exercise a clean-filter difference"

    # 3. The delivery record contains the filtered/path-aware SHA, not the raw one.
    assert human_evidence["blob_sha"] == filtered_hash
    assert human_evidence["blob_sha"] != raw_hash

    # 4. Execute the packager's exact generated stage command.
    run(root, *result.stage_command)

    # 5. The staged blob exactly matches the record.
    staged_sha = git(root, "rev-parse", f":{human_evidence['path']}")
    assert staged_sha == human_evidence["blob_sha"]

    # 6. Commit the generated package.
    commit(root, f"Record {TASK_ID} delivery evidence")

    # 7/8. The existing current-conformance evaluator derives conformant.
    state = evaluate_current_conformance(root, TASK_ID)
    assert state.state == "conformant", state.to_dict()
    assert state.selected_record_id == result.record_id


# 31: a committed directory/tree cannot be used as a conformance surface, even though
# `git rev-parse <commit>:<dir>` yields a syntactically valid-looking 40-character SHA.
def scenario_directory_surface_rejected(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec["surfaces"].append({"path": "Assets/Foo", "role": "directory"})
    spec_path = write_spec(root, spec)
    expect_error(lambda: create_delivery_package(spec_path, root), "not a blob")


# 32: the printed human report inserts an exact VALIDATE DRAFT step, targeting the
# generated record path, between STAGE and CHECK/COMMIT.
def scenario_prints_validate_draft_between_stage_and_commit(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    result = create_delivery_package(spec_path, root)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_human_report(result)
    report = buffer.getvalue()

    stage_index = report.index("STAGE:")
    validate_index = report.index("VALIDATE DRAFT:")
    check_index = report.index("CHECK:")
    commit_index = report.index("COMMIT:")
    assert stage_index < validate_index < check_index < commit_index, report

    expected_validate_line = f"python Pipeline/TaskGraph/validate_draft_evidence.py --record {result.record_path}"
    assert expected_validate_line in report, report


def scenario_optional_token_usage_is_packaged_and_displayed(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    metric_path = write_token_usage(external / "token-usage.json")
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    result = create_delivery_package(spec_path, root, metric_path)
    sidecar = f"Pipeline/TaskGraph/evidence/{TASK_ID}/metrics/token-usage.json"
    assert sidecar in result.created_paths
    assert json.loads((root / sidecar).read_text(encoding="utf-8")) == token_usage_metric()

    run(root, *result.stage_command)
    draft = validate_draft_evidence(result.record_path, root)
    assert draft.status == "valid", draft.findings
    commit(root, f"Record {TASK_ID} delivery evidence with token usage")
    state = evaluate_current_conformance(root, TASK_ID)
    assert state.state == "conformant", state.to_dict()
    assert state.total_tokens_used == 30
    assert state.token_usage_complete is True
    assert state.token_usage_status == "complete"
    assert state.token_usage_scope == "through_delivery_evidence"

    output = io.StringIO()
    with patch("taskcontrol.evaluate_current_conformance", return_value=state):
        with redirect_stdout(output):
            assert command_state(TASK_ID, as_json=True) == 0
    rendered = json.loads(output.getvalue())
    assert rendered["total_tokens_used"] == 30
    assert rendered["token_usage_complete"] is True
    assert rendered["token_usage_status"] == "complete"

    output = io.StringIO()
    with patch("taskcontrol.evaluate_current_conformance", return_value=state):
        with redirect_stdout(output):
            assert command_state(TASK_ID) == 0
    assert "total_tokens_used: 30" in output.getvalue()


def scenario_conflicting_token_usage_is_not_overwritten(root: Path) -> None:
    init_repo(root)
    existing = write_token_usage(
        root / f"Pipeline/TaskGraph/evidence/{TASK_ID}/metrics/token-usage.json",
        total_tokens=31,
    )
    validated = commit(root, "Commit existing immutable token usage")
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    candidate = write_token_usage(external / "token-usage.json", total_tokens=30)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)

    before = existing.read_bytes()
    expect_error(
        lambda: create_delivery_package(spec_path, root, candidate),
        "different identity",
    )
    assert existing.read_bytes() == before


def scenario_malformed_token_usage_is_non_authoritative(root: Path) -> None:
    validated = init_repo(root)
    external = root.parent / "external-sources"
    sources = write_external_sources(external)
    spec = base_spec(validated)
    wire_sources(spec, sources)
    spec_path = write_spec(root, spec)
    result = create_delivery_package(spec_path, root)
    run(root, *result.stage_command)
    commit(root, f"Record {TASK_ID} delivery evidence")

    malformed = root / f"Pipeline/TaskGraph/evidence/{TASK_ID}/metrics/token-usage.json"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text('{"task_id":"NSC-999","total_tokens":NaN}\n', encoding="utf-8")
    commit(root, "Commit malformed non-authoritative telemetry fixture")

    state = evaluate_current_conformance(root, TASK_ID)
    assert state.state == "conformant", state.to_dict()
    assert state.total_tokens_used is None
    assert state.token_usage_complete is False
    assert state.token_usage_status == "invalid"


def main() -> int:
    fresh(scenario_happy_path)
    fresh(scenario_failed_unity_xml)
    fresh(scenario_malformed_unity_xml)
    fresh(scenario_missing_artifact)
    fresh(scenario_empty_human_validation)
    fresh(scenario_missing_surface)
    fresh(scenario_duplicate_surface)
    for mode in ("unknown", "missing", "duplicate"):
        fresh(scenario_gate_mismatch, mode)
    fresh(scenario_unknown_artifact_reference)
    fresh(scenario_dirty_repo)
    fresh(scenario_head_mismatch)
    fresh(scenario_base_not_ancestor)
    fresh(scenario_candidate_not_ancestor)
    fresh(scenario_existing_artifact)
    fresh(scenario_existing_record)
    fresh(scenario_unknown_field)
    fresh(scenario_ignored_log_not_omitted)
    fresh(scenario_no_auto_stage_or_commit)
    fresh(scenario_failed_preflight_no_side_effects)
    fresh(scenario_end_to_end_conformant)
    fresh(scenario_filtered_hash_matches_committed_blob)
    fresh(scenario_directory_surface_rejected)
    fresh(scenario_prints_validate_draft_between_stage_and_commit)
    fresh(scenario_optional_token_usage_is_packaged_and_displayed)
    fresh(scenario_conflicting_token_usage_is_not_overwritten)
    fresh(scenario_malformed_token_usage_is_non_authoritative)
    print("record_delivery_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
