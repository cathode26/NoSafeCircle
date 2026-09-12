#!/usr/bin/env python3
"""Run one structured goal-supervisor decision through authenticated Claude CLI.

This is the Claude sibling of ``codex_supervisor_turn.py`` and speaks exactly
the same host contract: one JSON request on stdin, one JSON response on stdout.
Every request validator is imported from that module rather than restated, so
the two routes can never drift into different bounds, schema versions, or
failure classifications.

Only the provider differs. It constructs the existing ``ClaudeCodeProvider``
from ``Pipeline/AgentRuntime``; there is no second Claude CLI adapter. The
supervisor keeps the empty capability set, so this turn reads no repository
files and holds no host tool authority: the deterministic host still owns
checkout, Git, Issue, test, commit, readiness, and closeout decisions.

Claude names its own conversation, so a pooled start binds the exact UUID the
host generated (``--session-id``) and a resume passes that same UUID
(``--resume``). Neither accepts a Codex sandbox argument; supplying one here is
refused rather than ignored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    Budgets,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.json_values import thaw_json  # noqa: E402
from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    ProviderSessionBinding,
    ProviderSessionError,
    ProviderSessionLedger,
)
from Pipeline.AgentRuntime.providers.base import ProviderInvocationError  # noqa: E402
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider  # noqa: E402
import Pipeline.TaskReviewAgent.codex_supervisor_turn as _shared_turn  # noqa: E402
from Pipeline.TaskReviewAgent.codex_supervisor_turn import (  # noqa: E402
    SUPERVISOR_ROLE,
    TURN_RESPONSE_SCHEMA_VERSION,
    SupervisorTurnError,
    _emit_failure,
    _object,
    _provider_failure_detail,
    _request,
)


_SESSION_FIELDS = {"mode", "session_id", "resume_sandbox_argument"}

# The shared failure emitter announces which supervisor stopped. Rebinding the
# label keeps one emitter while telling the operator the truth about this route.
_shared_turn.SUPERVISOR_TURN_LABEL = "CLAUDE SUPERVISOR TURN"


def _claude_provider_session(value: Any) -> ProviderSessionBinding:
    """Validate the host's pooled-session binding for the Claude route.

    Claude accepts the conversation identity the host chooses, so BOTH a start
    and a resume carry the exact UUID. That is the one contract difference from
    Codex, which assigns its own thread ID and therefore binds nothing at
    start. A Codex sandbox control is refused outright: it reproduces a policy
    that has no meaning here, and silently ignoring it would let an operator
    believe a verified control was applied.
    """

    session = _object(value, field="provider_session")
    if set(session) != _SESSION_FIELDS:
        raise SupervisorTurnError(
            "provider_session fields mismatch; "
            f"missing={sorted(_SESSION_FIELDS - set(session))}, "
            f"extras={sorted(set(session) - _SESSION_FIELDS)}"
        )
    if session.get("resume_sandbox_argument") is not None:
        raise SupervisorTurnError(
            "the Codex resume sandbox control is not a Claude capability; a "
            "Claude supervisor resumes natively with '--resume <uuid>'"
        )
    mode = session.get("mode")
    session_id = session.get("session_id")
    if mode not in ("start", "resume"):
        raise SupervisorTurnError(
            "provider_session.mode must be exactly 'start' or 'resume'"
        )
    if type(session_id) is not str or not session_id:
        raise SupervisorTurnError(
            "a pooled Claude turn requires the exact session_id the host chose, "
            "because Claude accepts the conversation identity rather than "
            "assigning it"
        )
    try:
        return ProviderSessionBinding("claude-code", SUPERVISOR_ROLE, mode, session_id)
    except ProviderSessionError as exc:
        raise SupervisorTurnError(f"provider_session binding is invalid: {exc}") from exc


def main() -> int:
    ledger: ProviderSessionLedger | None = None
    try:
        # The Claude session rule is supplied here rather than letting the
        # shared validator apply the Codex one, which would reject a Claude
        # start for binding the identity Claude actually requires.
        raw = _request(_claude_provider_session)
        session = raw.get("provider_session")
        invocation = AgentInvocationRequest(
            schema_version=AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
            run_id=raw["run_id"],
            role=SUPERVISOR_ROLE,
            prompt=raw["prompt"],
            context_paths=(),
            allowed_capabilities=(),
            write_boundaries=WriteBoundaries((), ()),
            output_schema=raw["output_schema"],
            model_capability_class="high_reasoning",
            budgets=Budgets(
                turn_limit=raw["provider_turn_limit"],
                timeout_seconds=raw["timeout_seconds"],
                token_limit=None,
            ),
            provider_configuration_key="claude-task-supervisor",
        )
        # ``reasoning_effort`` is required by the shared wire contract and is
        # part of the pooled session's compatibility key, but Claude Code has no
        # reasoning-effort control, so this route deliberately does not forward
        # it. Keeping it in the scope stays conservative -- a conversation
        # started under one routed effort is never reused under another -- but
        # it is not applied to the model, and no evidence here claims it was.
        provider_options: dict[str, Any] = {
            "executable": "claude",
            "repository_root": ROOT,
        }
        if session is not None:
            # A pooled turn is the ephemeral turn plus exactly one difference:
            # the adapter binds the host's conversation and proves the identity
            # it actually used. Every other control -- schema, model, budgets,
            # empty capabilities -- is restated on every turn.
            ledger = ProviderSessionLedger()
            provider_options["session"] = session
            provider_options["session_ledger"] = ledger
        provider = ClaudeCodeProvider(**provider_options)
        response = provider.invoke(invocation, raw["model"])
        result = {
            "schema_version": TURN_RESPONSE_SCHEMA_VERSION,
            "structured_output": thaw_json(response.structured_output),
            "usage": None if response.usage is None else response.usage.to_dict(),
            "provider_session_confirmation": (
                None if ledger is None else ledger.to_dict()
            ),
        }
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    except ProviderInvocationError as exc:
        _emit_failure(type(exc).__name__, _provider_failure_detail(exc), ledger)
        return 2
    except (SupervisorTurnError, ValueError) as exc:
        _emit_failure(type(exc).__name__, str(exc), ledger)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
