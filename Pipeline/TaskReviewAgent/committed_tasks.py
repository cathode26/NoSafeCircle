"""One shared loader for committed task contracts used in coordination decisions.

Resource-conflict checks and Issue-workflow observation must reason about the
real committed ``Tasks/<TASK-ID>.yaml`` contract — never a synthesized
``{"id": ..., "exclusive_resources": []}`` stand-in, which silently disables
exclusive-resource coordination. Every production ``task_loader`` should call
:func:`load_committed_task` so identity, contract bytes/hash, and the real
``exclusive_resources`` list come from Git HEAD.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .contracts import TaskReviewContractError, validate_task_id


class CommittedTaskError(TaskReviewContractError):
    """Raised when a committed task contract cannot be proven at HEAD."""


def load_committed_task(
    root: Path | str,
    task_id: str,
    *,
    expected_sha256: str | None = None,
    commit: str | None = None,
) -> dict[str, Any]:
    """Read ``Tasks/<TASK-ID>.yaml`` from a proven commit and verify identity.

    ``commit`` defaults to ``HEAD``. When supplied it must be one exact,
    lowercase Git object ID; symbolic refs and revision expressions are never
    accepted. Returns the parsed contract plus its exact
    ``task_contract_sha256``. Fails closed when the file is missing, is not
    valid JSON, declares a
    different task ``id``, carries a malformed ``exclusive_resources`` list, or
    (when ``expected_sha256`` is given) does not match the expected bytes.
    """

    task_id = validate_task_id(task_id)
    root = Path(root)
    path = f"Tasks/{task_id}.yaml"
    selected_commit = "HEAD"
    if commit is not None:
        if type(commit) is not str or re.fullmatch(
            r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit
        ) is None:
            raise CommittedTaskError(
                "committed task revision must be an exact lowercase Git object ID"
            )
        selected_commit = commit
    result = subprocess.run(
        ("git", "-C", str(root), "show", f"{selected_commit}:{path}"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0:
        raise CommittedTaskError(
            f"committed task contract is missing at {selected_commit}: {path}"
        )
    return parse_committed_task_bytes(
        task_id, result.stdout, expected_sha256=expected_sha256
    )


def load_committed_tasks(
    root: Path | str,
    task_ids: list[str] | tuple[str, ...],
    *,
    commit: str,
) -> dict[str, dict[str, Any]]:
    """Read many ``Tasks/<TASK-ID>.yaml`` contracts at one exact commit in one process.

    ``git cat-file --batch`` prints each stored blob byte-for-byte as ``git
    show`` does, so every returned ``task_contract_sha256`` equals the one
    :func:`load_committed_task` computes for the same task and commit. Fails
    closed, like the single-object loader, when any requested contract is
    missing, is not a blob, or does not parse.
    """

    if type(commit) is not str or re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit
    ) is None:
        raise CommittedTaskError(
            "committed task revision must be an exact lowercase Git object ID"
        )
    ordered = list(dict.fromkeys(validate_task_id(task_id) for task_id in task_ids))
    if not ordered:
        return {}
    request = "".join(
        f"{commit}:Tasks/{task_id}.yaml\n" for task_id in ordered
    ).encode("ascii")
    result = subprocess.run(
        ("git", "-C", str(Path(root)), "cat-file", "--batch"),
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise CommittedTaskError(
            f"committed task contracts could not be read at {commit}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    data = result.stdout
    position = 0
    contracts: dict[str, dict[str, Any]] = {}
    for task_id in ordered:
        path = f"Tasks/{task_id}.yaml"
        newline = data.find(b"\n", position)
        if newline < 0:
            raise CommittedTaskError(
                f"committed task contract is missing at {commit}: {path}"
            )
        header = data[position:newline].split(b" ")
        position = newline + 1
        if len(header) != 3 or header[1] != b"blob":
            raise CommittedTaskError(
                f"committed task contract is missing at {commit}: {path}"
            )
        size = int(header[2])
        body = data[position:position + size]
        if len(body) != size or data[position + size:position + size + 1] != b"\n":
            raise CommittedTaskError(
                f"committed task contract stream is truncated at {commit}: {path}"
            )
        position += size + 1
        contracts[task_id] = parse_committed_task_bytes(task_id, body)
    return contracts


def parse_committed_task_bytes(
    task_id: str,
    raw_bytes: bytes,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate task bytes supplied by a committed-object reader.

    This parser does not establish Git provenance. Callers must read the bytes
    from their validated commit, as the single-object loader and local batch
    reader do, before using the returned contract for coordination.
    """
    task_id = validate_task_id(task_id)
    path = f"Tasks/{task_id}.yaml"
    try:
        value = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommittedTaskError(
            f"committed task contract is invalid JSON: {path}"
        ) from exc
    if not isinstance(value, dict) or value.get("id") != task_id:
        raise CommittedTaskError(f"committed task identity mismatch: {path}")
    resources = value.get("exclusive_resources")
    if resources is not None and (
        not isinstance(resources, list)
        or any(not isinstance(item, str) or not item.strip() for item in resources)
    ):
        raise CommittedTaskError(
            f"committed task exclusive_resources must be a list of non-empty strings: {path}"
        )
    contract_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 is not None and contract_sha256 != expected_sha256:
        raise CommittedTaskError(
            f"committed task contract hash mismatch for {path}: "
            f"expected {expected_sha256}, found {contract_sha256}"
        )
    return {**value, "task_contract_sha256": contract_sha256}

__all__ = [
    "CommittedTaskError", "load_committed_task", "load_committed_tasks",
    "parse_committed_task_bytes",
]
