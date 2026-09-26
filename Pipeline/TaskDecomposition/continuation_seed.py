"""Read a v2 continuation seed only after replaying its complete retained chain.

No provider calls, publication, or host-record archival happen here. Paths are
confined to the output root and every consumed file is included in the proof.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

from TaskDecomposition.context_builder import DecompositionPreflightError
from TaskDecomposition.review_chain import (
    CandidateDigest, verify_continuation_chain, verify_three_call_chain,
)
from TaskDecomposition.run_diagnosis import confined, parse_json_object

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RESULT = "decomposition_run_result.json"


def verify_continuation_seed(
    output_root: Path, prior: Mapping[str, Any], *, parent_contract: Mapping[str, Any],
    candidate_digest: CandidateDigest,
) -> dict[str, Any]:
    """Return the accepted candidate/sheet, findings, settings and replay proof.

    ``evidence_sha256`` uses output-root-relative paths, including each prior
    run result. ``proof`` is the immediate prior run's verified open end and
    can be passed directly to ``verify_continuation_chain``.
    """

    try:
        return _verify_seed(Path(output_root), prior, parent_contract, candidate_digest)
    except DecompositionPreflightError:
        raise
    except Exception as exc:
        raise DecompositionPreflightError(f"continuation seed evidence refused: {exc}") from exc


def _verify_seed(output_root: Path, prior: Mapping[str, Any], parent_contract: Mapping[str, Any],
                 candidate_digest: CandidateDigest) -> dict[str, Any]:
    # Import lazily: the engine uses this loader during its own preflight.
    from TaskDecomposition.continuation import continuable_problem

    chain: list[tuple[str, dict[str, Any], bytes]] = []
    seen: set[str] = set()
    run_id = prior.get("run_id")
    hashes: dict[str, str] = {}
    while run_id is not None:
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None or run_id in seen:
            raise ValueError(f"continuation chain is malformed at {run_id!r}")
        seen.add(run_id)
        path = confined(output_root, f"{run_id}/{_RESULT}")
        raw = path.read_bytes()
        value = parse_json_object(raw, f"run {run_id}")
        if value.get("run_id") != run_id or (not chain and value != prior):
            raise ValueError(f"run {run_id} does not equal its retained result")
        request = parse_json_object(
            confined(output_root, f"{run_id}/decomposition_request.json").read_bytes(), "prior request")
        problem = continuable_problem(value, request=request)
        if problem:
            raise ValueError(f"cannot continue {run_id}: {problem}")
        if (value.get("task_id") != prior.get("task_id")
                or value.get("provider_order") != prior.get("provider_order")
                or value.get("task_execution_contract_identity") != prior.get("task_execution_contract_identity")
                or value.get("d1a_semantic_parent_identity") != prior.get("d1a_semantic_parent_identity")):
            raise ValueError(f"run {run_id} has another task, provider order or parent contract")
        if ((value.get("designer_bookkeeper") or {}).get("notes_rule")
                != (prior.get("designer_bookkeeper") or {}).get("notes_rule")):
            raise ValueError(f"run {run_id} changed the inherited bookkeeper notes_rule")
        hashes[f"{run_id}/{_RESULT}"] = hashlib.sha256(raw).hexdigest()
        chain.insert(0, (run_id, value, raw))
        continued = value.get("continued_from")
        if continued is not None and not isinstance(continued, Mapping):
            raise ValueError(f"run {run_id} has a malformed continued_from")
        run_id = (continued or {}).get("run_id")
    if not chain:
        raise ValueError("the prior run has no identity")
    providers = tuple(prior.get("provider_order") or [])
    base_id, base, previous_bytes = chain[0]
    if base.get("mode") != "round_robin_d1b2":
        raise ValueError("the continuation chain does not start with a fresh run")
    proof = verify_three_call_chain(
        run_dir=confined(output_root, base_id), run_result=base, providers=providers,
        candidate_digest=candidate_digest, parent_contract=parent_contract, open_end=True)
    if "settings" not in proof or "latest_sheet" not in proof:
        raise ValueError("bookkeeper protocol is unsupported; a fresh run is required")
    hashes.update({f"{base_id}/{key}": value for key, value in proof["evidence_sha256"].items()})
    for run_id, value, raw in chain[1:]:
        proof = verify_continuation_chain(
            run_dir=confined(output_root, run_id), run_result=value, prior=proof,
            prior_run_result_sha256=hashlib.sha256(previous_bytes).hexdigest(), providers=providers,
            candidate_digest=candidate_digest, parent_contract=parent_contract, open_end=True)
        hashes.update({f"{run_id}/{key}": digest for key, digest in proof["evidence_sha256"].items()})
        previous_bytes = raw
    return {
        "candidate": proof["candidate"], "candidate_summary": proof["latest_candidate"],
        "sheet": proof["sheet"], "latest_sheet": proof["latest_sheet"],
        "unresolved_findings": [value for key, value in sorted(proof["unresolved_findings"].items())],
        "finding_history": proof["finding_history"], "settings": proof["settings"],
        "source_heads": {run_id: (value.get("source_identity") or {}).get("head_commit")
                         for run_id, value, _ in chain},
        "proof": proof, "evidence_sha256": hashes,
    }
