#!/usr/bin/env python
"""The record a standalone closure job publishes, and the one way to read it.

A closure review run outside a GER packet had no completion record at all. The
consumer therefore could not tell a review whose job SUCCEEDED from one whose job
failed, and `resolve_post_commit_check` stamped `provider_evidence: imported` on
both - so a result that `check_job_result` rejects with a non-zero process status
was accepted downstream and given provenance it had not earned (Astra MJ-P3-03,
reproduced at the boundary).

This is the host's own record that a review was successfully PRODUCED. It is not
a second verdict: the reviewer's eight-field result is unchanged and still owns
the decision, and `recommendation` is deliberately not copied here. What the
record carries is the evidence a consumer cannot otherwise get - that the process
succeeded, that the transport reported no error, and that the two files on disk
are the ones this run wrote.

**Only a validated COMPLETE result gets a record.** A complete `revise` gets one
and the runner exits 0, because that is a finished review with a negative
conclusion. Incomplete, malformed, a failed process or wrapper, a stale or empty
result, and a failed view write all produce NO final record. Raw diagnostic files
may remain; a reader that finds no record must treat the job as unfinished.

The naming rule is defined once, here: the record is the raw result path with
`.metadata.json` appended. Consumers derive it rather than being told a path, so
relocating a whole job's files keeps working.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import sys
from typing import NamedTuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import review_result  # noqa: E402

__all__ = ["Job", "RecordError", "metadata_path", "view_path", "existing_evidence",
           "build", "publish", "read_job", "sha256", "PROVIDERS"]

PROTOCOL = "json-v1"
PROVIDERS = ("codex", "claude-host", "claude-docker")
_HEX = frozenset("0123456789abcdef")


class RecordError(Exception):
    """A refusal with a machine-readable reason, matching review_result's shape."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _reject(code: str, message: str) -> None:
    raise RecordError(code, message)


def metadata_path(result: pathlib.Path) -> pathlib.Path:
    """THE naming rule. Derived, never supplied by the record itself."""
    return result.with_name(result.name + ".metadata.json")


