"""Apply an audited GER task-contract revision to canonical main (dry run by default).

Usage:
    python apply_contract.py --packet <packet-dir> [--override-json <fields.json>] [--commit]
        [--policy-filters-file <json>] [--drop-policy] [--journal <path>]

Preconditions (fail closed):
- 04-claude-reaudit exists without FAILED.json and recommends commit_contract or
  commit_contract_then_decompose (the recommendation word must appear in its final section).
- Or, when 06-claude-recheck exists: 04 recommends blocked_not_design or a committable verdict, the GER
  owner applied only the re-audit's quoted replacements in 05-owner-patch (hash-bound), and the fresh
  06 re-check that reviewed that exact patch recommends commit_contract or commit_contract_then_decompose.
  The patched contract is then committed, and --override-json is refused.
- Or, when 08-claude-recheck exists: 07-owner-decision-revision (hash-bound to rounds 03 and 04) holds the
  GER owner's revised contract applying recorded design decisions and the re-audit's required changes, and
  the fresh 08 re-check that reviewed that exact revision recommends a committable verdict. The revised
  contract is committed, and --override-json is refused.
- Tasks/<ID>.yaml at HEAD and in the working tree still matches the packet's task hash.
- The round-03 "Final proposed task contract" JSON keeps id, parent, schema_version and
  reconciliation_key, and increments contract_revision by exactly one.

Effects:
- Rewrites only Tasks/<ID>.yaml: existing key order is preserved, changed fields take the audited
  values, `--override-json` applies the re-auditor's quoted minor edits, and provenance gains a
  task_design_ger record (run id, source commit, round output hashes, recommendation).
- Runs Pipeline/TaskGraph/taskcontrol.py validate; restores the original bytes on failure.
- Pipeline/TaskReviewAgent/authoritative_validation_policy.json: an existing entry for the task is rebound
  to the new committed contract hash in the same commit, same rule as contract_commit.py.
  --policy-filters-file sets or creates the entry; --drop-policy removes it for a revision with no Unity
  gate; without an entry and without either flag the policy is untouched.
- With --commit: stages exactly those paths and commits with the Task Design GER .invalid identity. The
  write is bracketed by MAIN-WRITE START/END journal markers (nsc-main-orchestrator-guide.md section 5).
  --journal overrides the journal path; without it, the live graph-lead journal is used only when the repo
  is the canonical checkout, so a test or any other clone gets its own journal file inside its git dir
  instead (never the live one).
Never pushes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

# ger_round owns the round layout, the decision bindings and the one reader;
# review_result owns the protocol. Both are reachable in the tracked and the
# deployed layout alike.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import ger_round  # noqa: E402
import review_result  # noqa: E402

# The shared standalone-closure-job record boundary, used by both launchers
# and by the post-commit consumer below.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "jobs"))
import closure_record  # noqa: E402

import main_write

REPO = pathlib.Path(r"C:\NSC\NSC\NoSafeCircle")
IDENTITY = ["-c", "user.name=No Safe Circle Task Design GER",
            "-c", "user.email=task-design-ger@nosafecircle.invalid"]
ROUNDS = ["01-codex-generate", "02-claude-evaluate", "03-codex-refine", "04-claude-reaudit"]
COMMITTABLE = ("commit_contract_then_decompose", "commit_contract")
INVARIANT_FIELDS = ("id", "parent", "schema_version", "reconciliation_key")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reconcile_resource_groups(source_groups: list[dict], tasks: list[dict]) -> list[dict]:
    """Mirror of Pipeline/TaskGraph/graph_delta.py:217 `_update_resource_groups` (changes only).

    Existing groups keep their member order, drop non-claimants and append new claimants in task
    order; a newly shared resource (more than one claimant) gets a created group.
    """
    owners: dict[str, list[dict]] = {}
    for task in tasks:
        for resource in task["exclusive_resources"]:
            owners.setdefault(resource, []).append(task)
    changes: list[dict] = []
    existing: set[str] = set()
    for source in source_groups:
        resource = source["resource_key"]
        existing.add(resource)
        owner_by_id = {task["id"]: task for task in owners.get(resource, [])}
        ordered = [task_id for task_id in source["work_ids"] if task_id in owner_by_id]
        ordered.extend(task["id"] for task in owners.get(resource, []) if task["id"] not in ordered)
        after = {"resource_key": resource, "work_ids": ordered,
                 "reconciliation_keys": [owner_by_id[task_id]["reconciliation_key"] for task_id in ordered]}
        if (source["work_ids"], source["reconciliation_keys"]) != (after["work_ids"], after["reconciliation_keys"]):
            changes.append({"change_type": "updated", "resource_key": resource, "after": after})
    for resource in sorted(set(owners) - existing):
        if len(owners[resource]) <= 1:
            continue
        changes.append({"change_type": "created", "resource_key": resource, "after": {
            "resource_key": resource, "work_ids": [task["id"] for task in owners[resource]],
            "reconciliation_keys": [task["reconciliation_key"] for task in owners[resource]]}})
    return changes


def serialize(data: dict, crlf: bool) -> bytes:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def same_content(data: bytes, want: str) -> bool:
    lf = data.replace(b"\r\n", b"\n")
    return want in (sha256(data), sha256(lf), sha256(lf.replace(b"\n", b"\r\n")))


def contract_blob_sha256(data: dict) -> str:
    """sha256 of the *committed* (LF, core.autocrlf-normalized) Tasks/<ID>.yaml blob for `data`.

    Pipeline/TaskReviewAgent/authoritative_validation_policy.json binds a task's entry to this exact
    hash (committed_tasks.load_committed_task hashes `git show <rev>:<path>`, i.e. the stored blob, which
    core.autocrlf keeps as LF regardless of the worktree's line endings). Never hash the worktree file
    directly when the tool's own crlf choice might differ from what git will actually store.
    """
    return sha256(serialize(data, False))


def validate_policy_filters(policy_filters: dict | None) -> None:
    if policy_filters is not None and (not isinstance(policy_filters, dict) or not policy_filters or any(
            platform not in ("EditMode", "PlayMode") or not isinstance(value, str) or not value.strip()
            for platform, value in policy_filters.items())):
        raise SystemExit("--policy-filters-file must map EditMode/PlayMode to non-empty filter strings")


def plan_policy_rebind(policy_data: dict, policy_crlf: bool, task_id: str, blob_sha: str,
                       policy_filters: dict | None, drop_policy: bool) -> tuple[bytes | None, str | None]:
    """Mirror of runbook_contract_commit.py's validation-policy rebind (same key order and formatting).

    Mutates `policy_data["tasks"]` in place (the caller re-serializes with `serialize`, matching
    `policy_crlf` to the existing file). Returns `(policy_bytes, message)`; `policy_bytes` is None when
    the task has no existing entry and no `--policy-filters-file` was given (policy left untouched).
    `blob_sha` must come from `contract_blob_sha256`, not a worktree hash.
    """
    policy_entry = policy_data["tasks"].get(task_id)
    if drop_policy:
        if policy_filters is not None or policy_entry is None:
            raise SystemExit("--drop-policy needs an existing entry and no --policy-filters-file")
        del policy_data["tasks"][task_id]
        return (serialize(policy_data, policy_crlf),
                f"validation policy entry removed for {task_id} (was {policy_entry['test_filters']})")
    if policy_entry is None and policy_filters is None:
        return None, None
    entry = dict(policy_entry or {"authority": "committed_task_specific_authoritative_validation_policy"})
    rebound = {"task_contract_sha256": blob_sha}
    if policy_filters is not None:
        rebound["required_test_platforms"] = list(policy_filters)
        rebound["test_filters"] = dict(policy_filters)
    ordered = {"task_contract_sha256": None, "required_test_platforms": None, "test_filters": None}
    ordered.update(entry)
    ordered.update(rebound)
    policy_data["tasks"][task_id] = ordered
    message = (f"validation policy {'rebound' if policy_entry else 'created'} for {task_id}: "
              f"{(policy_entry or {}).get('task_contract_sha256', '-')[:16]} -> {blob_sha[:16]}; "
              f"filters {ordered['test_filters']}")
    return serialize(policy_data, policy_crlf), message


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = main_write.run_process(["git", "-C", str(REPO), *args], capture_output=True, env=env,
                            mutation_capable=any(a in ("add", "commit", "reset") for a in args),
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}")
    return result


def json_object_end(text: str, start: int) -> int:
    """Index of the closing brace of the JSON object whose opening brace is at start (string-aware)."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise SystemExit("unbalanced JSON object in RESOURCE_GROUPS.yaml")


def append_created_groups(original: bytes, expected: dict, changes: list[dict], crlf: bool) -> bytes:
    """Append created resource groups without reformatting other bytes of a non-canonical file."""
    newline = "\r\n" if crlf else "\n"
    text = original.decode("utf-8")
    for change in [c for c in changes if c["change_type"] == "updated"]:
        # Rewrite only that group's object; every other byte, including other groups' formatting, is unchanged.
        after = change["after"]
        needle = '"resource_key": ' + json.dumps(after["resource_key"], ensure_ascii=False)
        if text.count(needle) != 1:
            raise SystemExit(f"could not find exactly one RESOURCE_GROUPS.yaml group for {after['resource_key']}")
        start = text.rfind("{", 0, text.index(needle))
        end = json_object_end(text, start)
        entry = {"reconciliation_keys": after["reconciliation_keys"], "resource_key": after["resource_key"],
                 "work_ids": after["work_ids"]}
        block = newline.join("    " + line for line in json.dumps(entry, indent=2, ensure_ascii=False).split("\n"))
        text = text[:start] + block[4:] + text[end + 1:]
    changes = [c for c in changes if c["change_type"] == "created"]
    if not changes:
        updated = text.encode("utf-8")
        if json.loads(updated) != expected:
            raise SystemExit("in-place RESOURCE_GROUPS.yaml edit did not reproduce the expected groups; refusing")
        return updated
    anchor = f"{newline}  ],{newline}  \"schema_version\""
    if text.count(anchor) != 1:
        raise SystemExit("could not find exactly one end of the resource_groups array in RESOURCE_GROUPS.yaml")
    blocks = []
    for change in changes:
        after = change["after"]
        entry = {"reconciliation_keys": after["reconciliation_keys"], "resource_key": after["resource_key"],
                 "work_ids": after["work_ids"]}
        blocks.append(newline.join("    " + line for line in json.dumps(entry, indent=2, ensure_ascii=False).split("\n")))
    index = text.index(anchor)
    updated = (text[:index] + "," + newline + ("," + newline).join(blocks) + text[index:]).encode("utf-8")
    if json.loads(updated) != expected:
        raise SystemExit("append-only RESOURCE_GROUPS.yaml edit did not reproduce the expected groups; refusing")
    return updated


def final_recommendation(text: str) -> str | None:
    """LEGACY. The pre-protocol grep, kept for packets written before the cutover.

    The implementation moved to ger_round.legacy_round_recommendation, because
    this function and ger_node's were two near-identical copies of one rule - the
    shape that has produced five findings in this family. The name stays so old
    callers and tests keep working.

    New packets do not come through here. round_decision below reads the declared
    verdict, and only a LegacyPacket falls back to this.
    """
    return ger_round.legacy_round_recommendation(text)


def read_imported_review(raw: bytes, *, task_id: str, review_kind: str,
                         artifact_kind: str, reviewed_sha256: str, legacy: bool,
                         legacy_reader, refuse,
                         legacy_requires_identity: bool = True) -> tuple[str, str, object | None]:
    """A review handed over by a person, validated once for every caller.

    Three places take a review the host did not run: ger_decision_revision's
    round-08 recheck, apply_followup_revision's primary --report, and
    resolve_post_commit_check. Each had its own version of "the report names the
    first 16 hex characters somewhere in its prose, then grep it for a verdict",
    and writing the second one was already a copy. This is the one.

    Returns (verdict, protocol, validated result or None). `refuse(message)` must
    not return.

    `legacy` is the CALLER's declaration, never inferred - with one exception
    that only ever refuses: a JSON document read with --legacy sails through both
    old checks by accident, because its reviewed_artifact_sha256 field contains
    the 16-hex prefix and the grep finds the verdict word inside
    `"recommendation": "..."`. A mislabelled result would then have its verdict
    read by a grep, which is the cross-format confusion the protocol removes. The
    forbidden direction - retrying a failed JSON parse as Markdown - stays
    impossible.
    """
    if legacy:
        text = raw.decode("utf-8", errors="replace")
        # Structural, not a parse. Astra MJ-P2-06 reproduced three holes in the
        # parse-based version: a BOM-prefixed result, a valid object followed by
        # trailing text, and anything JSON-shaped but malformed all failed
        # json.loads and fell through to the grep, which then read a verdict out
        # of `"recommendation": "..."`.
        if review_result.looks_like_result(text):
            refuse("a JSON-shaped document was given with the legacy flag; a "
                   "new-format result must be read as one, not grepped, and a "
                   "malformed one is refused rather than retried as Markdown")
        # Only where the old format actually demanded it. The round-08 and
        # followup paths required the reviewer to name the artifact; the
        # post-commit check never did, and imposing it here retroactively would
        # refuse genuinely historical reports - which is the one thing the legacy
        # path exists to avoid. The JSON path binds properly for all three.
        if legacy_requires_identity and reviewed_sha256[:16] not in text:
            refuse("the report does not name the reviewed artifact (first 16 hex "
                   "characters of its sha256)")
        verdict = legacy_reader(text)
        if verdict is None:
            refuse("the report has no final recommendation")
        return verdict, "legacy-markdown", None

    try:
        result = review_result.load(
            raw, task_id=task_id, review_kind=review_kind,
            reviewed_artifact_kind=artifact_kind,
            reviewed_artifact_sha256=reviewed_sha256)
    except review_result.ReviewResultError as error:
        refuse(f"the reviewer result is not valid ({error.code}): {error.message}")
    if not result.is_complete:
        refuse("the reviewer declared the review incomplete; there is no verdict "
               "to record")
    return result.recommendation, "json-v1", result


def review_override(packet: pathlib.Path, proposed: dict, overrides: dict,
                    human_exception: str | None) -> dict | None:
    """What --override-json would change after round 04, and whether that is allowed.

    Astra MJ-P2-07. The owner-patch and decision-revision paths already refuse
    overrides outright; the direct round-04 path did not, so arbitrary keys could
    be applied to the proposal AFTER the reviewer approved it, while provenance
    still recorded that approval as though it covered the result.

    Under the JSON protocol the approval is bound to the exact proposed bytes,
    which makes editing them afterwards a misrepresentation rather than a
    judgement call. A no-op override changes nothing and still passes; anything
    substantive needs a fresh re-check, or a person saying in writing that they
    are overriding the reviewer - which is then recorded beside the keys it
    changed, so no reader can mistake the committed bytes for the reviewed ones.

    Historical (non-json-v1) rounds are unaffected: those reviews were never
    bound to anything, so there is no binding for an override to contradict.
    Returns the provenance record, or None when there is nothing to record.
    """
    # Astra MJ-P2-07, second half: `proposed.get(key) != value` classified three
    # real changes as no-ops. `.get` returns None for an absent key, so adding a
    # key whose value is null looked unchanged; and Python's `==` makes
    # `True == 1` and `1 == True` true, so changing 1 to true - including nested
    # inside a dict - looked unchanged too. Each produced a changed contract with
    # no provenance record of the override.
    #
    # Presence is tested separately from value, and values are compared by their
    # canonical JSON text, which distinguishes 1 from true and orders nested keys.
    changed = []
    for key, value in overrides.items():
        if key not in proposed:
            changed.append(key)
        elif json.dumps(proposed[key], sort_keys=True) != json.dumps(value, sort_keys=True):
            changed.append(key)
    changed.sort()
    if not changed:
        return None
    if ger_round.decision_protocol(packet, "04-claude-reaudit") != "json-v1":
        return None
    if not human_exception:
        raise SystemExit(
            "--override-json changes " + ", ".join(changed) + " after a round-04 "
            "review that was bound to the exact proposal. Route the edit through "
            "an owner patch and a fresh re-check, or, if a person is deliberately "
            "overriding the reviewer, say so with --override-human-exception; the "
            "record must not present changed content as what the reviewer approved")
    return {"keys": changed, "human_exception": human_exception}


def round_decision(packet: pathlib.Path, round_name: str, task_id: str,
                   allow_legacy: bool = False) -> str | None:
    """The verdict of a decision round: declared for v2 packets, grepped for old ones.

    Refuses rather than guesses. A v2 packet whose RESULT.json does not validate
    has NO verdict and must not fall through to the legacy grep - that would make
    every guarantee the protocol buys available to bypass by emitting something
    the loader rejects. The caller turns None into its own refusal.
    """
    try:
        return ger_round.read_decision(packet, round_name, task_id,
                                       allow_legacy=allow_legacy).recommendation
    except ger_round.LegacyPacket:
        output = packet / round_name / "OUTPUT.md"
        if not output.is_file():
            return None
        return final_recommendation(output.read_text(encoding="utf-8"))
    except (ValueError, review_result.ReviewResultError) as error:
        print(f"{round_name} carries no readable decision: {error}", file=sys.stderr)
        return None


POST_COMMIT_VERDICTS = ("commit_contract_then_decompose", "commit_contract", "revise")

_POST_COMMIT_LEADING_MARKUP = re.compile(r"^[ \t]*(?:[-*>][ \t]*)*")
_POST_COMMIT_LINE = re.compile(
    r"(?i)^final recommendation[ \t*`]*:[ \t*`]*("
    + "|".join(POST_COMMIT_VERDICTS) + r")[ \t*`.]*$")


def parse_post_commit_verdict(text: str) -> str | None:
    """Parse a post-commit Codex contract-check report's own last 'Final recommendation:' line.

    This is the check_g15 (nsc-ger-orchestrator-guide.md, "The contract check") vocabulary -
    commit_contract | commit_contract_then_decompose | revise - which is not the round-recommendation
    vocabulary `final_recommendation` above parses. Case-insensitive; tolerates surrounding markdown
    such as '**Final recommendation:** revise', a leading '- ', '* ' or '>', and a trailing period.

    A qualifying line names exactly one verdict word and nothing else (only whitespace and closing
    markdown/backticks may follow it) - so the unfilled prompt template's own
    'Final recommendation: commit_contract | commit_contract_then_decompose | revise' line, and any
    other line naming more than one candidate word, never qualifies: a line containing '|' is always
    skipped, and a word that doesn't run to the end of the line (e.g. 'commit_contract, but revise
    later') doesn't match. Among qualifying lines, the last one wins. Returns None (never raises) when
    no line qualifies, so the caller can turn that into its own usage error.
    """
    # Astra MJ-P2-06: this is the THIRD legacy reader, connected after MJ-P2-01
    # guarded the other two, and it accepted a derived `revise` view as
    # `commit_contract` through resolve_post_commit_check(legacy=True). Same rule,
    # third location - so the test now lives in review_result and
    # jobs/tests/test_legacy_readers.py asserts every reader on that list refuses.
    if review_result.is_derived_view(text):
        return None
    found = None
    for line in text.splitlines():
        if "|" in line:
            continue
        stripped = _POST_COMMIT_LEADING_MARKUP.sub("", line, count=1)
        match = _POST_COMMIT_LINE.match(stripped)
        if match:
            found = match.group(1).lower()
    return found


def resolve_post_commit_check(report_arg: pathlib.Path, commit_arg: str, task_id: str, error,
                              legacy: bool = False,
                              import_source: str | None = None) -> dict:
    """Validate --post-commit-check-report/--post-commit-check-commit and return the followup record.

    `error(message)` must not return (e.g. an ArgumentParser's bound `.error`); every refusal below
    goes through it, so on a refusal nothing is read further and nothing is written.

    The commit is now resolved BEFORE the verdict is read, because the verdict's
    binding needs it: a post-commit check reviews the exact Git blob
    `Tasks/<task>.yaml` at the checked commit, and that is what the result must
    declare. Reading the verdict first, as this did, meant the report's subject
    was never checked against the commit it was filed against.

    `legacy=True` selects the pre-cutover Markdown grep, and is the explicitly
    labelled legacy path the handoff requires. It is a caller's declaration, not
    something inferred from the bytes: a v2 result that fails to validate must
    never be retried through the old reader, and sniffing the format is how that
    rule gets quietly lost.
    """
    report_path = report_arg.resolve()
    if not report_path.is_file():
        error(f"--post-commit-check-report {report_path} does not exist")
    report_bytes = report_path.read_bytes()

    resolved = git("rev-parse", "--verify", f"{commit_arg}^{{commit}}", check=False)
    if resolved.returncode != 0:
        error(f"--post-commit-check-commit {commit_arg!r} does not resolve to a commit in {REPO}")
    checked_commit = resolved.stdout.decode().strip()
    if git("merge-base", "--is-ancestor", checked_commit, "HEAD", check=False).returncode != 0:
        error(f"--post-commit-check-commit {checked_commit} is not an ancestor of HEAD")
    touched = git("diff-tree", "--no-commit-id", "--name-only", "-r", checked_commit).stdout.decode().splitlines()
    if f"Tasks/{task_id}.yaml" not in touched:
        error(f"--post-commit-check-commit {checked_commit} did not change Tasks/{task_id}.yaml")

    record = {"report_path": str(report_path), "checked_commit": checked_commit}

    blob = git("show", f"{checked_commit}:Tasks/{task_id}.yaml", check=False)
    if blob.returncode != 0:
        error(f"cannot read Tasks/{task_id}.yaml at {checked_commit}")
    contract_sha = sha256(blob.stdout)

    # Astra MJ-P3-03-D: the dispatch happens BEFORE anything is read for a
    # verdict. The first version read the report through the import reader, then
    # called the job reader on a SECOND read and discarded what it returned -
    # so swapping the files in between produced a recorded approval of a result
    # that validated as `revise`, with a report hash matching neither. Whichever
    # branch runs, the verdict, the subject hash and the report hash all come
    # from the one read that branch performed.
    if import_source:
        # Hand-carried. The caller names who carried it, and `legacy` selects the
        # format. Both are explicit; neither is inferred.
        verdict, protocol, result = read_imported_review(
            report_bytes,
            task_id=task_id,
            review_kind="closure",
            artifact_kind="contract",
            reviewed_sha256=contract_sha,
            legacy=legacy,
            legacy_reader=parse_post_commit_verdict,
            legacy_requires_identity=False,
            refuse=lambda message: error(
                f"--post-commit-check-report {report_path}: {message}"))
        record.update({"verdict": verdict, "protocol": protocol,
                       "report_sha256": sha256(report_bytes),
                       "provider_evidence": "imported",
                       "imported_from": import_source})
        if result is not None:
            record["reviewed_artifact_sha256"] = result.reviewed_artifact_sha256
        return record

    if legacy:
        # A legacy report cannot be a generated job: nothing produces that format
        # any more, so it is necessarily hand-carried and needs the import
        # declaration too. Astra's rule - "a caller selecting a legacy imported
        # review must select both relevant options explicitly".
        error(f"--post-commit-check-report {report_path} was read as a legacy "
              f"report, which no current job produces, so it can only be "
              f"hand-carried. Name who carried it with --post-commit-check-import "
              f"as well; the two selections are separate on purpose.")

    # GENERATED: one read through the shared job reader, which checks readiness,
    # both file hashes, the provider evidence with exact types, and the reviewer's
    # own binding to the Git blob this caller selected. Every fact recorded below
    # comes back from that single load.
    try:
        job = closure_record.read_job(report_path, task_id=task_id,
                                      reviewed_artifact_sha256=contract_sha)
    except (closure_record.RecordError, review_result.ReviewResultError) as failure:
        # BOTH types. read_job checks the record and then calls
        # review_result.load, which raises its own error class - so catching only
        # RecordError let a result that fails the reviewer's binding raise out of
        # this function instead of refusing. That is the third time in this work
        # that a narrow except missed a second exception type from the same call;
        # the shape to look for is a helper that delegates to another module.
        code = getattr(failure, "code", "invalid")
        error(f"--post-commit-check-report {report_path} is not a finished job "
              f"({code}): {failure}. If this review was handed over by a person "
              f"rather than generated here, say so with --post-commit-check-import "
              f"naming who carried it; a missing or broken job record never "
              f"becomes an import by itself.")
    record.update({
        "verdict": job.result.recommendation,
        "protocol": "json-v1",
        "report_sha256": job.result_sha256,
        "reviewed_artifact_sha256": job.result.reviewed_artifact_sha256,
        "provider_evidence": "generated",
        "provider": job.record["provider"],
        "job_record": str(closure_record.metadata_path(report_path)),
    })
    return record


def final_contract(text: str) -> dict:
    lower = text.lower()
    start = lower.find("final proposed task contract")
    if start < 0:
        raise SystemExit("round 03 output has no 'Final proposed task contract' section")
    match = re.search(r"```json\s*(.*?)```", text[start:], flags=re.S)
    if not match:
        raise SystemExit("round 03 final contract section has no ```json block")
    return json.loads(match.group(1))


def verify_owner_patch_and_recheck(packet: pathlib.Path, hashes: dict, reaudit_recommendation: str | None,
                                   task_id: str, allow_legacy: bool = False) -> dict:
    """An owner patch applies the re-audit's quoted replacements verbatim; a fresh re-check must approve it."""
    if reaudit_recommendation not in COMMITTABLE + ("blocked_not_design",):
        raise SystemExit(f"re-audit recommendation is {reaudit_recommendation!r}; an owner patch cannot resolve it")
    for name in ("05-owner-patch", "06-claude-recheck"):
        directory = packet / name
        if (directory / "FAILED.json").exists() or not (directory / "OUTPUT.md").is_file() \
                or not (directory / "METADATA.json").is_file():
            raise SystemExit(f"round {name} is missing, incomplete or failed")
        hashes[name] = sha256((directory / "OUTPUT.md").read_bytes())
    patch_meta = json.loads((packet / "05-owner-patch" / "METADATA.json").read_text(encoding="utf-8"))
    patched = (packet / "05-owner-patch" / "PATCHED_CONTRACT.json").read_bytes()
    if sha256(patched) != patch_meta.get("patched_contract_sha256"):
        raise SystemExit("PATCHED_CONTRACT.json does not match the owner patch metadata")
    if hashes["05-owner-patch"] != patch_meta.get("output_sha256"):
        raise SystemExit("05-owner-patch/OUTPUT.md does not match the owner patch metadata")
    inputs = patch_meta.get("input_sha256", {})
    if inputs.get("03-codex-refine/OUTPUT.md") != hashes["03-codex-refine"] or \
            inputs.get("04-claude-reaudit/OUTPUT.md") != hashes["04-claude-reaudit"]:
        raise SystemExit("the owner patch was built from different round-03 or round-04 outputs")
    recheck_meta = json.loads((packet / "06-claude-recheck" / "METADATA.json").read_text(encoding="utf-8"))
    if recheck_meta.get("input_sha256", {}).get("05-owner-patch/OUTPUT.md") != hashes["05-owner-patch"]:
        raise SystemExit("the 06 re-check did not review this owner patch")
    recommendation = round_decision(packet, "06-claude-recheck", task_id, allow_legacy=allow_legacy)
    if recommendation not in COMMITTABLE:
        raise SystemExit(f"re-check recommendation is {recommendation!r}; not committing")
    return {"recheck_recommendation": recommendation, "owner_patch_contract_sha256": sha256(patched)}


def verify_decision_revision_only(packet: pathlib.Path, hashes: dict) -> dict:
    """Integrity checks for a 07 decision revision committed without a re-check (Vincent-approved skip only)."""
    directory = packet / "07-owner-decision-revision"
    if (directory / "FAILED.json").exists() or not (directory / "OUTPUT.md").is_file() \
            or not (directory / "METADATA.json").is_file():
        raise SystemExit("round 07-owner-decision-revision is missing, incomplete or failed")
    hashes["07-owner-decision-revision"] = sha256((directory / "OUTPUT.md").read_bytes())
    build_meta = json.loads((directory / "METADATA.json").read_text(encoding="utf-8"))
    revised = (directory / "REVISED_CONTRACT.json").read_bytes()
    if sha256(revised) != build_meta.get("revised_contract_sha256"):
        raise SystemExit("REVISED_CONTRACT.json does not match the decision revision metadata")
    if hashes["07-owner-decision-revision"] != build_meta.get("output_sha256"):
        raise SystemExit("07-owner-decision-revision/OUTPUT.md does not match its metadata")
    inputs = build_meta.get("input_sha256", {})
    if inputs.get("03-codex-refine/OUTPUT.md") != hashes["03-codex-refine"] or \
            inputs.get("04-claude-reaudit/OUTPUT.md") != hashes["04-claude-reaudit"]:
        raise SystemExit("the decision revision was built from different round-03 or round-04 outputs")
    return {"decision_revision_contract_sha256": sha256(revised)}


def verify_decision_revision_and_recheck(packet: pathlib.Path, hashes: dict, task_id: str,
                                         allow_legacy: bool = False) -> dict:
    """A decision revision applies recorded decisions and the re-audit's required changes; a fresh re-check must approve it."""
    for name in ("07-owner-decision-revision", "08-claude-recheck"):
        directory = packet / name
        if (directory / "FAILED.json").exists() or not (directory / "OUTPUT.md").is_file() \
                or not (directory / "METADATA.json").is_file():
            raise SystemExit(f"round {name} is missing, incomplete or failed")
        hashes[name] = sha256((directory / "OUTPUT.md").read_bytes())
    build_meta = json.loads((packet / "07-owner-decision-revision" / "METADATA.json").read_text(encoding="utf-8"))
    revised = (packet / "07-owner-decision-revision" / "REVISED_CONTRACT.json").read_bytes()
    if sha256(revised) != build_meta.get("revised_contract_sha256"):
        raise SystemExit("REVISED_CONTRACT.json does not match the decision revision metadata")
    if hashes["07-owner-decision-revision"] != build_meta.get("output_sha256"):
        raise SystemExit("07-owner-decision-revision/OUTPUT.md does not match its metadata")
    inputs = build_meta.get("input_sha256", {})
    if inputs.get("03-codex-refine/OUTPUT.md") != hashes["03-codex-refine"] or \
            inputs.get("04-claude-reaudit/OUTPUT.md") != hashes["04-claude-reaudit"]:
        raise SystemExit("the decision revision was built from different round-03 or round-04 outputs")
    recheck_meta = json.loads((packet / "08-claude-recheck" / "METADATA.json").read_text(encoding="utf-8"))
    reviewed = recheck_meta.get("input_sha256", {})
    if reviewed.get("07-owner-decision-revision/OUTPUT.md") != hashes["07-owner-decision-revision"] or \
            reviewed.get("07-owner-decision-revision/REVISED_CONTRACT.json") != sha256(revised):
        raise SystemExit("the 08 re-check did not review this decision revision")
    if hashes["08-claude-recheck"] != recheck_meta.get("output_sha256"):
        raise SystemExit("08-claude-recheck/OUTPUT.md does not match its metadata")
    recommendation = round_decision(packet, "08-claude-recheck", task_id, allow_legacy=allow_legacy)
    if recommendation not in COMMITTABLE:
        raise SystemExit(f"re-check recommendation is {recommendation!r}; not committing")
    return {"recheck_recommendation": recommendation, "decision_revision_contract_sha256": sha256(revised)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packet", required=True, type=pathlib.Path)
    parser.add_argument("--override-json", type=pathlib.Path)
    parser.add_argument("--legacy-rounds", action="store_true",
                        help="this packet predates the JSON protocol, so its decision rounds "
                             "are read with the legacy Markdown parser. A declaration by the "
                             "caller: a JSON round that fails to validate is refused, never "
                             "retried through the old reader.")
    parser.add_argument("--override-human-exception", metavar="WHY",
                        help="a person is deliberately overriding the round-04 reviewer. "
                             "Required with --override-json after a JSON-protocol review, and "
                             "recorded in provenance beside the keys it changed.")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--skip-recheck", metavar="REASON",
                        help="Commit a 07 decision revision without an 08 re-check; only when Vincent approved it")
    parser.add_argument("--policy-filters-file", type=pathlib.Path,
                        help="JSON object mapping EditMode/PlayMode to a Unity test filter; sets or creates "
                        "the task's authoritative_validation_policy.json entry")
    parser.add_argument("--drop-policy", action="store_true",
                        help="remove the task's validation policy entry (the revision has no Unity test gate)")
    parser.add_argument("--role", default=None,
                        help="the role writing to main, e.g. 'GER Agent'. Falls back to "
                             "NSC_ROLE. Required: the one-writer guard compares open "
                             "writes against it, and a default is what made that guard "
                             "compare every role against itself until 2026-09-22.")
    parser.add_argument("--journal", type=pathlib.Path, default=None,
                        help="MAIN-WRITE START/END journal path (default: the live graph-lead journal for "
                        "the canonical checkout, otherwise a journal file inside this repo's own git dir)")
    args = parser.parse_args()
    if args.journal is None:
        args.journal = main_write.default_journal(REPO)
        if args.journal != main_write.JOURNAL:
            print(f"[PLAN] MAIN-WRITE journal (not the live one): {args.journal}")
    packet = args.packet.resolve()
    identity = json.loads((packet / "SOURCE_IDENTITY.json").read_text(encoding="utf-8"))
    task_id = identity["task_id"]
    rel = f"Tasks/{task_id}.yaml"

    hashes = {}
    for name in ROUNDS:
        directory = packet / name
        if (directory / "FAILED.json").exists() or not (directory / "OUTPUT.md").is_file():
            raise SystemExit(f"round {name} is missing or failed")
        hashes[name] = sha256((directory / "OUTPUT.md").read_bytes())
    reaudit_recommendation = round_decision(packet, "04-claude-reaudit", task_id, allow_legacy=args.legacy_rounds)
    recheck = None
    decision = None
    if (packet / "08-claude-recheck").exists():
        decision = verify_decision_revision_and_recheck(packet, hashes, task_id,
                                                       allow_legacy=args.legacy_rounds)
        recommendation = decision["recheck_recommendation"]
    elif (packet / "07-owner-decision-revision").exists() and not (packet / "06-claude-recheck").exists():
        if not args.skip_recheck:
            raise SystemExit("07-owner-decision-revision has no 08 re-check; pass --skip-recheck REASON only if Vincent approved skipping it")
        decision = verify_decision_revision_only(packet, hashes)
        decision["recheck_skipped"] = args.skip_recheck
        recommendation = "re-check skipped"
    elif (packet / "06-claude-recheck").exists():
        recheck = verify_owner_patch_and_recheck(packet, hashes, reaudit_recommendation, task_id,
                                                 allow_legacy=args.legacy_rounds)
        recommendation = recheck["recheck_recommendation"]
    else:
        recommendation = reaudit_recommendation
        if recommendation not in COMMITTABLE:
            raise SystemExit(f"re-audit recommendation is {recommendation!r}; not committing")

    head = git("rev-parse", "HEAD").stdout.decode().strip()
    head_blob = git("show", f"HEAD:{rel}").stdout
    path = REPO / rel
    original = path.read_bytes()
    if not same_content(head_blob, identity["task_sha256"]) or not same_content(original, identity["task_sha256"]):
        raise SystemExit(f"{rel} changed since the packet (source {identity['source_head']}); start a new GER cycle")

    current = json.loads(original)
    override_record = None
    if decision is not None:
        if args.override_json:
            raise SystemExit("--override-json is not allowed after a decision revision; route edits through a new revision and re-check")
        proposed = json.loads((packet / "07-owner-decision-revision" / "REVISED_CONTRACT.json").read_bytes())
    elif recheck is not None:
        if args.override_json:
            raise SystemExit("--override-json is not allowed after an owner patch; route edits through a new patch and re-check")
        proposed = json.loads((packet / "05-owner-patch" / "PATCHED_CONTRACT.json").read_bytes())
    else:
        proposed = final_contract((packet / "03-codex-refine" / "OUTPUT.md").read_text(encoding="utf-8"))
        if args.override_json:
            overrides = json.loads(args.override_json.read_text(encoding="utf-8"))
            override_record = review_override(packet, proposed, overrides,
                                              args.override_human_exception)
            proposed.update(overrides)
    for field in INVARIANT_FIELDS:
        if proposed.get(field) != current.get(field):
            raise SystemExit(f"proposed contract changes invariant field {field}: {current.get(field)!r} -> {proposed.get(field)!r}")
    if proposed.get("contract_revision") != current.get("contract_revision", 0) + 1:
        raise SystemExit(f"contract_revision must be {current.get('contract_revision', 0) + 1}, got {proposed.get('contract_revision')}")

    merged = {}
    for key in current:
        if key in proposed:
            merged[key] = proposed[key]
    for key in sorted(set(proposed) - set(current)):
        merged[key] = proposed[key]
    removed = sorted(set(current) - set(proposed))
    provenance = dict(merged.get("provenance") or current.get("provenance") or {})
    record = {"ger_run_id": packet.name, "packet_source_head": identity["source_head"],
              "previous_contract_revision": current.get("contract_revision"),
              "round_output_sha256": hashes, "reaudit_recommendation": reaudit_recommendation}
    if override_record is not None:
        # Named separately from the recommendation so no reader can mistake the
        # committed bytes for the ones the reviewer saw.
        record["override_after_review"] = override_record
    if recheck is not None:
        record.update({"owner_patch_contract_sha256": recheck["owner_patch_contract_sha256"],
                       "recheck_recommendation": recommendation})
    if decision is not None:
        record.update({"owner_decision_revision_contract_sha256": decision["decision_revision_contract_sha256"]})
        if decision.get("recheck_skipped"):
            record["recheck_skipped"] = decision["recheck_skipped"]
        else:
            record["recheck_recommendation"] = recommendation
    provenance["task_design_ger"] = list(provenance.get("task_design_ger") or []) + [record]
    merged["provenance"] = provenance

    changed = sorted(key for key in set(current) | set(merged) if current.get(key) != merged.get(key))
    print(f"[PLAN] {task_id}: revision {current.get('contract_revision')} -> {merged['contract_revision']} at HEAD {head}")
    print(f"[PLAN] changed fields: {changed}; removed fields: {removed}")

    # Shared exclusive resources must keep RESOURCE_GROUPS.yaml in step with task claims. Reuse the
    # canonical graph-delta reconciliation and apply only its changed or created groups.
    groups_rel = "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml"
    groups_path = REPO / groups_rel
    groups_original = groups_path.read_bytes()
    groups_crlf = b"\r\n" in groups_original
    groups_data = json.loads(groups_original)
    groups_canonical = serialize(groups_data, groups_crlf) == groups_original
    all_tasks = []
    for task_file in sorted((REPO / "Tasks").glob("NSC-*.yaml")):
        task = json.loads(task_file.read_bytes())
        all_tasks.append(merged if task.get("id") == task_id else task)
    group_changes = reconcile_resource_groups(groups_data["resource_groups"], all_tasks)
    for change in group_changes:
        after = change["after"]
        entry = {"reconciliation_keys": after["reconciliation_keys"], "resource_key": after["resource_key"],
                 "work_ids": after["work_ids"]}
        if change["change_type"] == "updated":
            index = next(i for i, group in enumerate(groups_data["resource_groups"])
                         if group["resource_key"] == after["resource_key"])
            groups_data["resource_groups"][index] = entry
        else:
            groups_data["resource_groups"].append(entry)
        print(f"[PLAN] resource group {change['change_type']}: {after['resource_key']} -> {after['work_ids']}")
    groups_bytes = None
    if group_changes and groups_canonical:
        groups_bytes = serialize(groups_data, groups_crlf)
        print("[PLAN] RESOURCE_GROUPS.yaml: canonical re-serialization")
    elif group_changes:
        groups_bytes = append_created_groups(groups_original, groups_data, group_changes, groups_crlf)
        print("[PLAN] RESOURCE_GROUPS.yaml has non-canonical formatting elsewhere; editing only the changed groups "
              "in place and appending created groups, every other byte unchanged")

    policy_rel = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
    policy_path = REPO / policy_rel
    policy_original = policy_path.read_bytes()
    policy_head = git("show", f"HEAD:{policy_rel}").stdout
    if policy_head.replace(b"\r\n", b"\n") != policy_original.replace(b"\r\n", b"\n"):
        if args.commit:
            raise SystemExit(f"{policy_rel} differs from HEAD; refusing")
        # G15b round 3: a dry run only previews. Plan from HEAD's copy and say that a commit refuses.
        print(f"[PLAN] WARNING: {policy_rel} differs from HEAD; planning from HEAD's copy. A --commit run refuses.")
        policy_original = policy_head
    policy_data = json.loads(policy_original)
    policy_filters = (json.loads(args.policy_filters_file.read_bytes().decode("utf-8"))
                      if args.policy_filters_file else None)
    validate_policy_filters(policy_filters)
    blob_sha = contract_blob_sha256(merged)
    policy_bytes, policy_message = plan_policy_rebind(
        policy_data, b"\r\n" in policy_original, task_id, blob_sha, policy_filters, args.drop_policy)
    if policy_message:
        print(f"[PLAN] {policy_message}")

    if not args.commit:
        print(json.dumps(merged, indent=2, ensure_ascii=False))
        print("[DRY RUN] no file written")
        return 0

    touched = [rel] + ([groups_rel] if group_changes else []) + ([policy_rel] if policy_bytes else [])
    dirty = git("status", "--porcelain=v1", "--", *touched).stdout.decode().strip()
    if dirty:
        raise SystemExit(f"target paths already have uncommitted changes: {dirty}")
    pre_staged = git("diff", "--cached", "--name-only").stdout.decode().strip()
    if pre_staged:
        raise SystemExit(f"the index already has staged paths; refusing to commit: {pre_staged}")

    if group_changes:
        changed = changed + ["RESOURCE_GROUPS.yaml: " + ", ".join(
            f"{c['change_type']} {c['after']['resource_key']}" for c in group_changes)]
    title = merged.get("title", "")
    if decision is not None and decision.get("recheck_skipped"):
        review = (f"a fresh Claude re-audit ({reaudit_recommendation}). The GER owner then applied the recorded\n"
                  f"design decisions and the re-audit's required changes in a decision revision. The per-room\n"
                  f"re-check was skipped: {decision['recheck_skipped']}.")
    elif decision is not None:
        review = (f"a fresh Claude re-audit ({reaudit_recommendation}). The GER owner then applied the recorded\n"
                  f"design decisions and the re-audit's required changes in a decision revision, and a second\n"
                  f"fresh Claude re-check recommended {recommendation}.")
    elif recheck is None:
        review = f"a fresh Claude re-audit, which recommended\n{recommendation}."
    else:
        review = (f"a fresh Claude re-audit ({reaudit_recommendation}). The GER owner applied only the\n"
                  f"re-audit's quoted replacement text, and a second fresh Claude re-check recommended\n"
                  f"{recommendation}.")
    message = (f"TaskGraph: GER contract revision {merged['contract_revision']} for {task_id}\n\n"
               f"Task Design GER carried {task_id} ({title}) through Codex Generate, independent Claude\n"
               f"Evaluate, one bounded Codex Refine and {review}\n"
               f"Changed fields: {', '.join(changed)}.\n"
               + (("Validation policy entry removed: this revision has no Unity test gate.\n" if args.drop_policy
                   else f"Validation policy rebound to contract sha256 {blob_sha}.\n") if policy_bytes else "")
               + f"GER run {packet.name} at source {identity['source_head']}.\n\n"
               "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n")

    if git("rev-parse", "HEAD").stdout.decode().strip() != head:
        raise SystemExit("HEAD moved since planning; rerun")
    with main_write.transaction(f"{task_id} GER contract revision {merged['contract_revision']}", head, role=args.role, journal=args.journal, repo=REPO, touched=touched,
                                expected_files={rel: original, groups_rel: groups_original,
                                                policy_rel: policy_original}):
        commit = write_and_commit_packet(rel, path, original, merged, b"\r\n" in original, groups_path,
                                         groups_original, groups_bytes, group_changes, policy_path,
                                         policy_original, policy_bytes, blob_sha, touched, packet, message)
        files = git("show", "--name-only", "--format=", "HEAD").stdout.decode().split()
        print(f"[DONE] {task_id} contract commit {commit} (parent {head}; files {files}); not pushed")
    return 0


def write_and_commit_packet(rel, path, original, merged, crlf, groups_path, groups_original, groups_bytes,
                            group_changes, policy_path, policy_original, policy_bytes, blob_sha, touched,
                            packet, message) -> str:
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    def restore() -> None:
        path.write_bytes(original)
        groups_path.write_bytes(groups_original)
        policy_path.write_bytes(policy_original)

    # G15b round 4: one failed write must not leave the earlier ones on disk.
    try:
        path.write_bytes(serialize(merged, crlf))
        if group_changes:
            groups_path.write_bytes(groups_bytes)
        if policy_bytes:
            policy_path.write_bytes(policy_bytes)
    except OSError as error:
        restore()
        raise SystemExit(f"writing {touched} failed; restored: {error}") from error
    validate = main_write.run_process([sys.executable, "-B", "Pipeline/TaskGraph/taskcontrol.py", "validate"], cwd=str(REPO),
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(validate.stdout.strip()[-1200:])
    if validate.returncode != 0 or "PASS" not in validate.stdout:
        restore()
        raise SystemExit(f"taskcontrol validate failed; restored {touched}:\n{validate.stderr.strip()[-1200:]}")
    check = git("diff", "--check", "--", *touched, check=False)
    if check.returncode != 0:
        restore()
        raise SystemExit(f"git diff --check failed; restored {touched}:\n{check.stdout.decode(errors='replace')}")
    # G15b round 3: as in contract_commit.py and apply_followup_revision.py, everything from staging through
    # the commit itself (a hook rejection included) is protected: a failure unstages and restores the
    # contract, RESOURCE_GROUPS.yaml and the validation policy instead of leaving them staged.
    try:
        git("add", "--", *touched)
        staged = sorted(line for line in git("diff", "--cached", "--name-only").stdout.decode().splitlines() if line)
        if staged != sorted(touched):
            raise RuntimeError(f"unexpected staged paths {staged}")
        if policy_bytes and sha256(git("show", f":{rel}").stdout) != blob_sha:
            raise RuntimeError("staged contract blob hash differs from the rebound policy hash")
        message_path = packet / "CONTRACT_COMMIT_MESSAGE.txt"
        message_path.write_text(message, encoding="utf-8")
        git(*IDENTITY, "commit", "-F", str(message_path))
    except main_write.MutationChildUncertain:
        raise
    except (SystemExit, RuntimeError, OSError) as error:
        if git("rev-parse", "HEAD").stdout.decode().strip() != head:
            raise  # preserve a completed commit when a later step reports failure
        # G15b round 4: reset the whole index, not just these paths. Both tools refuse to start with
        # anything staged, and a path git staged under a different spelling (a case variant of an
        # existing folder) would survive a pathspec reset.
        git("reset", "-q")
        restore()
        raise SystemExit(f"commit failed; unstaged and restored {touched}: {error}") from error
    return git("rev-parse", "HEAD").stdout.decode().strip()


if __name__ == "__main__":
    raise SystemExit(main())
