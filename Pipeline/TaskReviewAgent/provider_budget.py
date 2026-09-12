"""Host-owned usage accounting and stable task-provider assignments.

The scheduler and its host workers share this hash-checked, locked ledger.
Provider outputs supply usage, never assignments or quota estimates. Invocation
identity is deduplicated before aggregation; conflicting replays fail closed.
"""
from __future__ import annotations

from contextvars import ContextVar
import datetime as dt
import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .contracts import semantic_sha256, validate_task_id
from .provider_profiles import ProviderTopology

UNAVAILABLE = None
PROVIDER_NAMES = {"claude-code": "claude", "openai-codex": "codex", "claude": "claude", "codex": "codex"}
_WORKER_BUDGET: ContextVar[tuple | None] = ContextVar("provider_budget_worker", default=None)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class ProviderBudgetError(ValueError):
    pass


def _worker_identity(worker_run_id: str, task_id: str, contract_sha256: str) -> None:
    validate_task_id(task_id)
    if type(worker_run_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", worker_run_id) is None:
        raise ProviderBudgetError("worker run identity must be a bounded path-safe identifier")
    if type(contract_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", contract_sha256) is None:
        raise ProviderBudgetError("assignment requires an exact task-contract hash")


class ProviderBudgetLedger:
    def __init__(self, path: Path, *, topology: ProviderTopology, repository: str, run_id: str):
        self.path = Path(path).resolve()
        self.topology = topology
        self.identity = dict(topology=topology.to_dict(), repository=repository, run_id=run_id)

    def _lock(self):
        from .execution_session_pool import _exclusive_file_lock
        return _exclusive_file_lock(self.path.with_suffix(".lock"))

    def _load(self) -> dict:
        if not self.path.exists():
            return dict(schema_version="1.0", identity=self.identity, invocations={}, assignments={},
                        workers={}, next_provider="claude", latest_snapshot=None)
        state = json.loads(self.path.read_text(encoding="utf-8"))
        digest = state.pop("sha256", None)
        if digest != semantic_sha256(state) or state.get("identity") != self.identity:
            raise ProviderBudgetError("provider ledger identity or hash differs from the immutable run")
        if set(state) != {"schema_version", "identity", "invocations", "assignments", "workers", "next_provider", "latest_snapshot"}:
            raise ProviderBudgetError("provider ledger schema differs")
        if state["schema_version"] != "1.0" or state["next_provider"] not in {"claude", "codex"}:
            raise ProviderBudgetError("provider ledger state is invalid")
        return state

    def _save(self, state: dict) -> None:
        from .execution_session_pool import _write_verified
        body = {**state, "sha256": semantic_sha256(state)}
        _write_verified(self.path, (json.dumps(body, sort_keys=True) + "\n").encode())

    def observe(self, *, invocation_id: str, provider: str, role: str, usage: dict | None,
                status: str = "succeeded", evidence: str = "", worker_run_id: str | None = None) -> None:
        provider = PROVIDER_NAMES.get(provider, provider)
        self.topology.require_provider(provider)
        if not invocation_id or len(invocation_id) > 250 or not role:
            raise ProviderBudgetError("usage requires a bounded exact invocation and role identity")
        tokens = {}
        for field in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(field) if isinstance(usage, dict) else None
            if value is not None and (type(value) is not int or value < 0):
                raise ProviderBudgetError("provider reported invalid token usage")
            tokens[field] = value
        value = dict(provider=provider, role=role, usage=tokens, status=status, evidence=evidence,
                     worker_run_id=worker_run_id)
        with self._lock():
            state = self._load()
            if worker_run_id is not None and worker_run_id not in state["workers"]:
                raise ProviderBudgetError("usage does not belong to a registered run worker")
            old = state["invocations"].get(invocation_id)
            if old is not None:
                if {k: v for k, v in old.items() if k != "observed_at"} != value:
                    raise ProviderBudgetError("replayed invocation identity changed its usage or provider")
                return
            state["invocations"][invocation_id] = {**value, "observed_at": _now()}
            self._save(state)

    def _snapshot(self, state: dict, *, active: dict, warm: dict | None, availability: dict | None) -> dict:
        rows = {}
        quotas = dict(self.topology.token_budgets)
        for provider in self.topology.provider_allowlist:
            calls = [v for v in state["invocations"].values() if v["provider"] == provider]
            totals = {}
            for field in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"):
                values = [call["usage"][field] for call in calls]
                # No observations is unavailable, not evidence of no account use.
                totals[field] = sum(values) if values and all(v is not None for v in values) else None
            failures = [dict(invocation_id=key, role=call["role"], status=call["status"], observed_at=call["observed_at"])
                        for key, call in state["invocations"].items() if call["provider"] == provider
                        and call["status"] != "succeeded"
                        and (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(call["observed_at"])).total_seconds() <= 300]
            available = availability.get(provider) if availability is not None else None
            if failures:
                available = False
            if available is not None and type(available) is not bool:
                raise ProviderBudgetError("availability must be host-observed boolean or unavailable")
            total = totals["total_tokens"]
            quota = quotas[provider]
            rows[provider] = dict(**totals, configured_token_budget=quota,
                normalized_utilization=total/quota if total is not None and quota else None,
                active_assignments=active.get(provider, []),
                warm_compatible_sessions=warm.get(provider) if warm is not None else None,
                available=available, recent_failures=failures, invocation_count=len(calls))
        return dict(schema_version="1.0", authority="host_observed_invocation_ledger",
            accounting_scope="this_immutable_autonomous_run", metric=self.topology.balance_metric,
            providers=rows, next_round_robin_provider=state["next_provider"], observed_at=_now())

    def snapshot(self, *, active: dict | None = None, warm: dict | None = None,
                 availability: dict | None = None) -> dict:
        with self._lock():
            state = self._load()
            result = self._snapshot(state, active=active or {}, warm=warm, availability=availability)
            state["latest_snapshot"] = result
            self._save(state)
            return result

    def assign(self, *, task_id: str, contract_sha256: str, recommendation: Any,
               snapshot: dict) -> dict:
        _worker_identity("assignment", task_id, contract_sha256)
        key = task_id + ":" + contract_sha256
        with self._lock():
            state = self._load()
            if snapshot != state["latest_snapshot"]:
                raise ProviderBudgetError("assignment snapshot is not this ledger's current durable observation")
            rows = snapshot["providers"]
            snapshot = self._snapshot(state, active={p:r["active_assignments"] for p,r in rows.items()},
                warm={p:r["warm_compatible_sessions"] for p,r in rows.items()},
                availability={p:r["available"] for p,r in rows.items()})
            state["latest_snapshot"] = snapshot
            available = [p for p in self.topology.provider_allowlist if snapshot["providers"][p]["available"] is not False]
            if key in state["assignments"]:
                saved = state["assignments"][key]
                if saved["provider"] not in available:
                    raise ProviderBudgetError("committed task provider is unavailable; assignment is preserved")
                return saved
            if not available:
                raise ProviderBudgetError("no profile provider is currently available")
            preference = {"openai": "codex", "codex": "codex", "claude": "claude"}.get(recommendation.provider_preference)
            basis = getattr(recommendation, "preference_basis", None)
            reason = "profile_fixed_provider"
            if self.topology.mixed:
                if basis == "capability" and preference in available:
                    provider = preference
                    reason = "architect_capability_advantage"
                else:
                    choices = available
                    pressure = {p: snapshot["providers"][p]["normalized_utilization"] for p in choices}
                    if all(v is not None for v in pressure.values()):
                        minimum = min(pressure.values())
                        choices = [p for p in choices if pressure[p] == minimum]
                        reason = "lower_normalized_budget_pressure"
                    else:
                        reason = "pressure_unavailable"
                    if len(choices) > 1:
                        warmth = {p: snapshot["providers"][p]["warm_compatible_sessions"] for p in choices}
                        if all(type(v) is int and v >= 0 for v in warmth.values()):
                            maximum = max(warmth.values())
                            choices = [p for p in choices if warmth[p] == maximum]
                            reason = "warm_compatible_session" if len(choices) == 1 else reason
                    if len(choices) > 1:
                        provider = state["next_provider"]
                        state["next_provider"] = "codex" if provider == "claude" else "claude"
                        reason = "persisted_round_robin"
                    else:
                        provider = choices[0]
                        if len(available) == 1:
                            reason = "provider_availability"
            else:
                provider = available[0]
            saved = dict(task_id=task_id, task_contract_sha256=contract_sha256, provider=provider,
                supervisor=self.topology.supervisor_for(provider), validator=self.topology.reviewer_for(provider),
                lead_developer=self.topology.reviewer_for(provider), reason=reason,
                architect_preference=recommendation.provider_preference, preference_basis=basis,
                rationale=recommendation.rationale, budget_snapshot_sha256=semantic_sha256(snapshot))
            state["assignments"][key] = saved
            self._save(state)
            return saved

    def worker_profile(self, *, worker_run_id: str, task_id: str, contract_sha256: str,
                       provider: str, role_routes: dict) -> Path:
        from .provider_profiles import validate_crew_routes
        from .execution_session_pool import _write_verified
        _worker_identity(worker_run_id, task_id, contract_sha256)
        validate_crew_routes(self.topology, provider, role_routes)
        with self._lock():
            state = self._load()
            assignment = state["assignments"][task_id+":"+contract_sha256]
            if assignment["provider"] != provider:
                raise ProviderBudgetError("profile differs from committed task assignment")
            if assignment.get("role_routes", role_routes) != role_routes:
                raise ProviderBudgetError("committed task role models changed on retry")
            assignment["role_routes"] = role_routes
            self._save(state)
        self.register_worker(worker_run_id=worker_run_id, task_id=task_id,
                             contract_sha256=contract_sha256, provider=provider)
        value = dict(topology=self.topology.to_dict(), role_routes=role_routes,
            worker_run_id=worker_run_id, task_id=task_id, task_contract_sha256=contract_sha256,
            provider=provider, ledger_path=str(self.path))
        path = self.path.parent / "provider-assignments" / (worker_run_id + ".json")
        body = (json.dumps({**value, "sha256": semantic_sha256(value)}, sort_keys=True)+"\n").encode()
        if path.exists() and path.read_bytes() != body:
            raise ProviderBudgetError("worker profile identity was reused")
        _write_verified(path, body)
        return path

    def register_worker(self, *, worker_run_id: str, task_id: str, contract_sha256: str, provider: str) -> None:
        _worker_identity(worker_run_id, task_id, contract_sha256)
        with self._lock():
            state = self._load()
            assignment = state["assignments"].get(task_id+":"+contract_sha256)
            if assignment is None or assignment["provider"] != provider:
                raise ProviderBudgetError("worker differs from the committed provider assignment")
            value = dict(task_id=task_id, task_contract_sha256=contract_sha256, provider=provider)
            if state["workers"].get(worker_run_id, value) != value:
                raise ProviderBudgetError("worker run identity was reused")
            state["workers"][worker_run_id] = value
            self._save(state)

    def register_decomposition_worker(self, *, worker_run_id: str, task_id: str, contract_sha256: str) -> None:
        provider = "claude" if self.topology.decomposition_strategy == "claude_role_pair" else "codex"
        _worker_identity(worker_run_id, task_id, contract_sha256)
        with self._lock():
            state = self._load()
            value = dict(task_id=task_id, task_contract_sha256=contract_sha256, provider=provider)
            if state["workers"].get(worker_run_id, value) != value:
                raise ProviderBudgetError("decomposition worker identity was reused")
            state["workers"][worker_run_id] = value
            self._save(state)


def bind_worker_budget(path: Path, *, topology: ProviderTopology, worker_run_id: str,
                       task_id: str, contract_sha256: str, provider: str) -> ProviderBudgetLedger:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = raw.get("identity", {})
    ledger = ProviderBudgetLedger(path, topology=topology, repository=identity["repository"], run_id=identity["run_id"])
    with ledger._lock():
        state = ledger._load()
        expected = dict(task_id=task_id, task_contract_sha256=contract_sha256, provider=provider)
        if state["workers"].get(worker_run_id) != expected:
            raise ProviderBudgetError("worker is not registered with the run's provider assignment")
    _WORKER_BUDGET.set((ledger, worker_run_id, topology.supervisor_for(provider)))
    return ledger


def load_worker_profile(path: Path, *, task_id: str, worker_run_id: str, contract_sha256: str,
                        provider: str, model: str, supervisor: str, bind: bool = False) -> dict:
    from .provider_profiles import preflight_topology, validate_crew_routes
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = value.pop("sha256", None)
    if digest != semantic_sha256(value) or set(value) != {"topology", "role_routes", "worker_run_id", "task_id", "task_contract_sha256", "provider", "ledger_path"}:
        raise ProviderBudgetError("worker provider profile fields or hash differ")
    topology = ProviderTopology.from_dict(value["topology"])
    for field, expected in dict(task_id=task_id, worker_run_id=worker_run_id,
            task_contract_sha256=contract_sha256, provider=provider).items():
        if value[field] != expected:
            raise ProviderBudgetError("worker provider profile identity differs")
    validate_crew_routes(topology, provider, value["role_routes"])
    if value["role_routes"]["implementer"]["model"] != model or topology.supervisor_for(provider) != supervisor:
        raise ProviderBudgetError("worker route differs from its host assignment")
    preflight_topology(topology)
    # Re-read the registered assignment, not merely a self-consistent JSON hash.
    ledger = bind_worker_budget(Path(value["ledger_path"]), topology=topology,
        worker_run_id=worker_run_id, task_id=task_id, contract_sha256=contract_sha256, provider=provider)
    with ledger._lock():
        if ledger._load()["assignments"][task_id+":"+contract_sha256]["role_routes"] != value["role_routes"]:
            raise ProviderBudgetError("worker role map differs from the committed run assignment")
    if not bind:
        _WORKER_BUDGET.set(None)
    return value


def observe_supervisor_turn(*, turn: int, usage: dict | None, provider: str, status: str = "succeeded") -> None:
    binding = _WORKER_BUDGET.get()
    if binding is not None:
        ledger, run_id, expected_provider = binding
        if provider != expected_provider:
            raise ProviderBudgetError("supervisor invocation differs from the registered worker provider")
        if provider == "claude" and usage:
            usage = dict(usage)
            if "cached_input_tokens" not in usage and "cache_read_input_tokens" in usage:
                usage["cached_input_tokens"] = usage["cache_read_input_tokens"]
        ledger.observe(invocation_id=f"supervisor:{run_id}:{turn}", provider=provider,
            role="task_supervisor", usage=usage, status=status,
            evidence=f"worker:{run_id}:turn:{turn}", worker_run_id=run_id)


def observe_crew_result(result_path: Path) -> None:
    binding = _WORKER_BUDGET.get()
    if binding is None:
        return
    ledger, worker_run_id, _ = binding
    root = Path(result_path).parent.resolve()
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    # Only this exact host-verified crew result's invocation identities are read.
    for artifact in result["provider_invocation_artifacts"]:
        relative = artifact["path"]
        path = (root/relative).resolve()
        if not path.is_relative_to(root) or path.name != "result.json" or path.parent.parent != root/"agent_runtime":
            raise ProviderBudgetError("crew invocation artifact escaped its verified run")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != artifact["sha256"]:
            raise ProviderBudgetError("crew invocation bytes differ from the verified result")
        invocation = json.loads(payload)
        if invocation["run_id"] != path.parent.name:
            raise ProviderBudgetError("crew invocation identity differs from its artifact")
        if invocation["status"] == "invalid_request" and invocation["provider"] is None and invocation["usage"] is None:
            continue  # Runtime rejected the request before selecting or invoking a provider.
        route = result["role_routes"].get(invocation["role"])
        if (route is None or PROVIDER_NAMES.get(invocation["provider"]) != route["provider"]
                or invocation["model"] != route["model"]):
            raise ProviderBudgetError("crew usage provider/model differs from its host-assigned role")
        ledger.observe(invocation_id=invocation["run_id"], provider=invocation["provider"],
            role=invocation["role"], usage=invocation["usage"], status=invocation["status"],
            evidence=str(path), worker_run_id=worker_run_id)


def bind_decomposition_budget(path: Path, *, task_id: str, run_id: str, contract_sha256: str,
                              provider_order: tuple, permitted: tuple) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    topology = ProviderTopology.from_dict(value["identity"]["topology"])
    from .provider_profiles import preflight_topology
    expected = {"claude_role_pair": ("claude","claude"), "codex_role_pair": ("codex","codex"),
                "cross_provider_round_robin": ("codex","claude")}[topology.decomposition_strategy]
    if provider_order != expected or permitted != topology.provider_allowlist:
        raise ProviderBudgetError("decomposition order differs from run topology")
    preflight_topology(topology)
    bind_worker_budget(path, topology=topology, worker_run_id=run_id,
        task_id=task_id, contract_sha256=contract_sha256, provider=provider_order[0])


def observe_decomposition_result(run_dir: Path) -> None:
    binding = _WORKER_BUDGET.get()
    if binding is None:
        return
    ledger, worker_run_id, _ = binding
    root = run_dir.resolve()
    run = json.loads((root/"decomposition_run_result.json").read_text(encoding="utf-8"))
    if run["run_id"] != worker_run_id:
        raise ProviderBudgetError("decomposition usage belongs to another worker run")
    for number, round_result in enumerate(run["rounds"], 1):
        relative = round_result["agent_runtime_result_path"]
        if relative is None:
            continue  # No invocation artifact exists; no usage is invented.
        path = (root/relative).resolve()
        expected_parent = root/"rounds"/f"{number:02d}"/"agent_runtime"
        if path.name != "result.json" or path.parent.parent != expected_parent or not path.is_relative_to(root):
            raise ProviderBudgetError("decomposition usage artifact escaped its exact round")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["run_id"] != path.parent.name:
            raise ProviderBudgetError("decomposition invocation identity changed")
        if value["status"] == "invalid_request" and value["provider"] is None and value["usage"] is None:
            continue
        expected_provider = PROVIDER_NAMES.get(value["provider"])
        if expected_provider != round_result["requested_provider"] or value["role"] != round_result["role"]:
            raise ProviderBudgetError("decomposition invocation provider or role differs from its exact round")
        ledger.observe(invocation_id=value["run_id"], provider=value["provider"], role=value["role"],
            usage=value["usage"],status=value["status"],evidence=str(path),worker_run_id=worker_run_id)


def compatible_crew_sessions(*, checkout_root: Path, repository: str, topology: ProviderTopology,
                             policy, compose_project: str) -> dict:
    """Read only the existing pool namespace for these stores and resume controls.

    Warmth is advisory; actual checkout revalidates every lease and its lifecycle.
    An absent pool is an observed empty pool, not an estimate of account usage.
    """
    from .provider_profiles import profile_runtime_binding, crew_role_routes
    from .execution_session_pool import _exclusive_file_lock
    from Pipeline.ExecutionCrew.session_pool import SessionPool, SessionCompatibility
    from Pipeline.ExecutionCrew.role_profiles import PROFILE_ROLE_CAPABILITY_CLASSES
    binding = profile_runtime_binding(topology, compose_project)
    root = checkout_root/".task-review-agent"/"session-pools"/hashlib.sha256(repository.encode()).hexdigest()
    root = root/("profile-crew-"+semantic_sha256(binding))
    path = root/"execution-crew.json"
    counts = {p:0 for p in topology.provider_allowlist}
    if not path.exists():
        return counts
    with _exclusive_file_lock(root/"execution-crew.lock"):
        state=json.loads(path.read_text(encoding="utf-8"))
        body={k:v for k,v in state.items() if k != "state_sha256"}
        if state.get("state_sha256") != semantic_sha256(body):
            raise ProviderBudgetError("observed crew pool state hash differs")
        pool=SessionPool.from_dict(state["pool"])
    expected={p:set() for p in topology.provider_allowlist}
    for tier_name in ("fast","standard","deep"):
        tier = policy.for_tier(tier_name)
        if not set(topology.provider_allowlist).issubset(tier.allowed_execution_providers):
            continue
        for primary in topology.provider_allowlist:
            for role,route in crew_role_routes(topology,primary,tier).items():
                expected[route["provider"]].add(SessionCompatibility(
                    "claude-code" if route["provider"]=="claude" else "openai-codex",
                    route["model"],route["reasoning_effort"],role,PROFILE_ROLE_CAPABILITY_CLASSES[role],repository))
    moment=dt.datetime.now(dt.timezone.utc)
    for session in pool.sessions_for("idle"):
        for provider,compatibilities in expected.items():
            if session.compatibility in compatibilities and session.is_reusable_at(moment):
                counts[provider]+=1
    return counts


def read_budget_report(path: Path, *, topology: ProviderTopology, scheduler_id: str) -> dict | None:
    """Read atomic ledger bytes without creating locks or modifying run evidence."""
    if not path.is_file():
        return None
    identity = json.loads(path.read_text(encoding="utf-8"))["identity"]
    if identity["run_id"] != scheduler_id:
        raise ProviderBudgetError("provider budget belongs to another autonomous scheduler")
    ledger = ProviderBudgetLedger(path, topology=topology, repository=identity["repository"], run_id=scheduler_id)
    state = ledger._load()
    latest = state["latest_snapshot"]
    rows = latest["providers"] if latest else {}
    snapshot = ledger._snapshot(state,
        active={p: r["active_assignments"] for p, r in rows.items()},
        warm={p: r["warm_compatible_sessions"] for p, r in rows.items()} if latest else None,
        availability=None)
    return dict(identity=state["identity"], snapshot=snapshot, assignments=state["assignments"],
        invocations=state["invocations"], last_scheduler_observation=latest,
        activity_basis="last scheduler observation; token totals include subsequent worker receipts")
