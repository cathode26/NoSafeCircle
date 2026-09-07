# Provider profiles and budget routing

`Start-GameTaskAgent.ps1` and `Start-AutonomousGraphRun.ps1` accept
`-ProviderProfile`. Python owns the enum; PowerShell forwards its spelling to
the composition preflight instead of maintaining a second enum. Existing
launches without a profile retain the legacy provider selectors and defaults.

| Profile | Architect | Supervisor/implementer | Validator and Lead Developer | Decomposition |
| --- | --- | --- | --- | --- |
| `all-claude` | Claude | Claude | Separate Claude role sessions | Exactly two pooled Claude calls, distinct author/reviewer identities |
| `all-codex` | Codex | Codex | Separate Codex role sessions | Exactly two pooled Codex calls, distinct author/reviewer identities |
| `claude-architect-balanced` | Claude | Task assignment from host budget policy | Provider opposite the implementer | Codex/Claude round robin |
| `codex-architect-balanced` | Codex | Task assignment from host budget policy | Provider opposite the implementer | Codex/Claude round robin |

Same-provider decomposition is separate-session role review. It is never
cross-provider evidence. Both author and reviewer must confirm different exact
pooled conversation identities. The two-call limit is mandatory. Mixed
decomposition retains the existing bounded D1B.2 refinement circuit, regardless
of the task's implementation provider. Direct decomposition stays ephemeral
unless pooling is explicitly enabled.

## Composition and immutable schema

The Python composition root expands the profile once into frozen
`ProviderTopology`. The completion probe writes a unique UTF-8 JSON file; the
PowerShell launcher consumes that file and passes its path into the actual run.
Diagnostic stdout/stderr is not a JSON handoff channel. The consumer validates
the exact envelope, run identity, canonical topology, and routing table.

`runtime_configuration.provider_topology` in the immutable manifest contains:

| Field | Values |
| --- | --- |
| `schema_version` | `1.0` |
| `profile` | One of the four names above |
| `architect` | `claude` or `codex` |
| `provider_allowlist` | Ordered list: `claude`, `codex`, or both |
| `supervisor_policy` | Fixed provider or `follow_implementer` |
| `implementation_policy` | Fixed provider or `token_balance` |
| `validator_relationship` | `same_provider_separate_role` or `opposite_implementer` |
| `lead_developer_relationship` | Same alternatives as validator |
| `decomposition_strategy` | `claude_role_pair`, `codex_role_pair`, or `cross_provider_round_robin` |
| `session_policy` | `pooled_separate_roles` |
| `balance_metric` | `consumed_total_tokens/configured_token_budget` |
| `token_budgets` | Exactly the allowed providers, each a positive integer or JSON `null` |
| `codex_resume_required` | Boolean derived from whether Codex is allowed |

Resumes compare the full resolved topology, including budgets. A changed
profile, relationship, budget, or explicit legacy selector is rejected.
Matching fixed legacy selectors are accepted. A scalar execution/supervisor
selector cannot exactly express a mixed profile's dynamic policy, so supplying
one with a mixed profile is a contradiction. Explicit model overrides must
agree with the fixed provider; mixed models come from the existing tier policy.

The legacy manifest scalar supervisor field remains the architect provider as
a composition binding. For a profile, `supervisor_policy` is authoritative for
each worker. Reports verify every mixed worker's supervisor against its exact
implementation-provider argv rather than interpreting that legacy scalar as a
whole-run fixed supervisor.

Before paid work, preflight prints a routing table and requires only the
profile's credential volumes. Every profile containing Codex requires the
existing operator-verified `NSC_CODEX_RESUME_SANDBOX_ARGUMENT`; no sandbox
argument is guessed or automatically activated. Claude-only paths do not
resolve Codex models, credentials, or resume activation. Codex-only paths do
not resolve Claude models or credentials. Provider profiles do not authorize a
live run or substitute for its normal repository/Issue admission controls.

## Budget policy and accounting

Optional `-ProviderTokenBudget` entries use `claude=<positive integer>` and
`codex=<positive integer>`. Python accepts repeated `--provider-token-budget`.
These are configured allocations for **this immutable run**, not live account
quota discovery. Use allocations with the same accounting scope when comparing
providers. An omitted allocation is `null`, never an invented quota.

For provider P:

`pressure(P) = sum(observed invocation total_tokens for P) / configured budget(P)`