def view_path(result: pathlib.Path) -> pathlib.Path:
    """The labelled human view beside a JOB.result.json, i.e. JOB.report.md."""
    name = result.name
    for suffix in (".result.json", ".json"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return result.with_name(name + ".report.md")


def existing_evidence(result: pathlib.Path) -> list[pathlib.Path]:
    """Which of this job's three files are already on disk.

    Astra MJ-P3-03-C: a clone reservation protects the working DIRECTORY, not the
    previous run's evidence. Both producers ask this one question instead of each
    spelling the three paths out, because that rule had two homes with two
    different behaviours - the Claude launcher refused, the shell moved the files
    aside and then overwrote the record - and the shell's version is how C
    survived a round after I reported it fixed.

    The caller decides what to do with a non-empty answer. Every caller so far
    refuses: a finished job's evidence is not scratch space, and a retry is free
    because it only needs a different job name.
    """
    return [p for p in (result, view_path(result), metadata_path(result)) if p.exists()]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex64(value: object, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _HEX:
        _reject("bad_field", f"{field} must be 64 lowercase hex characters")


def _seconds(value: object, field: str) -> float:
    # bool first: it is an int subclass, so `isinstance(True, (int, float))` is
    # true and a truthy default would sail through as a timestamp.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject("bad_field", f"{field} must be a number of Unix seconds, got "
                             f"{type(value).__name__}")
    if not math.isfinite(float(value)):
        _reject("bad_field", f"{field} must be finite")
    return float(value)


def build(*, task_id: str, provider: str, reviewed_artifact_sha256: str,
          result_bytes: bytes, view_bytes: bytes, exit_code: int,
          is_error: bool | None, started_at: float, completed_at: float,
          review_status: str, session_id: str | None = None) -> dict:
    """Assemble a record. The caller has already validated the result."""
    record = {
        "protocol": PROTOCOL,
        "review_status": review_status,
        "task_id": task_id,
        "review_kind": "closure",
        "reviewed_artifact_kind": "contract",
        "reviewed_artifact_sha256": reviewed_artifact_sha256,
        "result_sha256": sha256(result_bytes),
        "output_sha256": sha256(view_bytes),
        "provider": provider,
        "exit_code": exit_code,
        "is_error": is_error,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    if session_id:
        # A real one only. Codex's transport supplies none, and inventing one
        # would be fabricating evidence for a run that did not report it.
        record["session_id"] = session_id
    return record


def publish(result: pathlib.Path, record: dict) -> pathlib.Path:
    """Write the record LAST, as one atomic publication.

    Same pattern as `ger_round.publish_metadata`: a temporary sibling renamed
    into place, so the record is absent or whole. A crash before the rename
    leaves no final record, which is the safe direction - absence means the job
    did not finish, and that is exactly what a reader should conclude.
    """
    final = metadata_path(result)
    # The backstop for any producer that forgets to check first. `os.replace` is
    # atomic, which makes an overwrite invisible rather than partial - so without
    # this, a second run on the same job name silently replaces a completed
    # `revise` with a `commit_contract` and nothing on disk records that it
    # happened (Astra MJ-P3-03-C, reproduced through the shell).
    if final.exists():
        _reject("record_exists",
                f"{final.name} already exists: that job finished and its record is "
                f"evidence, not scratch space. Use a new job name.")
    tmp = final.with_name(f".{final.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, final)
    return final


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            _reject("duplicate_key", f"the record repeats the key {key!r}")
        seen.add(key)
    return dict(pairs)


def check(record: dict, *, result_bytes: bytes, view_bytes: bytes, task_id: str,
          reviewed_artifact_sha256: str) -> None:
    """Is this a READY record, for these exact files and this exact subject?

    Exact types throughout. Astra's wording, and the reason for it: "false,
    missing is_error, missing ready status and a matching raw hash alone do not
    form a ready job record". A truthiness test would accept `exit_code: false`.
    """
    if record.get("protocol") != PROTOCOL:
        _reject("unknown_protocol",
                f"the record declares protocol {record.get('protocol')!r}")
    if record.get("review_status") != "complete":
        _reject("not_ready",
                f"the record's review_status is {record.get('review_status')!r}; "
                f"only a completed review is published")
    if record.get("review_kind") != "closure":
        _reject("bad_field", f"review_kind is {record.get('review_kind')!r}")
    if record.get("reviewed_artifact_kind") != "contract":
        _reject("bad_field",
                f"reviewed_artifact_kind is {record.get('reviewed_artifact_kind')!r}")

    provider = record.get("provider")
    if provider not in PROVIDERS:
        _reject("unknown_provider", f"provider {provider!r} is not one of {list(PROVIDERS)}")

    # `type(x) is int`, not `isinstance` minus bool. Astra MJ-P3-03-E: excluding
    # bool still let 0.0 and -0.0 through, because they equal 0 - and a float
    # exit code is not something any process produces, so its presence means the
    # record was written by something that did not observe one.
    exit_code = record.get("exit_code")
    if type(exit_code) is not int or exit_code != 0:
        _reject("not_ready", f"the record's exit_code is {exit_code!r}, not the "
                             f"integer 0")

    is_error = record.get("is_error", "absent")
    if provider == "codex":
        # Codex's transport supplies no such field, so the record says null
        # rather than inventing a successful one.
        if is_error is not None:
            _reject("bad_field", "a codex record must carry is_error null, because "
                                 "that transport reports no such field")
    else:
        if is_error is not False:
            _reject("not_ready", f"a Claude record must carry is_error exactly "
                                 f"false; it carries {is_error!r}")

    for field in ("reviewed_artifact_sha256", "result_sha256", "output_sha256"):
        _hex64(record.get(field), field)
    started = _seconds(record.get("started_at"), "started_at")
    completed = _seconds(record.get("completed_at"), "completed_at")
    if completed < started:
        _reject("bad_field", "completed_at is before started_at")

    if record.get("task_id") != task_id:
        _reject("subject_mismatch",
                f"the record is about task {record.get('task_id')!r}, the caller "
                f"asked about {task_id!r}")
    if record.get("reviewed_artifact_sha256") != reviewed_artifact_sha256.lower():
        _reject("subject_mismatch",
                "the record is about different contract bytes than the caller selected")

    if record["result_sha256"] != sha256(result_bytes):
        _reject("tampered", "the raw result does not match the hash its record published")
    if record["output_sha256"] != sha256(view_bytes):
        _reject("tampered", "the human view does not match the hash its record published")


class Job(NamedTuple):
    """One validated snapshot of a finished job: everything from a single read.

    Astra MJ-P3-03-D: the post-commit consumer took its verdict from one read of
    the report and then called the reader on a SECOND read, discarding what it
    returned. Swapping the files in between produced a recorded approval of a
    result that validated as `revise`, with a report hash matching neither. The
    facts a caller needs therefore come back together, from the same bytes.
    """

    result: review_result.ReviewResult
    result_sha256: str
    record: dict


def read_job(result: pathlib.Path, *, task_id: str,
             reviewed_artifact_sha256: str) -> Job:
    """THE reader for a generated closure job. Every consumer goes through here.

    Checks readiness, both file hashes and the provider evidence, then validates
    the reviewer's result through `review_result.load` bound to the caller's own
    expectations. Returns the validated result together with the hash of the
    exact bytes it validated; whether a verdict is an approval or a completed
    `revise` stays with the caller.
    """
    ready = metadata_path(result)
    if not ready.is_file():
        _reject("no_record",
                f"{result.name} has no job record beside it ({ready.name}); there "
                f"is no evidence its job finished")
    try:
        record = json.loads(ready.read_text(encoding="utf-8"),
                            object_pairs_hook=_no_duplicate_keys)
    except RecordError:
        raise
    except (OSError, ValueError) as error:
        _reject("unreadable_record", f"{ready.name} could not be read: {error}")
    if not isinstance(record, dict):
        _reject("unreadable_record", f"{ready.name} is not a JSON object")

    view = view_path(result)
    if not view.is_file():
        _reject("no_record", f"the human view {view.name} is missing")

    result_bytes = result.read_bytes()
    check(record, result_bytes=result_bytes, view_bytes=view.read_bytes(),
          task_id=task_id, reviewed_artifact_sha256=reviewed_artifact_sha256)

    validated = review_result.load(
        result_bytes,
        task_id=task_id,
        review_kind="closure",
        reviewed_artifact_kind="contract",
        reviewed_artifact_sha256=reviewed_artifact_sha256)

    # Astra MJ-P3-03-E: the record said complete and nothing checked the result
    # itself, so an incomplete result with matching hashes came back as a ready
    # job. The record is the host's claim; the result is the reviewer's. They
    # must agree, and it is the reviewer's that decides.
    # `check` above has already required the RECORD's review_status to be
    # exactly "complete", so once both have passed there is one value left and
    # they cannot disagree. An equality check between them used to sit here as
    # well; Fable found it unreachable, and a guard that cannot fire is worse
    # than none - it reads as a defence and its mutant survives silently.
    if not validated.is_complete:
        _reject("not_ready",
                f"the record claims a complete review but the result declares "
                f"{validated.review_status!r}")

    return Job(result=validated, result_sha256=sha256(result_bytes), record=record)


def main(argv: list[str] | None = None) -> int:
    """Two questions Bash would otherwise answer for itself, answered here.

    `run_closure_review.sh` used to move stale output aside with `mv` and hash
    nothing; both of those were its own implementations of rules that already
    existed in Python, and both were wrong in ways the Python ones were not.
    Shelling out to this keeps one implementation per rule.
    """
    import argparse

    ap = argparse.ArgumentParser(description="Job-record helpers for shell runners.")
    ap.add_argument("--refuse-existing", metavar="RESULT",
                    help="exit 2 if this job's result, view or record already "
                         "exists, naming what was found")
    ap.add_argument("--sha256", metavar="FILE",
                    help="print the sha256 of a file's exact bytes")
    args = ap.parse_args(argv)

    if not args.refuse_existing and not args.sha256:
        ap.error("nothing to do: pass --refuse-existing or --sha256")

    if args.sha256:
        try:
            print(sha256(pathlib.Path(args.sha256).read_bytes()))
        except OSError as error:
            print(f"cannot read {args.sha256}: {error}", file=sys.stderr)
            return 2

    if args.refuse_existing:
        found = existing_evidence(pathlib.Path(args.refuse_existing))
        if found:
            print(f"this job already has evidence on disk:", file=sys.stderr)
            for path in found:
                print(f"  {path}", file=sys.stderr)
            print("a finished job's evidence is never overwritten; use a new job "
                  "name.", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
