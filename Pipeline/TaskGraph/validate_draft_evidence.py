from __future__ import annotations

"""Deterministic draft-evidence validator for one staged TaskGraph evidence record.

This tool answers exactly one question: if the human commits the currently
staged Git index on top of the committed HEAD (i.e. the "would-be commit"),
does the draft evidence record supplied via --record actually contain the
record and evidence objects it claims to contain?

It is deterministic validation only. No agents, no LLM, no Unity. It never
stages, commits, pushes, merges, or mutates anything -- it only reads the
Git index, HEAD, and (for diagnostics only) the working tree.

NSC-005 postmortem: a delivery record referenced a `.log` file that existed
in the working tree but was silently excluded from `git add` because
`*.log` was gitignored, so the commit the human believed they were making
did not actually contain the referenced evidence. `record_delivery.py`
(a separate tool) solves *generating* correct evidence and prints an exact
`git add -f` staging command; this tool closes the remaining gap by
inspecting the actual staged index -- the would-be commit -- before the
human runs `git commit`, so an omission like that is caught deterministically
instead of relying on the human noticing.

It reuses the existing, unmodified conformance-record schema and Git-object
helpers in conformance_records.py; it does not duplicate or weaken that
schema. TaskGraph's evidence-derived evaluator (current_conformance.py)
remains the sole authority for derived state, and only after evidence is
actually committed.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conformance_records import (
    CANON_PATH,
    EVIDENCE_ROOT,
    TASK_ID_RE,
    ConformanceRecordError,
    GitRepository,
    canonical_text_sha256,
    safe_repository_path,
    semantic_json_sha256,
    validate_record_shape,
)

ROOT = Path(__file__).resolve().parents[2]

_TASK_FROM_RECORD_PATH_RE = re.compile(rf"^{re.escape(EVIDENCE_ROOT)}/({TASK_ID_RE.pattern})/records/")


class DraftEvidenceError(RuntimeError):
    """Raised for a condition that prevents any further validation."""


@dataclass(frozen=True)
class Finding:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class ValidationResult:
    status: str  # "valid" | "invalid"
    task_id: str
    record_path: str
    evidence_references_checked: int
    referenced_artifacts_present: int
    unrelated_staged_paths: tuple[str, ...]
    findings: tuple[Finding, ...]
    suggested_commands: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "task_id": self.task_id,
            "record_path": self.record_path,
            "evidence_references_checked": self.evidence_references_checked,
            "referenced_artifacts_present": self.referenced_artifacts_present,
            "unrelated_staged_paths": list(self.unrelated_staged_paths),
            "findings": [finding.to_dict() for finding in self.findings],
            "suggested_commands": list(self.suggested_commands),
        }


# --------------------------------------------------------------------------
# Git index helpers. conformance_records.GitRepository is reused for HEAD/
# commit-object operations; these operate on the INDEX specifically, which
# GitRepository intentionally has no notion of.
# --------------------------------------------------------------------------


def _run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise DraftEvidenceError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def staged_status(root: Path, head: str) -> dict[str, str]:
    """Return {repo_path: status_char} for every path that differs between HEAD and the index.

    Status is one of A (added), M (modified), D (deleted), T (type changed).
    Rename/copy detection is explicitly disabled so each side of a rename is
    reported as its own plain add/delete, matching what `git commit` would
    actually record as two separate blob-path facts.
    """
    output = _run_git(root, "diff", "--cached", "--name-status", "--no-renames", "-z", head)
    tokens = [token for token in output.decode("utf-8", "replace").split("\0") if token]
    status: dict[str, str] = {}
    iterator = iter(tokens)
    for code in iterator:
        path = next(iterator)
        status[path] = code[0]
    return status


def index_blob_sha(root: Path, path: str) -> str | None:
    """Return the staged (stage-0) blob SHA for path, or None if it has no index entry."""
    result = subprocess.run(
        ["git", "ls-files", "-s", "--", path], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise DraftEvidenceError(f"git ls-files -s -- {path} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    lines = [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line]
    if not lines:
        return None
    entries: list[tuple[int, str]] = []
    for line in lines:
        meta, _, _entry_path = line.partition("\t")
        mode_sha_stage = meta.split()
        if len(mode_sha_stage) != 3:
            raise DraftEvidenceError(f"Unexpected `git ls-files -s` output for {path!r}: {line!r}")
        _mode, sha, stage = mode_sha_stage
        entries.append((int(stage), sha))
    if len(entries) != 1 or entries[0][0] != 0:
        raise DraftEvidenceError(
            f"{path!r} has an unmerged/conflicted index entry; resolve conflicts before validating draft evidence."
        )
    return entries[0][1]


def read_index_bytes(root: Path, path: str) -> bytes:
    return _run_git(root, "show", f":{path}")


def commit_exists(root: Path, sha: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def git_object_type(root: Path, sha: str) -> str:
    """Return the actual Git object type for sha via cat-file -t (plumbing, index-independent).

    GitRepository.blob() (conformance_records.py) only verifies that
    `rev-parse <commit>:<path>` produced a syntactically valid 40-character SHA;
    a tree/directory path resolves to such a SHA too. This distinguishes them.
    """
    result = subprocess.run(
        ["git", "cat-file", "-t", sha], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise DraftEvidenceError(f"git cat-file -t {sha} failed: {detail}")
    return result.stdout.decode().strip()


def is_ignored(root: Path, path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", path], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _task_id_from_record_path(record_path: str) -> str:
    match = _TASK_FROM_RECORD_PATH_RE.match(record_path)
    return match.group(1) if match else ""


# --------------------------------------------------------------------------
# Core validation.
# --------------------------------------------------------------------------


def _fatal(record_path: str, findings: list[Finding]) -> ValidationResult:
    return ValidationResult(
        status="invalid",
        task_id=_task_id_from_record_path(record_path),
        record_path=record_path,
        evidence_references_checked=0,
        referenced_artifacts_present=0,
        unrelated_staged_paths=(),
        findings=tuple(findings),
        suggested_commands=(),
    )


def validate_draft_evidence(record_path_arg: str, root: Path = ROOT) -> ValidationResult:
    try:
        return _validate_draft_evidence(record_path_arg, root)
    except ConformanceRecordError as exc:
        raise DraftEvidenceError(str(exc)) from exc


def _validate_draft_evidence(record_path_arg: str, root: Path) -> ValidationResult:
    record_path = safe_repository_path(record_path_arg, "--record")
    findings: list[Finding] = []
    suggested_commands: list[str] = []

    repo = GitRepository(root)
    try:
        head = repo.head()
    except ConformanceRecordError as exc:
        raise DraftEvidenceError(f"{root} is not a usable Git repository at a committed HEAD: {exc}") from exc

    staged = staged_status(root, head)
    exists_at_head = repo.exists(head, record_path)
    status = staged.get(record_path)

    if status is None:
        working_tree_exists = (root / record_path).is_file()
        if exists_at_head:
            detail = "a record already exists at this path in HEAD and there is no staged change here; nothing new would be committed at this path."
        elif working_tree_exists:
            detail = "the record file exists in the working tree but has not been staged; run git add for it."
        else:
            detail = "no record exists at this path in the index, at HEAD, or in the working tree."
        findings.append(Finding("record_not_staged", f"{record_path}: {detail}"))
        return _fatal(record_path, findings)

    if exists_at_head:
        findings.append(Finding(
            "record_already_committed",
            f"{record_path}: a record already exists at this path in HEAD. Draft evidence records must be "
            "new, immutable files; this validator refuses to treat a modification or replacement of a "
            "committed record as new evidence.",
        ))
        return _fatal(record_path, findings)

    history = repo.path_history(head, record_path)
    if history:
        findings.append(Finding(
            "record_path_previously_used",
            f"{record_path}: this path does not exist at HEAD but has {len(history)} historical commit(s) in its "
            "Git history (it was previously created and later deleted). Immutable evidence record paths cannot "
            "be deleted and recreated: TaskGraph's load_committed_records() rejects any immutable record whose "
            "path history has more than one creation/modification event, so committing this draft would produce "
            "a record that is immutable-history-invalid. Use a new, never-before-used record path.",
        ))
        return _fatal(record_path, findings)

    # status is now necessarily "A": present in the index, absent from HEAD.
    try:
        raw = read_index_bytes(root, record_path)
    except DraftEvidenceError as exc:
        findings.append(Finding("record_unreadable", str(exc)))
        return _fatal(record_path, findings)
    try:
        record = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        findings.append(Finding("record_malformed_json", f"{record_path}: staged bytes are not valid JSON: {exc}"))
        return _fatal(record_path, findings)
    try:
        validate_record_shape(record, record_path)
    except ConformanceRecordError as exc:
        findings.append(Finding("record_shape_invalid", str(exc)))
        return _fatal(record_path, findings)

    task_id = record["task_id"]
    record_type = record["record_type"]

    if record_type != "delivery":
        findings.append(Finding(
            "unsupported_record_type",
            f"{record_path}: record_type {record_type!r} is not supported by this draft validator. This command "
            "currently validates new delivery closeout records only; it does not validate the revalidation basis "
            "graph (basis record existence, ancestry, cycles) that baseline/revalidation records require, so it "
            "must not report VALID for them.",
        ))
        return _fatal(record_path, findings)

    task_evidence_root = f"{EVIDENCE_ROOT}/{task_id}"
    artifact_prefix = f"{task_evidence_root}/artifacts/"

    # ---- Unrelated staged paths -------------------------------------------------
    unrelated = sorted(path for path in staged if not path.startswith(f"{task_evidence_root}/"))
    for path in unrelated:
        findings.append(Finding(
            "unrelated_staged_path",
            f"{path}: staged but outside {task_evidence_root}/; evidence closeout must not sweep unrelated "
            "work into this commit.",
        ))

    # ---- Immutability: no staged modification/deletion of already-committed evidence -----
    for path, code in staged.items():
        if path == record_path:
            continue
        if not path.startswith(f"{task_evidence_root}/"):
            continue  # already reported above as unrelated
        if code in {"M", "D", "T"}:
            findings.append(Finding(
                "evidence_immutability_violation",
                f"{path}: staged change {code!r} would modify, delete, or replace already committed "
                "evidence; committed evidence records and artifacts are immutable.",
            ))

    # ---- No other new staged records in this task's records/ directory --------------
    # TaskGraph's load_committed_records() enumerates and validates every committed file
    # under records_prefix, not just record_path. This validator only approves the one
    # record supplied via --record, so any other newly staged file here would be
    # committed -- and TaskGraph would derive from it -- without ever having been checked.
    records_prefix = f"{task_evidence_root}/records/"
    for path, code in staged.items():
        if path == record_path or code != "A":
            continue
        if not path.startswith(records_prefix):
            continue
        findings.append(Finding(
            "extra_staged_record",
            f"{path}: a new file is staged under {records_prefix} but this validator was only asked to "
            f"approve {record_path} via --record. TaskGraph's load_committed_records() loads and validates "
            "every file in this directory after commit, so this extra record would also be committed and "
            "derived from without ever having been checked by this validator.",
        ))

    # ---- validated_state ---------------------------------------------------------
    state = record["validated_state"]
    validated_commit = state["commit"]
    validated_tree = state["tree"]
    if not commit_exists(root, validated_commit):
        findings.append(Finding(
            "validated_commit_unresolvable",
            f"validated_state.commit {validated_commit} does not resolve to a commit.",
        ))
    else:
        actual_tree = repo.tree(validated_commit)
        if actual_tree != validated_tree:
            findings.append(Finding(
                "validated_tree_mismatch",
                f"validated_state.tree {validated_tree} does not match the actual tree {actual_tree} of "
                f"commit {validated_commit}.",
            ))
        if not (validated_commit == head or repo.is_ancestor(validated_commit, head)):
            findings.append(Finding(
                "validated_commit_not_ancestor",
                f"validated_state.commit {validated_commit} is neither HEAD ({head}) nor an ancestor of HEAD.",
            ))

        contract = record["task_contract"]
        contract_path = contract["path"]
        if not repo.exists(validated_commit, contract_path):
            findings.append(Finding(
                "recorded_contract_missing",
                f"{contract_path} does not exist at validated commit {validated_commit}.",
            ))
        else:
            contract_raw = repo.read(validated_commit, contract_path)
            try:
                contract_json = json.loads(contract_raw.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                findings.append(Finding(
                    "recorded_contract_unparseable", f"{contract_path} at {validated_commit}: {exc}",
                ))
                contract_json = None
            if contract_json is not None:
                if semantic_json_sha256(contract_raw) != contract["sha256"]:
                    findings.append(Finding(
                        "recorded_contract_hash_mismatch",
                        f"{contract_path} at {validated_commit}: semantic hash does not match the record.",
                    ))
                if contract_json.get("contract_revision") != contract["revision"] or contract_json.get("id") != task_id:
                    findings.append(Finding(
                        "recorded_contract_identity_mismatch",
                        f"{contract_path} at {validated_commit}: contract_revision/id does not match the record.",
                    ))

        canon = record["canon"]
        canon_path = canon["path"]
        if not repo.exists(validated_commit, canon_path):
            findings.append(Finding(
                "recorded_canon_missing", f"{canon_path} does not exist at validated commit {validated_commit}.",
            ))
        else:
            canon_raw = repo.read(validated_commit, canon_path)
            if canonical_text_sha256(canon_raw) != canon["sha256"]:
                findings.append(Finding(
                    "recorded_canon_hash_mismatch",
                    f"{canon_path} at {validated_commit}: hash does not match the record.",
                ))

        for surface in record["conformance_surfaces"]:
            s_path = surface["path"]
            if not repo.exists(validated_commit, s_path):
                findings.append(Finding(
                    "surface_missing_at_validated_commit",
                    f"{s_path}: does not exist at validated commit {validated_commit}.",
                ))
                continue
            validated_sha = repo.blob(validated_commit, s_path)
            validated_type = git_object_type(root, validated_sha)
            if validated_type != "blob":
                findings.append(Finding(
                    "surface_not_a_blob_at_validated_commit",
                    f"{s_path}: resolves to a Git {validated_type!r} at validated commit {validated_commit}, not "
                    "a blob; a directory/tree path cannot be a conformance surface.",
                ))
                continue
            if validated_sha != surface["blob_sha"]:
                findings.append(Finding(
                    "surface_blob_mismatch_at_validated_commit",
                    f"{s_path}: blob at validated commit {validated_commit} does not match the record.",
                ))
                continue
            if not repo.exists(head, s_path):
                findings.append(Finding("surface_missing_at_head", f"{s_path}: no longer exists at HEAD."))
                continue
            head_sha = repo.blob(head, s_path)
            head_type = git_object_type(root, head_sha)
            if head_type != "blob":
                findings.append(Finding(
                    "surface_not_a_blob_at_head",
                    f"{s_path}: resolves to a Git {head_type!r} at HEAD, not a blob; a directory/tree path cannot "
                    "be a conformance surface.",
                ))
                continue
            if head_sha != surface["blob_sha"]:
                findings.append(Finding(
                    "surface_changed_at_head",
                    f"{s_path}: blob at HEAD no longer matches the record; evidence is stale for current HEAD.",
                ))

    # ---- Current HEAD task contract must still be the one this record validated -------
    head_task_path = f"Tasks/{task_id}.yaml"
    head_task_json: dict[str, Any] | None = None
    if not repo.exists(head, head_task_path):
        findings.append(Finding("current_contract_missing", f"No committed task contract at HEAD: {head_task_path}."))
    else:
        head_task_raw = repo.read(head, head_task_path)
        try:
            head_task_json = json.loads(head_task_raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            findings.append(Finding("current_contract_unparseable", f"{head_task_path} at HEAD: {exc}"))
        else:
            contract = record["task_contract"]
            current_hash = semantic_json_sha256(head_task_raw)
            if (
                contract["path"] != head_task_path
                or contract["revision"] != head_task_json.get("contract_revision")
                or contract["sha256"] != current_hash
            ):
                findings.append(Finding(
                    "contract_changed_since_validation",
                    f"Current HEAD task contract for {task_id} differs from the one this record validated; "
                    "this evidence would require replan, not a delivery commit.",
                ))

    # ---- Current HEAD canon must still be the one this record validated ---------------
    if not repo.exists(head, CANON_PATH):
        findings.append(Finding("current_canon_missing", f"No committed canon at HEAD: {CANON_PATH}."))
    else:
        head_canon_raw = repo.read(head, CANON_PATH)
        head_canon_hash = canonical_text_sha256(head_canon_raw)
        canon = record["canon"]
        if canon["path"] != CANON_PATH or canon["sha256"] != head_canon_hash:
            findings.append(Finding(
                "canon_changed_since_validation",
                "Current HEAD canon differs from the one this record validated; evidence is stale.",
            ))

    # ---- Completion-gate ID set must exactly match the current task contract ----------
    if head_task_json is not None:
        gates = head_task_json.get("completion_gates")
        current_gate_ids: list[str] | None = None
        if not isinstance(gates, list) or not gates:
            findings.append(Finding(
                "current_contract_gates_invalid", f"{head_task_path}: completion_gates must be a non-empty list.",
            ))
        else:
            candidate_ids = [gate.get("gate_id") if isinstance(gate, dict) else None for gate in gates]
            if any(not isinstance(item, str) or not item for item in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
                findings.append(Finding(
                    "current_contract_gates_invalid",
                    f"{head_task_path}: has invalid or duplicate completion gate IDs.",
                ))
            else:
                current_gate_ids = candidate_ids  # type: ignore[assignment]
        if current_gate_ids is not None:
            record_gate_ids = [gate["gate_id"] for gate in record["gate_results"]]
            if set(record_gate_ids) != set(current_gate_ids):
                findings.append(Finding(
                    "completion_gate_set_mismatch",
                    f"Record gate IDs {sorted(record_gate_ids)} do not exactly match the current task "
                    f"contract's completion-gate set {sorted(current_gate_ids)}.",
                ))

    # ---- Human approval sufficiency ------------------------------------------------
    approval = record["human_approval"]
    if approval["required"]:
        if approval["decision"] != "approved" or not approval["approved_by"].strip():
            findings.append(Finding(
                "human_approval_insufficient",
                "human_approval.required is true but decision is not 'approved' with a non-blank approved_by.",
            ))
    else:
        if approval["decision"] != "not_required":
            findings.append(Finding(
                "human_approval_contradictory",
                "human_approval.required is false but decision is not 'not_required'.",
            ))

    # ---- Delivery-specific checks ----------------------------------------------------
    if record_type == "delivery":
        delivery = record["delivery"]
        base_commit = delivery["base_commit"]
        candidate_commit = delivery["candidate_commit"]
        if not commit_exists(root, base_commit):
            findings.append(Finding(
                "base_commit_unresolvable", f"delivery.base_commit {base_commit} does not resolve to a commit.",
            ))
        elif not repo.is_ancestor(base_commit, validated_commit):
            findings.append(Finding(
                "base_commit_not_ancestor",
                f"delivery.base_commit {base_commit} is not an ancestor of validated_state.commit {validated_commit}.",
            ))
        if not commit_exists(root, candidate_commit):
            findings.append(Finding(
                "candidate_commit_unresolvable",
                f"delivery.candidate_commit {candidate_commit} does not resolve to a commit.",
            ))
        elif not (candidate_commit == validated_commit or repo.is_ancestor(candidate_commit, validated_commit)):
            findings.append(Finding(
                "candidate_commit_not_ancestor",
                f"delivery.candidate_commit {candidate_commit} is neither validated_state.commit nor an "
                f"ancestor of it ({validated_commit}).",
            ))
        # integrated_commit/integrated_tree agreement with validated_state is already
        # enforced by validate_record_shape() above; not re-checked here.

    # ---- Gate evidence artifacts resolved against the would-be commit -----------------
    evidence_references_checked = 0
    referenced_present = 0
    for gate in record["gate_results"]:
        for evidence in gate["evidence"]:
            evidence_references_checked += 1
            e_path = evidence["path"]
            e_sha = evidence["blob_sha"]

            if not e_path.startswith(artifact_prefix):
                findings.append(Finding(
                    "artifact_location_invalid", f"{e_path}: gate evidence must be under {artifact_prefix}.",
                ))
                continue

            resolved_sha: str | None
            source: str
            if staged.get(e_path) == "D":
                findings.append(Finding(
                    "artifact_missing_from_would_be_commit",
                    f"{e_path}\nThis path is staged for deletion. Even though it is still committed at HEAD, the "
                    "would-be commit (HEAD plus the index) would not contain it.",
                ))
                continue

            staged_sha = index_blob_sha(root, e_path)
            if staged_sha is not None:
                resolved_sha, source = staged_sha, "staged"
            elif repo.exists(head, e_path):
                resolved_sha, source = repo.blob(head, e_path), "HEAD"
            else:
                working_tree_exists = (root / e_path).is_file()
                if working_tree_exists:
                    ignore_note = " It is ignored by .gitignore." if is_ignored(root, e_path) else ""
                    findings.append(Finding(
                        "artifact_missing_from_would_be_commit",
                        f"{e_path}\nThe file exists in the working tree but is neither staged nor already "
                        f"committed.{ignore_note}",
                    ))
                    suggested_commands.append(f"git add -f -- {_powershell_quote(e_path)}")
                else:
                    findings.append(Finding(
                        "artifact_missing_from_would_be_commit",
                        f"{e_path}\nThe file does not exist in the index, at HEAD, or in the working tree; "
                        "this evidence reference is genuinely missing.",
                    ))
                continue

            if resolved_sha != e_sha:
                findings.append(Finding(
                    "artifact_blob_mismatch",
                    f"{e_path}: {source} blob {resolved_sha} does not match the record's blob_sha {e_sha}.",
                ))
                continue

            referenced_present += 1

    status_str = "valid" if not findings else "invalid"
    if status_str == "valid":
        suggested_commands = [
            "git diff --cached --check",
            "git diff --cached --stat",
            f'git commit -m "Record {task_id} delivery evidence"',
            f"python Pipeline/TaskGraph/taskcontrol.py state {task_id} --json",
        ]

    return ValidationResult(
        status=status_str,
        task_id=task_id,
        record_path=record_path,
        evidence_references_checked=evidence_references_checked,
        referenced_artifacts_present=referenced_present,
        unrelated_staged_paths=tuple(unrelated),
        findings=tuple(findings),
        suggested_commands=tuple(suggested_commands),
    )


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------


def print_human_report(result: ValidationResult) -> None:
    if result.status == "valid":
        print("DRAFT EVIDENCE: VALID")
        print()
        print(f"Task: {result.task_id}")
        print(f"Record: {result.record_path}")
        print("Staged record: yes")
        print(f"Evidence references checked: {result.evidence_references_checked}")
        print(f"Referenced artifacts present in would-be commit: {result.referenced_artifacts_present}")
        print(f"Unrelated staged paths: {len(result.unrelated_staged_paths)}")
        print()
        print("CHECK:")
        print("git diff --cached --check")
        print("git diff --cached --stat")
        print()
        print("COMMIT:")
        print(f'git commit -m "Record {result.task_id} delivery evidence"')
        print()
        print("VERIFY AFTER COMMIT:")
        print(f"python Pipeline/TaskGraph/taskcontrol.py state {result.task_id} --json")
        print()
        print("TaskGraph remains authoritative for conformance after commit.")
        return

    print("DRAFT EVIDENCE: INVALID")
    print()
    print(f"Task: {result.task_id or '(unknown)'}")
    print(f"Record: {result.record_path}")
    print()

    missing = [f for f in result.findings if f.code == "artifact_missing_from_would_be_commit"]
    if missing:
        print("MISSING FROM WOULD-BE COMMIT:")
        for finding in missing:
            print(finding.message)
            print()

    other = [f for f in result.findings if f.code != "artifact_missing_from_would_be_commit"]
    if other:
        print("FINDINGS:")
        for finding in other:
            print(f"- [{finding.code}] {finding.message}")
        print()

    if result.unrelated_staged_paths:
        print("UNRELATED STAGED PATHS:")
        for path in result.unrelated_staged_paths:
            print(f"- {path}")
        print()

    if result.suggested_commands:
        print("FIX:")
        for command in result.suggested_commands:
            print(command)
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic draft-evidence validator for TaskGraph.")
    parser.add_argument("--record", required=True, help="Repository-relative POSIX-style path to the staged draft evidence record JSON.")
    parser.add_argument("--root", default=None, help="Repository root (defaults to this checkout's root).")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON summary instead of the human report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else ROOT
    try:
        result = validate_draft_evidence(args.record, root)
    except DraftEvidenceError as exc:
        print(f"validate_draft_evidence: FAIL\n{exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print_human_report(result)
    return 0 if result.status == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