Input, cached-input, output, and total tokens are reported separately. Cached
input is a subset of input and is not added to total again. A field is `null`
when no invocation reported it or any recorded invocation lacks that field.
Unknown paid-attempt cost makes the aggregate unavailable; known calls remain
individually visible. Raw provider token counts are not treated as equivalent
budgets.

The existing batched architect request receives the host snapshot. There is no
extra balancing invocation. The architect may return a provider preference,
`preference_basis` (`capability`, `availability`, `balance`, `no_preference`),
and the existing bounded rationale. Host ordering is:

1. Enforce topology, tier safety, and observed provider availability. Mixed
   execution needs both providers because the opposite reviewer is required;
   unavailability pauses admissions instead of silently weakening review.
2. Honor an allowed concrete `capability` preference and preserve its rationale.
3. Otherwise choose the lower normalized pressure when both are known.
4. On equal or unavailable pressure, prefer more compatible warm crew sessions
   when both counts are observed.
5. Otherwise use a persisted round-robin cursor. Only this tie-break advances it.

Availability preferences from a model cannot override host observations.
Capability preference is an advisory classification with a bounded rationale;
the host does not independently prove qualitative task/provider superiority.

`provider-budget.json` lives beside the autonomous event journal. Atomic,
hash-checked writes and a host file lock protect the run identity, invocation
ledger, task/contract assignments, registered workers, role-model maps, and
round-robin cursor. Conflicting replay or changed identity fails closed.
Exact invocation IDs deduplicate replayed receipts. Assignment transactions
refresh usage under lock, including usage returned after the architect snapshot.

The fixed architect counts toward its provider. Host worker accounting includes
supervisor responses and verified crew/decomposition invocation artifacts.
Crew artifacts are bound to their exact path, bytes hash, provider, model, and
role. Successful provider responses count even when subsequent host validation
rejects the output. Architect attempts without a usable receipt and failed or
uncertain supervisor transports report unknown cost. Recent recorded failures
mark availability false for five minutes; absence of a host availability signal
is `null`, not a claim of a healthy provider.

Snapshots also include active task assignments and compatible warm crew-pool
counts. Warmth is observed from the existing pool's exact repository, provider,
model, role, capability, conversation-store, resume-control, and lifecycle
bindings. Architect, supervisor, and decomposition warmth is not combined into
that crew metric. An absent compatible crew pool is observed as empty; a pool
that cannot be located is unavailable. Corrupt pool evidence is not ignored.

Assignments persist for the exact task ID and task-contract SHA. Retries and
restarts preserve provider and pinned role models. An unavailable assigned
provider pauses the task; it does not trigger a provider switch. Changed task
contracts receive separate assignments.

## Crew execution and evidence

Each profile worker carries a hash-checked host assignment file referencing its
registered ledger entry. The host supplies five isolated pooled role leases:
implementer, test author, validator, contract locality auditor, and optional
Lead Developer. Profiles reuse the existing session pool and durable settlement
guards, with a namespace bound to conversation stores and exact Codex resume
controls. The per-profile capacity is fifty leases (five roles for ten workers).

In mixed mode, the implementer and test author use provider A, the validator and
contract locality auditor use B, ordinary repair stays with A, and revalidation
stays with B. A design block or failed second repair may request one pooled B
Lead Developer diagnosis. That diagnosis cannot approve a rejected candidate or
fabricate human PASS. An unused Lead Developer lease is cancelled through the
existing unstarted-lease path.

`run_evidence_report.py` reports the resolved topology and raw/normalized budget
rows. It reads the ledger without creating lock files or mutating run evidence.
Token totals include receipts newer than the last scheduler snapshot; active
assignments and warmth are explicitly labelled as the last scheduler observation.
Legacy architect-call attribution remains separate from the complete profile
budget ledger so their counts must not be added together.

Usage is not recovered by scanning unrelated output directories. Abrupt host
death before a receipt reaches its accounting boundary can leave that invocation
unobserved; retained artifacts remain available for investigation. This ledger
does not claim whole-account usage or reconcile calls outside this run.

## Regression scope

`Pipeline/TaskReviewAgent/tests/provider_profiles_test.py` drives real profile
composition, both PowerShell launchers, scheduler capacity polling, pooled crew
repair, bounded decomposition, supervisor turns, and report boundaries with
fake external providers and disposable Git fixtures. These are orchestration
regressions, not Unity/task acceptance or evidence of a live gauntlet.
