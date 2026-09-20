# Rigor Pipeline Policy Review — fast / standard / deep

**Review-and-design only. Nothing in this document is implemented.**

Reviewed commit: `6e9128848a471e0150a3287a9a33cf520914c003`
Checkout: `C:\NSC\ClaudeRigorPolicy\NoSafeCircle` (branch `claude/rigor-policy-review`)
Author: Claude Opus 5 review pass, 2026-09-04

Provenance tags used throughout:
`[REPRODUCED]` derived by me or an agent from code at this commit, or personally executed ·
`[LOG-DERIVED]` from a named run artifact ·
`[PROPOSED]` design not yet implemented ·
`[UNCERTAIN]` needs live validation or product judgment.

---

## 0. Executive recommendation

**The three-tier policy is not currently costing what the task brief assumes, because two of its three axes do not exist at runtime.** `crew_profile` and `validation_profile` are computed in `execution_routing.py:373-377`, validated, serialised into the `worker_launched` event, and then read by nothing. They cross zero process boundaries. `[REPRODUCED]`

That single fact reorders every priority in this review:

1. **All four ExecutionCrew roles run at every tier**, so "lean crew" is unrepresentable today. `[REPRODUCED]`
2. **Raising a task to `deep` buys zero additional automated evidence for 58 of the 60 committed tasks**, because pre-handoff Unity validation is selected by `authoritative_validation_policy.json`, which binds exactly two tasks (NSC-020, NSC-042). `[REPRODUCED]`
3. Of the four consequences the NSC-914 escalation "forced", **only reasoning effort actually bills**. `crew_profile`/`validation_profile` are inert, and `--max-turns` is a ceiling, not a floor. `[REPRODUCED]`
4. Worse, with no `NSC_ROUTE_*` environment overrides, **all three tiers resolve to the same model identifiers** (`claude-sonnet-5` / `gpt-5.6-sol`), so on the default Claude path the tier's only real lever is supervisor reasoning effort and turn ceiling. `[REPRODUCED]`

So the honest answer to the primary question is in two parts.

**Part A — the cheap win, and it is large.** Do not redesign the policy to get speed. Close the propagation gap and honour the profiles that already exist. Measured on real runs: dropping the Contract Locality Auditor and Validator on a lean profile saves **1,648,816 tokens / $1.406 (31% / 37%)** on `nsc-042-20260902t093313z` and **778,768 tokens / $1.192 (53%)** on `nsc-020-20260828t091925z`. `[LOG-DERIVED]` Separately, the full 81,662-character GDD is embedded in **all four** role prompts — about 74% of the fixed prompt bytes in a single attempt — and the Contract Locality Auditor prompt alone is ~39K tokens with no diff in it at all. `[LOG-DERIVED]`

**Part B — the shape is genuinely wrong for two things, and only two.** An ordinal scale cannot express post-diff escalation, and it cannot reach risk dimensions that have no signal in the scale. Both are real and both are load-bearing. See §0A.

**Recommended course:** a **hybrid**. Keep `fast`/`standard`/`deep` as a *derived label* for receipts, budgets and operator legibility. Underneath, compute an explicit, monotone **obligation set**. The label becomes a projection of the obligation set rather than its cause. This preserves the trivial "never weaker" proof and every existing consumer, while making post-diff escalation coherent for the first time: escalation *adds obligations*, so evidence already bound to the same commit stays valid and only newly-triggered checks run.

**Do not use a trivial synthetic task as a speed benchmark until Stage 1 and Stage 2 of §15 land.** Today a fast task and a deep task execute the same four provider roles and the same (usually zero) Unity validation; a benchmark now would measure supervisor reasoning effort and host observation latency, not rigor.

**Sequenced recommendation:**

| Order | Change | Expected effect | Risk |
| --- | --- | --- | --- |
| 1 | Close the five-boundary propagation gap (receipt-only first, no behaviour change) | 0% cost, unblocks everything | very low |
| 2 | Fix the six reproduced escalation holes in §2 **before** any tier spends less | prevents a lean tier being selected unsafely | low |
| 3 | Honour `crew_profile` in `run_crew.py` | 31–53% token reduction, measured | medium — first change that removes a safety review |
| 4 | Trim shared prompt context (GDD, dependent contracts) | large, tier-independent | low |
| 5 | Add the post-diff obligation resolver | correctness, not speed | medium |
| 6 | Make `validation_profile` executable | correctness; today it is a label over an empty set | medium |

---

## 0A. Adversarial review of the three-tier premise *(added at operator request)*

The operator asked whether three ordinal levels can deliver what is wanted, or whether checks and agents need to be grouped and tripped by independent rules. I ran a four-voice adversarial pass (three attackers, one steelman defender) plus an independent judge, all grounded in this commit. **The operator's instinct is correct, but not for the reason one would expect, and the defender lands a decisive blow that changes the sequencing.**

### 0A.1 The strongest case *against* the ordinal model

**(a) The collapse is literal, not conceptual.** Crew and validation are not *computed* — they are *read off* the scalar by one dict lookup at `execution_routing.py:373-377`, and model/effort/turns are a second lookup on the same string. Only the three diagonal combinations are expressible. `[REPRODUCED]`

**(b) Max-collapse can UNDER-protect, because a max only dominates dimensions that are members of the scale.** At least four risk dimensions have no signal in `resolve_task_rigor` at all: human-perceptual risk, migration/reset-lifecycle risk, authorisation/credential risk, and regression-breadth need. Raising the scalar cannot reach them. `[REPRODUCED]`

Concrete instances found in committed contracts:
- `_resource_paths` (`execution_routing.py:241-249`) harvests **only** `repo-file:` entries. Every `unity-scene:` and `logical:` exclusive resource is silently dropped from the escalation basis. NSC-052 declares `unity-scene:Assets/Scenes/DoorPrototype.unity` and it contributes nothing. `[REPRODUCED]`
- `predicted_change_surface.symbols_or_components` is read at `execution_routing.py:288` purely to type-check it; the value is discarded. The documented "standard is mandatory when symbol impact is not confined" rule is a no-op. `[REPRODUCED]`
- `advisory.confidence` exists but is never passed to `resolve_task_rigor`. The documented "architect reports high uncertainty → full profile" rule has no wiring. `[REPRODUCED]`
- The width and file-type checks at `:339-351` are guarded by `if minimum == "fast":`, so once any other floor fires they are never computed — the audit record loses breadth information exactly when breadth matters most. `[REPRODUCED]`

**(c) Escalation is not merely unimplemented — it is hard-refused.** At the one checkpoint the design cares about (a human has read the candidate diff and rejected it), raising the tier is rejected outright: `run_crew.py:1655/1660/1665` refuse a retry whose provider/model/effort differ from the prior run identity. The tier is also a component of every pooled role's session identity (`run_crew.py:1374/1376`), so an ordinal jump triggered by one `.asset` file retires the Test Author's warm conversation too. `[REPRODUCED]` The repository's own `IMPLEMENTATION_SEQUENCE.md:73-76` concedes this: "One route is resolved after deterministic START admission and is held through the work." `[REPRODUCED]`

**(d) The alternative already exists downstream.** `downstream_pipeline.py:464-470` computes *required minus completed* platforms and returns exactly one next action; evidence is keyed `(test_platform, test_filter)` and invalidated when `manifest.commit != head_commit` (`:628-639`). That is an obligation set with per-key invalidation — the right shape, already built, with the ordinal tier bolted on top and appearing in none of those keys. `[REPRODUCED]` `candidate_integration.py:479-481` likewise already triggers a Unity scene rebuild from a deterministic *path predicate*, not from a tier. `[REPRODUCED]`

### 0A.2 The strongest case *for* keeping it (steelman)

**(a) The ordinal is not what is costing money — the propagation gap is.** Of the four things NSC-914's escalation forced, two are inert strings, one is a ceiling that bills nothing on a run that ends early, and only reasoning effort charges. A composite model changes none of that. `[REPRODUCED]`

**(b) A composite model does not touch the single largest cost item.** `_required_platforms` (`downstream_pipeline.py:189-202`) defaults to **both** EditMode and PlayMode on a prose keyword miss. Two Unity launches dwarf a reasoning-effort bump, and that default is tier-independent under either model. `[REPRODUCED]`

**(c) Monotonicity is currently free.** `raise_floor` only moves `minimum` up `_TIER_RANK`, and `effective = max(requested, minimum)`. "A stronger tier is never weaker" is a two-line structural fact. A union-of-obligations model must *prove* the equivalent exhaustively over 2^n signal combinations. `[REPRODUCED]`

**(d) Legibility.** `deep` fits in a log line and answers "why did this run cost so much". Ten obligations with per-item triggers do not. The `Audit record` section of `TASK_RIGOR_PROFILES.md` was designed around a scalar.

**(e) Architect output reliability.** The architect returns one enum today and cannot express an incoherent combination. Asking a model for orthogonal risk dimensions admits `{crew: lean, evidence: full_relevant, budget: deep}` — schema-valid, semantically incoherent.

### 0A.3 My synthesis

Both sides are right about different things, and the disagreement is about *sequencing*, not about the end state.

- The defender is right that **the ordinal shape is not the current cost driver**, and that replacing it first would be a pure-cost migration that saves nothing.
- The attackers are right that **the ordinal shape is a correctness ceiling** for post-diff escalation and for the four dimensions with no representation in the scale. Those cannot be fixed by threading the existing profiles through.

Therefore: **fix the gap first, adopt obligations second, and keep the tier as a derived label permanently.**

**Proposed target shape** `[PROPOSED]`:

- Five axes, each with its own minimum and its own lattice: `identity-invariant` (always on), `crew`, `provider-budget`, `automated-evidence`, `human-judgment`.
- A committed, ordered table of `(group_name, axis, predicate, discharge_action, evidence_key)`.
- Two resolution points: `resolve_task_obligations(...)` at admission (committed contract + architect prediction), and `resolve_integration_obligations(admission_set, execution_receipt, crew_result)` at integration (actual diff). The second is **monotone add-only** — de-escalation is forbidden, which is exactly where the ordinal gets its safety from `_TIER_RANK`.
- `capability_tier` becomes `derive_label(obligation_set)`, emitted in the receipt so every existing consumer keeps working.
- Obligations carry the **evidence keys the artifacts already use** — `(test_platform, test_filter, commit)` for Unity, `(source_head, source_tree, task_contract_sha256)` for the locality audit, candidate SHA for the crew — so "what stayed valid after escalation" becomes answerable instead of unauditable.

**What must be proven before adopting** `[PROPOSED]`:
1. For every reachable signal combination, the obligation set is a **superset** of what today's ordinal would have required. This is the replacement for the free monotonicity proof and must be a generated exhaustive test, not spot checks.
2. Trigger predicates must be computed from *committed* facts and *deterministic* diff facts only. Re-deriving obligations from the actual diff opens a self-certification channel: the writer influences its own review requirements. Mitigate by making every diff-keyed obligation **add-only** and by never letting a diff fact *remove* an admission obligation.
3. Keyword/lexicon triggers (perceptual gates, migration gates) are as brittle as the `_required_platforms` prose matching this review criticises. They must be backed by an explicit contract field, with the lexicon as a fail-closed fallback that escalates, never de-escalates.

**Falsifiable conditions — I am wrong if:** closing the propagation gap alone gets a trivial task under five minutes *and* no task in the next 20 runs exhibits a post-diff surface drift that the admission tier failed to catch. In that case the ordinal model is sufficient and the composite is over-engineering. `[UNCERTAIN]`

### 0A.4 Direct answer to the operator's question

> *"Maybe we need to break up the checks/tests into different groups and it needs to be a composite of different checks. Different rules trip a set of tests or agent type?"*

Yes — and the repository is already half-way there without naming it. `_requires_door_prototype_builder`, the `(platform, filter)` manifest keys, and `required minus completed` are all obligation-shaped. What is missing is a **single committed table** that names the groups, their triggers, and their evidence keys, so that the same mechanism governs crew roles, provider budget, automated evidence and human judgment instead of only Unity platforms.

The one thing I would *not* do is let the architect emit the obligation vector. It should emit judgment (`capability_tier`, `integration_risk`, `confidence`); the deterministic host should own the mapping from judgment plus committed facts to obligations. That preserves "the architect cannot waive repository-owned safety policy with prose."

### 0A.5 Independent judge verdict, and the measurement that settles it

A fifth agent, given only the four positions and the checkout, returned the verdict **`hybrid-derived-label-over-obligations`** — the same shape as §0A.3, reached independently. It also produced one measurement none of the four analysts found, which I have **re-run myself on this checkout and reproduced exactly**.

**Census over all 60 committed contracts** (`resolve_task_rigor` with architect=`fast`, surface = each contract's own `repo-file:` resources, `committed_path_probe` returning True): `[REPRODUCED — personally executed at 6e91288]`

| Population | deep | standard | fast |
| --- | --- | --- | --- |
| Today | **29** | 12 | 19 |
| With each contract's `unity-scene:` resource declared (i.e. after fixing G4) | **46** | 12 | **2** |

**Resource loss:** the 60 contracts declare **95** `exclusive_resources`. `_resource_paths` harvests only the 49 `repo-file:` entries and silently drops **46** — 26 `unity-scene:` and 20 `logical:` — spread across **35 of 60 tasks**. There are no other prefixes. `[REPRODUCED]`

**The finding that makes this a decision rather than a preference.** `TASK_RIGOR_PROFILES.md:70` declares a *mandatory* floor: at least `standard` when "a test must be designed or changed rather than merely executed from committed policy." That predicate is exactly `validation_plan_for(...) is None`, true for 58 of 60 tasks. Implemented as an ordinal `raise_floor` call, the census becomes **deep 29 / standard 30 / fast 1** — only NSC-020 remains eligible for `fast`.

The repository's own committed specification is therefore *unimplementable under the ordinal*, not because the rule is wrong but because a **crew/evidence fact cannot be recorded without also purchasing `high` reasoning and 80 turns from the same `_TIER_DEFAULTS` row** (`execution_routing.py:72-76`). That is the mechanical reason the rule has stayed unwritten, and the same reason `symbols_or_components` is validated and discarded at `:288` rather than implemented as `TASK_RIGOR_PROFILES.md:69` requires. `[REPRODUCED]`

**The cost side is smaller than the brief assumes.** I confirmed by repository-wide grep that **no `NSC_ROUTE_*` variable is set anywhere in the repository** — the only non-test occurrence is the prefix construction at `execution_routing.py:722`. Against an empty environment, `fast`, `standard` and `deep` all resolve to execution model `claude-sonnet-5`, supervisor model `gpt-5.6-sol`, and `execution_reasoning_effort=None` (populated only for codex, `:634-640`). The complete observable delta is supervisor reasoning effort and a turn ceiling. `[REPRODUCED]` — with the caveat in §17 that the operator's *live shell* may export these; that must be checked before the cost model is trusted.

**Where the judge corrected the analysts, and where I correct the judge.**
- Judge, correcting the composite proposal: drop the `EV-GENERATED-ARTIFACT-IDENTITY` byte-comparison group. `preflight_role_paths` already refuses any *new* role path ending in `.meta` (`run_crew.py:700`) and requires generated sidecars absent from the captured tree (`:722-725`); the bytes are written by the pipeline itself from `unity_meta_bytes` (`:638-641`). Byte-comparing bytes the pipeline just wrote proves nothing. **Keep** the serialized-diff review for edits to *existing* `.meta` files, which a role genuinely can make — the `kind == "existing"` branch at `:696-699` has no `.meta` exclusion. I agree; §9 reflects this.
- Judge: "zero committed tasks ever contain 'edit mode'." **Not quite.** One does — NSC-057's gate prose names Edit Mode, but it also names Play Mode, so `_required_platforms` still returns both. The correct statement, which I measured, is: `_required_platforms` returns **`(EditMode, PlayMode)` for 44 contracts and `(PlayMode,)` for 16; no contract ever selects EditMode alone.** EditMode is reached only by a keyword miss. `[REPRODUCED]`
- Judge, reproducing a defect I had not: with architect=`deep` and a `>4`-path standard floor, `override_reasons` is non-empty while `architect_recommendation_honored` is `True` and nothing was actually overruled — breaking the property the docstring at `:96-99` promises and `__post_init__:138-146` only partially guards. `[REPRODUCED by agent]` Listed as **G16** and scheduled into Phase 0.
- Judge, on migration cost: the Gauntlet is **not** a migration cost. `scheduler_adapter.py:1511-1517` supplies a *default* `capability_tier` rather than reading one, and `manifest.py` contains zero tier/rigor references. The real test surface is 32 `capability_tier` assertions in `execution_routing_smoke_test.py`, 11 in `polling_orchestrator_smoke_test.py`, 6 in `architect_preflight_smoke_test.py`, and 12 `crew_profile`/`validation_profile` assertions. Under a faithful derived label these all keep passing unchanged — which is precisely the Phase 1 acceptance test in §16.

**The judge's non-negotiable, which I adopt verbatim into §15:** any obligation group whose enforcement is not yet wired ships with an explicit `receipt_only: true` marker in the route event, and a group may lose that marker **only in the same change that adds its argv flag and its enforcement site**. The stated reason is the repository's own history: `ROLE_CAPABILITY_CLASSES` is an orthogonal per-role cost axis that was threaded into pooled-lease identity and then short-circuited to one model string at `run_crew.py:522`. `crew_profile`/`validation_profile` are the second instance of the same decay. A group with no consumer is how this codebase fails.

**Sequencing consequence.** Phase 0 (the shape-independent bug fixes) must land **and be re-measured** before any obligation table is calibrated. Calibrating triggers against a population where 46 of 95 declared resources are invisible calibrates against the wrong population — the corrected census is 46 deep, not 29.


---

## 1. Verified current behavior and call graph

### 1.1 The six-hop process ladder `[REPRODUCED]`

```
polling_orchestrator.py            host scheduler process
  |- architect batch call          ONE provider call for the whole admission batch (:2852-2999)
  |- resolve_task_rigor            (:3400) pure, no I/O beyond committed_path_probe
  |- resolve_execution_route       tier -> provider/model/effort/turns
  |- build_worker_command          (:1538-1651)  <-- BOUNDARY 1: the profiles stop here
       |
       v subprocess
host_worker_launcher.py            argv -> PowerShell argv (:60-124)
       |
       v subprocess
Start-GameTaskAgent.ps1            launcher_preflight, gh auth, codex login, Docker checks
       |
       v subprocess
run_pipeline_agent.py              constructs ProductionTaskController, Codex supervisor loop
       |
       v
production_pipeline.py             ProductionTaskController; publish_human_handoff
       |
       v
execution_bridge.py                docker compose run <provider>-exec
       |
       v container
Pipeline/ExecutionCrew/run_crew.py four roles, disposable clone, candidate.patch
```

### 1.2 What actually crosses Boundary 1 `[REPRODUCED]`

`build_worker_command` receives the whole `route` object — which still holds `route.rigor` — but reads only six fields (`polling_orchestrator.py:1560-1566`). The emitted argv is:

```
--task-id --mode --source --checkout-root --worker-id
--execution-provider --max-turns --output-root
[--model] [--supervisor-reasoning-effort]
[--execution-model] [--execution-reasoning-effort]
[--enable-execution-session-pool]            (Claude + model only, :1621)
--run-id --admission-source-head --task-contract-sha256
[--admission-issue-number]
```

`crew_profile`, `validation_profile`, `human_verification_policy` and even `capability_tier` itself are absent. The tier survives only as its *projections* (model, effort, turns).

### 1.3 What the tier actually changes today

| Lever | Fast | Standard | Deep | Real effect |
| --- | --- | --- | --- | --- |
| `max_supervisor_turns` | 40 | 80 | 120 | A **ceiling**; bills nothing on a run that ends early `[REPRODUCED]` |
| supervisor reasoning effort | medium | high | xhigh | **The only lever that reliably bills** `[REPRODUCED]` |
| `claude_model` / `openai_model` | — | — | — | **Identical across tiers** with no `NSC_ROUTE_*` env set `[REPRODUCED]` |
| `crew_profile` | lean | standard | full | **Inert.** No consumer `[REPRODUCED]` |
| `validation_profile` | targeted | task_specific | full_relevant | **Inert.** No consumer `[REPRODUCED]` |
| `human_verification_policy` | required | required | required | Hardcoded constant (`:385`); `machine_evidence_permitted` unreachable `[REPRODUCED]` |

### 1.4 ExecutionCrew: what actually runs `[REPRODUCED]`

Four roles, straight-line, no profile branch: `contract_locality_auditor` (`:2120`), `implementer` (`:2171`), `test_author` (`:2193`), `validator` (`:2233`). The auditor is a **hard gate** — a non-empty `audit_scope` sets `crew_status='rejected'` at `:2136` and the clone, implementer, test author and validator never run. The writer/validator triple runs inside `for attempt in (1,2)` (`:2166`); attempt 2 is entered only when the validator returned blocking issues.

`ROLE_CAPABILITY_CLASSES` (`:1167-1172`) assigns `high_reasoning` / `standard` / `low_cost` per role — but `runtime_configuration` (`:519-522`) maps **all three classes to the same model string**, and `:1682` overwrites `execution_model` with the `standard` entry. The per-role cost axis is therefore collapsed a second time inside the container. `[REPRODUCED]`

No token budget is ever set: `Budgets(turn_limit, timeout_seconds)` leaves `token_limit=None` (`run_crew.py:1972`), so per-role spend is bounded only by 32 turns and 1200 seconds. `[REPRODUCED]`

### 1.5 Authoritative validation: selected by committed policy, not by tier `[REPRODUCED]`

`validation_plan_for` (`downstream_resilience.py:170`) keys on `task_id`, requires an exact 64-hex `task_contract_sha256` match, and returns `required_test_platforms`, `test_filters`, `authority`, `policy_path`, `policy_sha256`. `authoritative_validation_policy.json` binds **two** tasks. For the other 58 it returns `None`, and `candidate_integration.py:667-669` skips pre-handoff Unity validation entirely.

When no policy binds, `_required_platforms` (`downstream_pipeline.py:191-202`) keyword-matches completion-gate prose and **defaults to both EditMode and PlayMode**. `test_filter` has **no default at all** — it is a required caller argument. So "targeted" versus "full_relevant" has no implementation anywhere in the pipeline.

---

## 2. Current integration gaps

Ordered by how much they matter for a safe fast tier. Every item is `[REPRODUCED]`.

**G1 — The profiles are inert.** `execution_routing.py:373-377` to the `worker_launched` event to nothing. Five boundaries would need a parameter each. This is the root cause of "all tiers cost the same in crew tokens".

**G2 — The rigor decision never sees actual paths.** `resolve_task_rigor` is called with `advisory.predicted_change_surface` (`polling_orchestrator.py:3400-3404`). The `effective_surface` computed 340 lines earlier (`:3062-3066`) — which folds a resumed task's *actual* changed paths and reclassifies `<asset>.meta` companions — is used only for conflict detection and never reaches the tier. **Every escalation is therefore based on prediction alone.** This is the single most load-bearing gap for section 7.

**G3 — `resolve_execution_route` is fail-open on `rigor`.** `rigor: TaskRigorDecision | None = None` (`:588`); when `None` the architect's tier is used with **no repository floor at all**. Any future caller that forgets the parameter silently loses the entire deterministic minimum.

**G4 — Non-`repo-file:` exclusive resources are dropped.** `_resource_paths` (`:241-249`) filters to `repo-file:` only. `unity-scene:` and `logical:` declarations — the repository's own way of naming shared risk — contribute nothing to escalation. NSC-052 declares `unity-scene:Assets/Scenes/DoorPrototype.unity`; it is ignored.

**G5 — Documented rules with no implementation.** `symbols_or_components` read and discarded (`:288`); `advisory.confidence` never passed; `.github/` in `_FULL_RIGOR_ROOTS` is dead code because `lstrip('./')` at `:174`/`:330` strips the leading dot.

**G6 — `.meta` is unconditionally lean.** `.meta` is in `_FAST_SURFACE_SUFFIXES` (`:63`) while the companion classifier inspects only `unity_serialized_assets` (`:285-286`, `:313-315`). A scene or prefab `.meta` declared only in `exact_paths` reaches `crew=lean`, contradicting the doc's guarantee.

**G7 — Over-escalation on extensionless paths.** `PurePosixPath('Makefile').suffix` is empty, and empty is not in `_FAST_SURFACE_SUFFIXES`, so *every* extensionless path escalates to standard: `Makefile`, `LICENSE`, `.gitignore`.

**G8 — Path dedupe is case-sensitive but the rules are not.** `dict.fromkeys` over raw strings (`:274-282`) while every downstream rule casefolds. Three spellings of one path count as three toward the four-path bound.

**G9 — Escalation is hard-refused on retry.** `run_crew.py:1655/1660/1665` reject a retry whose provider/model/effort differ from the prior run identity; `:1374/1376` reject a pooled lease whose model/effort differ. Raising the tier after human review is impossible by construction.

**G10 — Decomposition launches carry no rigor audit.** `polling_orchestrator.py:3386-3391` builds a hardcoded `route_event` with `capability_tier: "deep"` and none of the six documented audit fields.

**G11 — Pool always reserves all four roles.** `execution_session_pool.py:367` loops `CREW_SESSION_ROLES` unconditionally, and `run_crew.py:1253-1254` raises if the bundle is not exactly four. A lean run reserves the same four conversations a deep run does.

**G12 — `decomposition_child_templates` is missing from the policy file.** `decomposition_validation_policy_for` (`downstream_resilience.py:322-330`) requires the document key set to be exactly `schema_version`, `tasks`, `decomposition_child_templates`; the committed file has only the first two. Any decomposition parent resolution raises.

**G13 — A measured PlayMode launch ran 0 tests and reported "passed".** `validation-manifest.json` `test_run.total=0`, `test-results.xml testcasecount="0"`, cost 105.6 s. `[LOG-DERIVED]` A validation obligation that matches nothing must fail closed, not pass.

**G14 — Pooling has a permanent-denial bug and no stranded-lease reclamation.** `prepare()` selects a probation record without checking `is_retry_offerable_at`, and the call it then makes expires that record. Separately, `execution_bridge.py:429-435` re-raises without quarantining and `expire_idle` ignores `active`, so leases stranded by a crash are never reclaimed; after enough crashes the pool deadlocks against `POOL_CAPACITY = 40`. `[REPRODUCED]`

**G15 — Codex pooling is structurally unreachable.** `enable_session_pool` acts only when provider is `claude` (`execution_bridge.py:384`), `prepare()` hardcodes `claude-code`, and `codex_resume_sandbox_argument` has no CLI plumbing. `[REPRODUCED]`

**G16 — `override_reasons` reports overrides that never happened.** With architect=`deep` and a `>4`-path `standard` floor, `override_reasons` is non-empty while `architect_recommendation_honored` is `True` and nothing was actually overruled. `raise_floor` appends to both `reasons` and `overrides` unconditionally (`:298-299`) whether or not the floor exceeds the architect's request. This breaks the property the docstring at `:96-99` promises, and `__post_init__` (`:138-146`) guards it only partially. It is the audit record's own integrity, so it must be fixed before the record is asked to carry five axes.

---

## 3. Guard / phase inventory with A-E classification

251 phases were inventoried across eight subsystems by parallel tracers, each re-checked by an independent verifier (73 corrections, 84 additions). The full per-phase table is too large to reproduce here; what follows is the decision-relevant summary. Classification key: **A** invariant, **B** tier-selectable, **C** conditional after actual-diff inspection, **D** cacheable/reusable, **E** redundant.

### 3.1 Category A — invariant, must run at every tier

| Guard | Location | Failure prevented |
| --- | --- | --- |
| Stage-2 admission kernel (contract fields, TaskGraph state, dependencies, Issue ownership, reservations, claim refs) | `dispatch_plan.evaluate_fresh_candidate` | Wrong or unauthorised task admitted |
| Ephemeral atomic multi-ref claim (`push --force-with-lease`) | `claim_refs.py:549-557` | Two workers on one task |
| Durable Issue lease and event-chain integrity | `issue_workflow_store.py` | Forged or forked workflow state |
| Exact source HEAD and `task_contract_sha256` | `candidate_integration.py:331`, `:394` | Work built against the wrong base |
| Physical read-only source mount assertion | `run_crew.py:1636-1645` | Crew mutating the canonical checkout |
| Deterministic incremental changed-path scope check | `run_crew.py:2171-2187`, `:2202-2216` | Role writing outside its boundaries |
| Final clone snapshot after sidecar generation | `run_crew.py:2258` | Pipeline-generated `.meta` escaping scope validation |
| `verify_patch_applies` against real source | `run_crew.py:997`, called `:2287` | Candidate that cannot apply cleanly |
| Worker-result identity re-verification | `worker_result.py:207-302` | Accepting a result from a different run |
| Merge of current main before authoritative testing, plus revalidation | `mainline_reintegration` | Testing stale code |
| Evidence bound to exact commit; manifest rejected when commit differs | `downstream_pipeline.py:628-639` | Stale evidence |
| Guarded fast-forward publication and post-merge verification | `mainline_reintegration` | Unreviewed content on main |
| Post-Unity churn fence | `safe_unity_churn.py:89-120`, `:140-205` | Regenerated artefacts silently committed |
| Approved-remote allow-list; controller HEAD equals origin/main | `durable_checkout.py:351-352`, `:383-389` | Work against an unapproved remote |
| Handoff checkout origin equals controller origin | `real_workflow.py:399-408` | Handoff proven against a different repository |

**Verifier correction accepted:** a tracer proposed `run_authoritative_unity_test` as **E-redundant** (covered by the pre-handoff run). Downgraded to **D-cacheable-with-conditions**: after `integrate_current_main` the merge creates a new commit and tree, so the pre-handoff manifest no longer binds. It proves the same property *only* when the commit is unchanged.

### 3.2 Category B — legitimately tier-selectable

| Item | Location | Note |
| --- | --- | --- |
| Provider model / reasoning effort / turn ceiling | `execution_routing.py:583-644` | The only tier lever wired today |
| Contract Locality Auditor invocation | `run_crew.py:2120` | Most expensive single prompt (~39K tokens); **a hard gate, not just a cost centre** |
| Test Author invocation | `run_crew.py:2193` | Omissible only under a fail-closed "no new test paths" rule |
| Validator invocation | `run_crew.py:2233` | Sole input to the attempt-2 repair cycle |
| Attempt-2 repair cycle | `run_crew.py:2166` | ~110K additional input tokens |
| Pool role-lease breadth | `execution_session_pool.py:367` | Currently fixed at four |
| Per-role capability class to model mapping | `run_crew.py:519-522` | Currently collapsed to one model |

### 3.3 Category C — conditional after actual-diff inspection

| Item | Trigger |
| --- | --- |
| DoorPrototype scene rebuild | `_requires_door_prototype_builder`, `candidate_integration.py:479-481` — **the existing precedent for obligation-style triggering** `[REPRODUCED]` |
| Serialized-asset review | *(proposed)* actual diff contains a `_FULL_RIGOR_SUFFIXES` path |
| Surface-drift review | *(proposed)* `final_actual_changed_paths` is not a subset of the predicted surface |
| Generated-sidecar identity check | *(proposed)* `crew_result['pipeline_generated_paths']` is non-empty |

### 3.4 Category D — cacheable / reusable, with named replacement

| Item | Saving | Replacement that still proves the property |
| --- | --- | --- |
| Routing observation duplicated by turn 1 | **33.891 s** measured `[LOG-DERIVED]` | The phase-change guard already re-reads state before mutating |
| Two full `gh api --paginate` listings per observation | ~15 s/turn `[LOG-DERIVED]` | One listing feeds both `find()` and `_unauthorized_claimant_diagnostics` |
| `taskcontrol states` bulk observation | 60-90 s, ~150x the cost of `validate` `[LOG-DERIVED]` | Memoise on (repo root, source_commit); it is a pure function of the tree |
| `taskcontrol validate` per turn | 405 git subprocesses, 14.4 s `[LOG-DERIVED]` | Memoise on HEAD tree SHA |
| Contract Locality Auditor across a human-review retry | ~39K tokens | Cache key (task_contract_sha256, source_head, source_tree, work-graph hash); the prompt contains no diff |
| Full GDD in all four prompts | 326,648 of ~442K fixed prompt chars (74%) `[LOG-DERIVED]` | GDD is already in `context_paths`; roles have read capability |
| Auditor dependent-contract payload | 40,767 chars, 26% of that prompt `[LOG-DERIVED]` | The catalog it also receives already carries id/key/title |
| Pre-handoff manifest reuse downstream | one Unity launch per task instead of two | Reuse branch already exists at `downstream_pipeline.py:632-641` |
| `codex login status` throwaway container per volume | container startup per run | Cached volume revalidated as a hint, not trusted |

### 3.5 Category E — genuinely redundant

Only three items survived verification as E:

1. **`crew_profile` / `validation_profile` as currently emitted.** They are a deterministic 1:1 function of `capability_tier`, which is in the same event dict. They carry zero information today. *This is an argument for making them real, not for deleting them.*
2. **Two of three checks in `ExecutionCrewBridge._preflight_docker`** (`execution_bridge.py:252-272`) — `shutil.which("docker")` and compose availability are already proven earlier in the same process tree by `Start-GameTaskAgent.ps1`. The checkout-local `compose.yaml` assertion is **not** redundant.
3. **`launcher_preflight` for scheduler-launched workers** (`Start-GameTaskAgent.ps1:100-116`) — re-reads the Issue and re-runs the Stage-2 kernel the scheduler just ran, when `-RunId`/`-AdmissionSourceHead`/`-TaskContractSha256` already carry that proof and `run_pipeline_agent` independently re-verifies them.

**Rejected E claims** (proposed by a tracer, refuted by its verifier): the attempt-1 crew invocations (they *produce* the candidate); the attempt-2 repair cycle (conditional, and the validator's output is its sole input); the pool lease reservation (correctness-bearing — it binds provider, model, role, capability class and repository identity); the final clone snapshot (sidecars are written *after* the role snapshot); `_required_platforms` (load-bearing at three call sites no policy check covers); `_verify_receipt` (it *is* the cache-validation mechanism, and launches nothing).

---


## 4. Fast policy

Everything in §4–§6 is `[PROPOSED]` unless tagged otherwise. Each section answers the four decisions **separately and in order**, because collapsing them is the defect this review exists to name.

### 4.0 What `fast` is, under the recommended shape

`fast` is a **derived label**, not a cause. It is emitted when the resolved obligation set contains no member of `DEEP_MARKERS` and no member of `STANDARD_MARKERS`. It answers **one** question — provider budget — and answers it by projection. It does not, and must not, answer crew composition, evidence breadth, or human verification.

### 4.1 Decision 1 — architect recommendation

The architect may recommend `fast`. The architect's recommendation is **additive only**: `fast → {}` budget groups. It can never *lower* a floor and it can never touch the crew, evidence, or human axes. This preserves `execution_routing.py:365-372` exactly, and it is the mechanical expression of "the architect must not be able to waive repository-owned safety policy with prose."

### 4.2 Decision 2 — deterministic minimum

All of the following must hold, evaluated on **committed contract facts plus the architect's predicted surface**, after the Phase 0 fixes in §15:

| # | Condition | Source today |
| --- | --- | --- |
| F1 | `execution_scope == 'single_agent'` and `decomposition_state == 'concrete'` | `:301-305` |
| F2 | `exact_paths` non-empty | `:308` |
| F3 | `path_patterns` empty | `:310` |
| F4 | `shared_systems` empty | `:312` |
| F5 | `symbols_or_components` ⊆ the declared exact paths | **not implemented today** (`:288` discards it) |
| F6 | ≤ 4 paths after **case-insensitive** normalization | `:341` — today the dedupe at `:274-282` is case-sensitive (G8) |
| F7 | Every suffix in `_FAST_SURFACE_SUFFIXES`, with `.meta` removed from that set and handled by the companion rule instead | `:63`, `:349` (G6) |
| F8 | No path under `_FULL_RIGOR_ROOTS` and no `_FULL_RIGOR_NAMES` basename, with the `.github/` entry actually reachable | `:333-335`, `:41` (G5) |
| F9 | Serialized assets, if any, are exclusively **new** `<script>.cs.meta` companions proven absent from the committed tree by the probe | `:313-327` |
| F10 | **New:** no `unity-scene:` or `logical:` entry in `exclusive_resources` | **not implemented today** (G4) |
| F11 | **New:** extensionless paths (`Makefile`, `LICENSE`) are classified explicitly, not by empty-suffix fallthrough | (G7) |

**Measured consequence of F10 alone:** the eligible-`fast` population drops from 19 to 2 of 60 contracts. `[REPRODUCED]` The operator must see that number before adopting a fast tier, because it says the current 19 are cheap largely by parser accident.

### 4.3 Decision 3 — post-implementation validation

**This decision is answered by the evidence axis, not by the label.** A `fast` budget does not authorize less evidence.

- If `validation_plan_for(...)` binds the task: run **exactly** `required_test_platforms × test_filters` pre-handoff against the exact candidate commit and tree. Non-negotiable, identical at every tier.
- If it does not bind (58 of 60 today): the run records `automated_evidence: none_bound` plus the advisory `_required_platforms` set, and **the receipt must not claim validation ran**. This is the direct replacement for the current `validation_profile: full_relevant` string that resolves to an empty tuple at `candidate_integration.py:667-669`.
- A validation obligation that matches zero tests **fails closed**. A manifest with `test_run.total == 0` is a failed run, not a pass (G13). `[LOG-DERIVED]`

### 4.4 Decision 4 — human verification

`human_policy` stays `required` (`:385`). `fast` does not authorize a machine-evidence exception.

The documented exception at `TASK_RIGOR_PROFILES.md:106` is conditioned on "the effective tier is fast" — but `fast` is a **path-count-and-suffix test** (`:339-351`). That is a *size* proxy standing in for a *judgment* proxy, and they are not the same predicate. A one-constant diff whose acceptance criterion is "the wall must read as continuous at the gameplay camera" is small and needs eyes. **13 of 60 committed contracts match the judgment lexicon** (`visual, camera, sorting order, reads as, audio, sound, animation, feel, timing, latency, human validation, human runtime`) in their AC or gate prose. `[REPRODUCED]` For those, human visual review is required *independently of tier*, and no other axis may remove it.

### 4.5 What `fast` may never waive

Every Category-A guard in §3.1, without exception: admission kernel, atomic claim, contract/HEAD identity, read-only source mount, per-attempt changed-path scope validation, final post-sidecar snapshot, `verify_patch_applies`, worker-result identity re-verification, merge of current main before authoritative testing, evidence-to-commit binding, guarded publication, post-Unity churn fence, approved-remote allow-list. These are not tier-selectable at any tier and must not appear in any obligation table as optional.

### 4.6 Exit conditions

`fast` is abandoned — the run escalates — the moment any §7 post-diff trigger fires. Escalation is **add-only**; see §7.3 for why the current retry-identity refusal makes this impossible today.

---

## 5. Standard policy

### 5.1 Decision 1 — architect recommendation

Architect `standard` unions in `{BUDGET-SUPERVISOR-EXTENDED}`. Nothing else.

### 5.2 Decision 2 — deterministic minimum

`standard` is the floor when any of these hold and no `deep` trigger does:

| Trigger | Source | Note |
| --- | --- | --- |
| `exact_paths` empty | `:308` | no established surface |
| `path_patterns` non-empty | `:310` | broader-than-exact review |
| `> 4` normalized paths | `:341` | **breadth, not depth** |
| Non-lean suffix present | `:349` | |
| `symbols_or_components` not confined to the declared paths | `TASK_RIGOR_PROFILES.md:69`, unimplemented | |

**The separation this tier exists to make.** Breadth and depth are different needs and today they come from the same `_TIER_DEFAULTS` row. A 12-file mechanical rename needs **turns**, not `high` reasoning. Under the obligation model `BUDGET-SUPERVISOR-EXTENDED` raises `max_supervisor_turns` to 80 and **explicitly does not raise reasoning effort**. That combination — 80 turns at `medium` — is inexpressible ordinally, and it is the single cheapest correctness win in the whole design.

### 5.3 Decision 3 — post-implementation validation

Identical rule to §4.3. `standard` does not buy more evidence, because evidence breadth is not a function of budget. What `standard` *does* add is the **CREW-TESTS** obligation: when no committed filter binds the task, a Test Author must design one **and the authored filter must be recorded in `crew_result.json`** so it can later be promoted into `authoritative_validation_policy.json`. That promotion path is how 58/60 eventually becomes a smaller number; without it the evidence axis never improves.

### 5.4 Decision 4 — human verification

Unchanged: `required`. Plus the judgment-lexicon rule from §4.4 if it matches.

### 5.5 Exit conditions

Same as §4.6, plus: if the actual diff introduces a `shared_systems`-adjacent path or any `_FULL_RIGOR_SUFFIXES` file, the run escalates to the `deep` obligations for the *remaining* work — it does not restart.

---

## 6. Deep policy

### 6.1 Decision 1 — architect recommendation

Architect `deep` unions in `{BUDGET-SUPERVISOR-EXTENDED, BUDGET-XHIGH-REASONING, BUDGET-IMPL-HIGH}`.

### 6.2 Decision 2 — deterministic minimum

`deep` is the floor when any of these hold:

| Trigger | Source | Change proposed |
| --- | --- | --- |
| `shared_systems` non-empty | `:312` | unchanged |
| Path under `.github/`, `Packages/`, `Pipeline/`, `ProjectSettings/` | `:335` | fix the `.github/` dead branch (G5) |
| Basename in `agents.md`, `compose.yaml`, `dockerfile` | `:335` | unchanged |
| Substantive Unity serialized asset | `:337` | **split**: the *budget* half keeps `.unity/.prefab/.asset`; the `.meta`-suffix half moves to the evidence axis |
| `execution_scope != 'single_agent'` or `decomposition_state != 'concrete'` | `:304` | unchanged |
| **New:** any `unity-scene:` exclusive resource | (G4) | **moves 17 tasks from fast/standard to deep** `[REPRODUCED]` |

`BUDGET-XHIGH-REASONING` raises supervisor effort to `xhigh` and turns to 120. `BUDGET-IMPL-HIGH` raises the **Implementer's** `model_capability_class` from `standard` to `high_reasoning` for this run only, through the pooled lease's `capability_class` (`session_pool.py:119, :145`). No setting of the current tier can move that: `ROLE_CAPABILITY_CLASSES` is a module constant and `runtime_configuration` collapses all three classes to one model string (`run_crew.py:519-522`). Until that collapse is fixed, `BUDGET-IMPL-HIGH` is **receipt-only** and must be labelled so.

### 6.3 Decision 3 — post-implementation validation

`deep` adds two evidence obligations that are genuinely about depth, not budget:

- **Serialized-diff review.** Any path in the *actual* diff whose suffix is in `_FULL_RIGOR_SUFFIXES` and which is not a pipeline-generated sidecar blocks handoff until a machine-generated serialized-asset diff summary (per-file added/removed/changed YAML keys, every GUID reference delta) is attached to the receipt. This keys on the **actual** diff; today the trigger is the *predicted* surface (`:337`), so an unpredicted `.prefab` escalates nothing.
- **Scene rebuild**, already implemented at `candidate_integration.py:479-481` and reachable from a diff predicate with no tier involvement — the existing proof that this repository already resolves obligations from diff facts.

`deep` still does **not** run more Unity tests than `fast` unless `authoritative_validation_policy.json` binds the task. That is the honest statement and it must appear in the receipt.

### 6.4 Decision 4 — human verification

Unchanged: `required`. `deep` adds the **migration** obligation: any `Assets/` path present in the baseline snapshot and absent in the final one (a delete or rename), or any `.asset/.prefab/.unity` path present in **both** snapshots (an edit, not an add), requires an explicit human data-loss acknowledgement naming each path before merge-closeout. Both snapshots are already taken (`run_crew.py:603-606`). The ordinal model cannot distinguish an *added* serialized asset from an *edited* one — `_classify_serialized_surface` (`:196`) uses the probe only to exempt new sidecars, and both cases collapse to the same escalation.

---

## 7. Pre-diff / post-diff escalation design

### 7.1 The structural problem

The tier is resolved **once**, at `polling_orchestrator.py:3400`, from the architect's *predicted* surface, and the worker launches 39 lines later at `:3439`. `final_actual_changed_paths` is not written until `run_crew.py:2362` — inside a container, in a different process, typically an hour later. `grep -E 'tier|rigor' Pipeline/ExecutionCrew/*.py` returns nothing; `worker_result.py` has zero hits. There is no code path by which a diff fact can influence a rigor decision. `[REPRODUCED]`

Compounding it, **G2**: the resolver is handed `advisory.predicted_change_surface`, not the `effective_surface` computed at `:3062-3066` that folds a resumed task's actual changed paths. Even the information the host already has does not reach the decision.

### 7.2 Two resolution points `[PROPOSED]`

```
ADMISSION (host, pre-diff)
  resolve_task_obligations(recommendation, task, effective_surface, committed_path_probe)
      -> ObligationSet A     (committed contract + architect prediction + probe)
      -> derived_label(A)    -> provider budget, argv, receipt

INTEGRATION (host, post-diff)
  resolve_integration_obligations(A, execution_receipt, crew_result)
      -> A | D               (D keyed on final_actual_changed_paths,
                              pipeline_generated_paths, and the two Snapshots)
```

Three rules make this safe:

1. **Add-only.** The resolver type has no cancel, no precedence, no subtraction. `D` can only add. This is where the model gets the safety property that `_TIER_RANK` gives the ordinal for free.
2. **No diff fact may remove an admission obligation.** Otherwise the writer influences its own review requirements — a self-certification channel. The Implementer chooses the diff; it must not be able to choose the review.
3. **Every obligation carries the evidence key the artifacts already use** — `(test_platform, test_filter, commit)` for Unity (`downstream_pipeline.py:628-639`), `(source_head, source_tree, task_contract_sha256)` for the locality audit, candidate SHA for the crew. Escalation then answers "what stayed valid?" mechanically instead of by hand.

### 7.3 The blocker: escalation is currently hard-refused

Raising the tier mid-flight is not merely unimplemented — it is rejected by three separate identity checks:

| Refusal | Line | What it rejects |
| --- | --- | --- |
| Retry provider mismatch | `run_crew.py:1655` | a retry whose provider differs from the prior run identity |
| Retry model mismatch | `run_crew.py:1660` | a retry whose model differs |
| Retry effort mismatch | `run_crew.py:1665` | a retry whose reasoning effort differs |
| Pooled lease model/effort mismatch | `run_crew.py:1374/1376` | reusing a warm role session at a new budget |

`IMPLEMENTATION_SEQUENCE.md:73-76` states the intent plainly: "One route is resolved after deterministic START admission and is held through the work." `[REPRODUCED]`

**Proposed resolution — separate the two things these checks conflate.** They exist to prevent *silent* substitution of a cheaper or different provider, which is a real and important protection. They should reject a *downgrade or lateral change*, not an *authorized escalation*. Concretely:

- Give the retry an explicit `escalation_token` carrying `{prior_run_id, prior_route, new_route, triggering_obligations, authorizing_transition}`.
- Permit the retry when the new route is **≥** the prior route on every budget dimension (turn cap, effort index, capability class) and the token names at least one newly-triggered obligation. Reject on any decrease, exactly as today.
- Treat pooled leases as **retired on escalation**: a lease's identity includes model and effort by design (`session_pool.py:145-149`), so an escalated role gets a fresh session. That is correct, not a bug — but it should be a *deliberate retirement with a recorded reason*, not an unexplained refusal. See §11.

### 7.4 Escalation triggers, and what each one costs

| Trigger (post-diff) | Adds | Cost |
| --- | --- | --- |
| `final_actual_changed_paths` ⊄ (predicted ∪ generated) | re-run Contract Locality Auditor against the **actual** diff | 1 provider call (~39K tokens) |
| Actual diff contains a `_FULL_RIGOR_SUFFIXES` non-generated path | serialized-diff summary attached to receipt; block handoff | deterministic, 0 provider calls |
| `_DOOR_PROTOTYPE_BUILDER` in the actual diff | scene rebuild + normalization | 1 Unity batchmode launch |
| Delete/rename under `Assets/`, or edit of an existing serialized asset | human data-loss acknowledgement | 0 tokens, human latency |
| Bound filter exists and its manifest commit ≠ candidate commit | re-run that exact `(platform, filter)` | 1 Unity launch |

Note that **three of five are deterministic and cost no provider tokens**. The ordinal model has no vocabulary for a zero-provider obligation: all three of its settings spend tokens. That is precisely why the only available fix for the `.cs.meta` case was to *delete* the escalation rather than to replace it with a cheap check.

---

## 8. Crew-role matrix

### 8.1 Today

| Role | Line | Conditional? | Gate behavior |
| --- | --- | --- | --- |
| `contract_locality_auditor` | `:2120` | No | **Hard gate** — non-empty `audit_scope` ⇒ `crew_status='rejected'` at `:2136`; clone, implementer, test author and validator never run |
| `implementer` | `:2171` | No | writes; per-attempt changed-path validation at `:2171-2187` |
| `test_author` | `:2193` | No | writes tests; scope validation at `:2202-2216` |
| `validator` | `:2233` | No | sole input to the attempt-2 repair cycle (`for attempt in (1,2)`, `:2166`) |

All four run at every tier. `[REPRODUCED]`

### 8.2 Proposed — and the honest answer about "lean"

The brief's key constraint is that **a lean crew must not automatically mean fewer required tests.** The evidence forces a stronger version of that: *today, lean is essentially unreachable, and saying otherwise would be the third instance of an inert profile.*

| Role | May be omitted? | Only when | Reachable today |
| --- | --- | --- | --- |
| Contract Locality Auditor | **Never** | — | — |
| Implementer | **Never** | — | — |
| Test Author | Yes | `validation_plan_for(...)` binds the task — i.e. the test is *executed from committed policy* rather than designed | **2 of 60** contracts |
| Validator | Yes | all of: bound filter exists **and** passed at the candidate commit; actual diff ⊆ predicted surface; no judgment-lexicon hit; no serialized asset in the diff | **≤ 2 of 60** |

So the correct near-term statement is: **`fast` saves provider *budget*, not crew roles.** Crew savings become real only as `authoritative_validation_policy.json` grows. Anyone who wants a genuinely lean crew must first commit bound filters — the cost lever and the safety lever are the same lever, which is a good property and should be stated as one.

The judge's warning applies directly here: **do not answer "which role gets dropped" with "the Contract Locality Auditor" by default.** It is the largest prompt (~39K tokens, `[LOG-DERIVED]`) and therefore the tempting answer, and it is also the only role that reads the contract independently of the implementation plan, and it is a hard gate. Dropping it converts a blocking safety review into a silent skip.

### 8.3 Role-level budget, once the collapse at `run_crew.py:522` is fixed

| Role | Committed class | `BUDGET-IMPL-HIGH` fires |
| --- | --- | --- |
| `contract_locality_auditor` | `high_reasoning` | unchanged |
| `implementer` | `standard` | → `high_reasoning` |
| `test_author` | `low_cost` | unchanged |
| `validator` | `high_reasoning` | unchanged |

Also unset today: `Budgets(...)` at `run_crew.py:1972` leaves `token_limit=None`, so per-role spend is bounded only by 32 turns and 1200 seconds. A per-role token ceiling is a prerequisite for any credible cost claim (§13).

### 8.4 Crew obligations that are not roles

| Obligation | Trigger | Cost |
| --- | --- | --- |
| Validator as a **fresh** session rather than a continuation of the Implementer conversation | `shared_systems` or `symbols_or_components` non-empty, or any path outside `assets/` | same call, different session — this is the group that finally consumes the value discarded at `:288` |
| Auditor re-run against the **actual** diff | §7.4 surface drift | 1 call |
| Attempt-2 repair cycle | validator returned blocking issues | ~110K input tokens `[LOG-DERIVED]` |

---

## 9. Validation matrix

### 9.1 What actually decides Unity execution today `[REPRODUCED]`

Two independent mechanisms, neither of which reads the tier:

1. `validation_plan_for(root, task)` — exact `task_id` + 64-hex `task_contract_sha256` match against `authoritative_validation_policy.json`. Binds **NSC-020** and **NSC-042**. Returns `None` otherwise, and `candidate_integration.py:667-669` then returns `()` — zero pre-handoff Unity launches.
2. `_required_platforms(task)` — keyword scan of completion-gate prose. **Measured census over all 60 contracts: `(EditMode, PlayMode)` for 44, `(PlayMode,)` for 16, EditMode-alone for 0.** Exactly one contract (NSC-057) names Edit Mode in gate prose, and it names Play Mode too, so it still returns both. **EditMode is only ever selected by a keyword miss.**

`test_filter` is a required caller argument with **no default** (`downstream_pipeline.py:618`). Nothing constrains it to a filter that actually selects the new tests.

### 9.2 Proposed matrix `[PROPOSED]`

| Obligation | Trigger | Evidence key | Cost | Fails closed on |
| --- | --- | --- | --- | --- |
| `EV-COMMITTED-FILTERS` | `validation_plan_for(...) is not None` | `(platform, filter, commit)` | 1 Unity launch per platform | any platform not passed at the exact commit |
| `EV-NO-BOUND-FILTER-RECEIPT` | `validation_plan_for(...) is None` | — | 0 | receipt claiming validation ran |
| `EV-EMPTY-RUN-IS-FAILURE` | any manifest with `test_run.total == 0` | `(platform, filter, commit)` | 0 | **the measured 105.6 s / 0-test "passed" run** `[LOG-DERIVED]` |
| `EV-SERIALIZED-DIFF-REVIEW` | actual diff has a `_FULL_RIGOR_SUFFIXES` path not in `pipeline_generated_paths` | candidate SHA | deterministic | missing summary |
| `EV-SCENE-REBUILD` | `_DOOR_PROTOTYPE_BUILDER` in actual diff | candidate SHA | 1 Unity launch | rebuilt scene ≠ candidate scene |
| `EV-AUTHORED-FILTER-RECORDED` | `CREW-TESTS` fired | authored filter string | 0 | Test Author ran but recorded no filter |

**Deliberately dropped** (judge's correction, which I accept): a byte-comparison group over pipeline-generated `.cs.meta` sidecars. `preflight_role_paths` already refuses any *new* role path ending in `.meta` (`run_crew.py:700`) and requires generated sidecars absent from the captured tree (`:722-725`); the bytes are written by the pipeline from `unity_meta_bytes` (`:638-641`). Comparing bytes the pipeline just wrote proves nothing. The real exposure is an **edit to an existing `.meta`**, which the `kind == "existing"` branch at `:696-699` permits with no `.meta` exclusion — that is covered by `EV-SERIALIZED-DIFF-REVIEW`.

### 9.3 The two costs no rigor change touches

Stated explicitly because they are larger than the tier question and need their own owner:

- `_required_platforms` obligates **44 of 60 tasks** to two Unity boots on a prose keyword miss. The fix is an explicit `required_test_platforms` field on the completion-gate schema, failing closed to both only when genuinely absent.
- `test_filter` is an unconstrained caller string. An LLM-chosen filter can satisfy a regression obligation while selecting nothing — the 0-test "passed" run is the existing proof this is not hypothetical.

Neither is fixed by anything in §4–§8. If nobody owns them, this whole effort optimizes the smaller term.

---


## 10. Human-verification rules

### 10.1 Current state `[REPRODUCED]`

`human_policy = "required"` is a **hard-coded literal** at `execution_routing.py:385`, with an in-code comment stating that `machine_evidence_permitted` is unreachable. The documented exception in `TASK_RIGOR_PROFILES.md:106` is conditioned on "the effective tier is `fast`".

This is the one axis that is currently safe, and it is safe **precisely because it was removed from the scale**. That is a tacit admission in the code that an axis becomes trustworthy once it stops being a function of the tier. Keep the pin.

### 10.2 Why "fast ⇒ machine evidence may suffice" is the wrong predicate

`fast` is computed at `:339-351` from path count and file suffix. It is a **size** proxy. Whether a change needs eyes is a **judgment** question, and the two are independent:

- NSC-042-shaped: a one-constant diff whose AC-001 requires a wall to read as continuous at the gameplay camera. Small, and unverifiable without looking.
- A 12-file mechanical rename: large, and fully provable by compilation plus a passing filter.

Under the current rule, smallness is the thing that would authorize skipping the human. That is backwards.

### 10.3 Proposed rules `[PROPOSED]`

| Rule | Statement |
| --- | --- |
| H1 | `HUMAN-DEFAULT` is unconditional and is a floor member of the human axis. No group on any other axis — crew, budget, evidence — may remove it. Passing tests never waive it. |
| H2 | `HUMAN-VISUAL-JUDGMENT` fires when any committed `acceptance_criteria[].requirement` or `completion_gates[].requirement` matches the committed judgment lexicon. **Matches 13 of 60 contracts today.** `[REPRODUCED]` It emits a per-criterion observation checklist into the Issue naming each matched `AC-###`/`VAL-###`, and marks the run **permanently ineligible** for any machine-evidence exception regardless of surface size or derived label. |
| H3 | `HUMAN-MIGRATION` fires at integration time on any `Assets/` delete or rename, or any edit (not add) of an existing `.asset`/`.prefab`/`.unity`. Requires an explicit named data-loss acknowledgement before merge-closeout. |
| H4 | The lexicon is a **fail-closed fallback that escalates only**. It must be backed by an explicit contract field (`requires_human_observation: true`) as the primary signal; the lexicon exists to catch contracts written before that field. It may never de-escalate, and a lexicon miss never authorizes anything. |
| H5 | Any future machine-evidence exception must key on an **explicit contract assertion** that the acceptance criteria are fully machine-decidable — never on tier, never on diff size, never on a passing test count. |

**Rule H4 is a deliberate self-criticism.** §9.3 criticises `_required_platforms` for keyword-matching prose. H2 does the same thing. The difference that makes it acceptable is direction: `_required_platforms` uses keywords to *narrow* an obligation (a miss silently produces both platforms, which happens to fail safe, but a hit *removes* EditMode), whereas H2 uses them only to *add* one. A keyword rule that can only escalate is safe under misclassification; one that can de-escalate is not. If that distinction is not maintained, H2 becomes the same defect.

### 10.4 What "human verification" must actually mean in the receipt

Today a run can reach handoff with `validation_profile: full_relevant` in the event and zero Unity launches behind it. The human is then reviewing a candidate whose receipt overstates its own evidence. The rule that fixes this is not about rigor at all:

> **The receipt must state what did not happen.** `automated_evidence: none_bound` is more useful to a reviewer than `full_relevant`, because it tells them what they personally have to check.

---

## 11. Pooling and context-retirement rules

### 11.1 Current state `[REPRODUCED]`

| Fact | Location |
| --- | --- |
| Reservation always loops all four roles | `execution_session_pool.py:367` |
| `POOL_CAPACITY = 40` | `execution_session_pool.py:39` |
| Lease bundle must carry exactly the four `ROLE_CAPABILITY_CLASSES` roles or `CrewBlocked` | `run_crew.py:1253-1254` |
| Lease identity includes model and reasoning effort | `run_crew.py:1374/1376`, `session_pool.py:145-149` |
| Pooling is gated on `provider == "claude"` | `execution_bridge.py:384` |
| `prepare()` can select a probation record without checking `is_retry_offerable_at` (`session_pool.py:917`), and the call it then makes expires that record — a permanent denial | `session_pool.py:1152` context |
| `execution_bridge.py:429-435` re-raises without quarantining; `expire_idle` ignores `active` leases | — |

### 11.2 Consequences

- **G11**: a lean run reserves the same four conversations a full run does. Any crew-composition obligation that does not also change the reservation saves nothing in pool pressure.
- **G14**: a lease stranded by a container crash is never reclaimed. After enough crashes the pool deadlocks against capacity 40. This is a **liveness bug independent of the rigor question** and should be fixed on its own schedule.
- **G15**: Codex pooling is structurally unreachable — the provider gate, a hardcoded `claude-code` in `prepare()`, and `codex_resume_sandbox_argument` with no CLI plumbing. Any cost model that assumes provider-neutral pooling is wrong today.

### 11.3 Proposed rules `[PROPOSED]`

| Rule | Statement |
| --- | --- |
| P1 | Reservation breadth is a function of the resolved **crew obligation set**, not a constant. The bundle validator accepts the reserved subset and records which roles were deliberately not reserved. |
| P2 | Escalation **retires** the affected role's lease rather than refusing the retry. A lease's identity legitimately includes model and effort; the correct behavior on an authorized budget increase is a fresh session with a recorded `retirement_reason: escalation`, not a `CrewBlocked`. |
| P3 | Escalation retires **only the roles whose budget actually changed.** Today a tier bump changes the run identity and therefore invalidates every pooled role. Under `BUDGET-IMPL-HIGH`, only the Implementer's class moves; the Test Author's warm conversation should survive. |
| P4 | Context retirement is **explicit and auditable**: every retirement records `(role, prior_identity, new_identity, triggering_obligation, run_id)`. A silently dropped warm session is indistinguishable from a bug today. |
| P5 | Stranded leases are reclaimed. `expire_idle` must consider `active` leases whose owning run has terminated, and the bridge must quarantine on the failure path at `:429-435`. Fix before any change that increases pool churn — and escalation-driven retirement *is* such a change. |
| P6 | Any obligation-driven caching (§3.4: the Contract Locality Auditor cached across a human-review retry on `(task_contract_sha256, source_head, source_tree, work-graph hash)`) must key on facts that a retry cannot change. The auditor prompt contains no diff, which is why this cache is sound. |

---

## 12. Adversarial analysis

This section attacks the **proposed** design, not the current one.

### 12.1 Self-certification through the diff

**Attack.** Post-diff obligations are computed from `final_actual_changed_paths`, which the Implementer chooses. An Implementer that wants a cheaper review shapes its diff to avoid triggers — e.g. touching a serialized asset in a way that avoids the suffix predicate, or staying inside the predicted surface to avoid the reconcile trigger.

**Defence.** (a) Diff-keyed obligations are strictly **add-only**; staying inside the predicted surface only avoids *additional* review, it never removes an admission obligation. (b) The surface itself came from the architect, in a different process, before the Implementer existed. (c) The changed-path scope check at `run_crew.py:2171-2187` is deterministic and already blocks writes outside the approved boundary. **Residual risk:** an Implementer can still choose *not* to touch a file it should have touched. No obligation model detects an omission; only the Auditor and the human do. This is unchanged from today and must not be claimed as a new protection.

### 12.2 The registration hazard — the model's own worst failure mode

**Attack.** Under the ordinal, monotonicity is structural: `raise_floor` can only move `minimum` up `_TIER_RANK`. Under the derived label, it depends on `DEEP_MARKERS`/`STANDARD_MARKERS` **membership**. Add a group, forget to register its marker, and the derived label silently drops while the obligation set is unchanged — a receipt that under-reports its own rigor.

**Defence.** Make registration impossible to forget by construction: each group **declares its own marker as a field on the group record**, so there is no separate registration step. The enumeration test then asserts every registered group is reachable. This is the single most important structural detail in the proposal, and it is the one the composite proposal named against itself.

### 12.3 Lexicon brittleness

**Attack.** §9.3 criticises `_required_platforms` for keyword-matching prose; H2 and any migration lexicon do the same.

**Defence.** Direction-of-effect, per §10.3 H4: escalate-only keyword rules are safe under misclassification. Plus an explicit contract field as the primary signal. **Residual risk:** a contract whose visual requirement is phrased outside the lexicon gets no visual checklist. Mitigated only partly by H1 (the unconditional human gate still applies) — the checklist is lost, not the human.

### 12.4 Combinatorial blow-up of the proof

**Attack.** The ordinal's "never weaker" proof is two lines. The obligation model's is an enumeration over a cross-product.

**Defence.** The space is finite and small: `execution_scope` ∈ 2 × `decomposition_state` ∈ 2 × `path_patterns` ∈ 2 × `shared_systems` ∈ 2 × serialized ∈ 3 × exact-path root ∈ ~6 × suffix ∈ ~8 × path count ∈ 2 × architect tier ∈ 3 ≈ **10³ vectors**. That is a single `for` loop, not a formal method. **But this defence is only valid while the space stays small.** Every new signal multiplies it. The proposal must therefore cap the admission signal set, and any signal added later must come with its dimension explicitly added to the enumeration.

### 12.5 The "another inert string" attack — the strongest one

**Attack.** This repository has already done this twice. `ROLE_CAPABILITY_CLASSES` is an orthogonal per-role cost axis, threaded into pooled-lease compatibility identity, then short-circuited to one model string at `run_crew.py:522`. `crew_profile`/`validation_profile` are the second instance. A five-axis obligation table is a much larger surface on which to repeat the same decay, and the repository root's 35+ loose patch-named directories are a visible record of policy accreted and never folded back.

**Defence.** The `receipt_only: true` marker, and the rule that a group may lose it **only in the same change that adds its argv flag and its enforcement site**, enforced by a test. This does not prevent the decay; it makes the decay *visible in the receipt* rather than silent. That is a weaker guarantee than I would like, and it should be stated as such.

### 12.6 Escalation as a denial-of-service

**Attack.** Post-diff escalation adds provider calls after the expensive work is done. A task that repeatedly drifts its surface could re-trigger the Auditor on every attempt.

**Defence.** Escalation obligations are keyed on evidence keys; a re-run against an unchanged `(source_head, source_tree, contract_sha)` is served from cache. Bound the reconcile obligation to at most one re-audit per candidate SHA and treat a second drift as a **blocking** condition requiring human review rather than another provider call.

### 12.7 What would make me abandon the proposal

- If `authoritative_validation_policy.json` grows to bind most of the catalog, the evidence axis becomes tier-reachable, `validation_profile` stops being inert, and the ordinal becomes considerably more defensible.
- If the operator's live environment does set `NSC_ROUTE_*` per-tier models, the budget axis is materially expensive, the "Phase 1 is receipt honesty, not savings" framing is wrong, and the cost analysis must be redone.
- If real advisory records show the architect routinely returning `deep`, the max is doing more work than measured and the floor is less load-bearing than it appears. Conversely, if the architect **always** returns `fast`, the entire recommendation-versus-floor apparatus is over-built and a plain deterministic policy with no architect tier at all is the simpler answer.
- If the Phase 0 `_resource_paths` fix pushes the catalog to 46/60 `deep` and operators find that acceptable, the over-escalation half of the case evaporates and only receipt honesty survives — a much smaller mandate than a resolver rewrite.

---

## 13. Performance and token model

All figures `[LOG-DERIVED]` from named artifacts unless marked otherwise.

### 13.1 Measured crew cost, and what dropping roles would save

| Run | Total | Auditor + Validator share |
| --- | --- | --- |
| `nsc-042-20260902t093313z` | 5.3M tokens / $3.80 | **1,648,816 tokens / $1.406 — 31% of tokens, 37% of cost** |
| `nsc-020-20260828t091925z` | 1.47M tokens / $2.25 | **778,768 tokens / $1.192 — 53% of tokens** |

Source: 222 per-role usage records at `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\PipelineUsage\`.

**This is the headline number, and §8.2 is the reason it is not yet bankable.** Both roles are droppable only for the ~2 tasks with bound filters. The measured saving is what a *correct* lean profile would be worth once bound filters exist — not what is available today.

### 13.2 Prompt composition — the tier-independent win

| Item | Size | Share |
| --- | --- | --- |
| GDD, embedded in **all four** role prompts | 81,662 chars × 4 = **326,648** | **74% of ~442K fixed prompt chars per attempt** |
| Contract Locality Auditor prompt (largest single) | 156,410 chars ≈ 39K tokens | — |
| …of which dependent contracts | 40,767 chars | 26% of that prompt |
| Attempt-2 repair cycle | ~110K additional input tokens | — |

The GDD is already listed in `context_paths` and every role has read capability. Removing three of the four inline copies is a **tier-independent** reduction available at every tier, larger than most tier deltas, and it changes no safety property. It is the highest ratio of saving to risk in this entire review.

### 13.3 Host-side latency

| Item | Measured | Note |
| --- | --- | --- |
| Routing observation duplicated by turn 1 | **33.891 s** removable | Not the ~70 s previously assumed — corrected by verification |
| `taskcontrol validate` | 405 git subprocesses, 14.4 s per turn | pure function of the HEAD tree; memoisable |
| `taskcontrol states` bulk observation | 60–90 s | ~150× the cost of `validate` |
| Two full `gh api --paginate` listings per observation | ~15 s/turn | one listing can feed both consumers |
| PlayMode launch that executed **0 tests** and reported "passed" | 105.6 s | `test_run.total=0`, `testcasecount="0"` — G13 |

### 13.4 Supervisor economics

20,989 input vs 533 output tokens per decision — a **39:1 ratio**. 75 of 173 decisions carry no `provider_usage` at all, so any total is a lower bound. `[LOG-DERIVED]`

This is why `--max-turns` is a weak lever: it caps a loop (`for turn in range(1, max_turns+1)` with early terminal return, backstopped by a 12-turn no-progress cutoff), so a run that finishes early bills nothing extra for a higher ceiling. Raising fast→deep buys 80 extra turns that are usually never spent, and the reasoning-effort change is the part that actually bills.

### 13.5 Scale context

ArchitectureReview alone accounts for **70.6M tokens / $20.73** of a **89.6M / $38.93** total across the retained artifacts. The rigor tier governs a minority of total spend. This does not make the work pointless — correctness, not cost, is the primary justification — but it should prevent the tier from being sold as the main cost lever.

### 13.6 Artifact inventory backing these numbers

- 27 scheduler journals under `C:\NSC\NSC\.task-review-agent\outputs`
- 222 per-role usage records under `...\Downloads\NoSafeCircleOutput\PipelineUsage\`
- **No scheduler `events.jsonl` exists in any readable location.** `[UNCERTAIN]` Several claims that would benefit from event-level timing could not be checked.

---


## 14. Proposed durable schema / API changes

All `[PROPOSED]`.

### 14.1 `execution_routing.py`

```python
@dataclass(frozen=True)
class ObligationGroup:
    name: str                  # "CREW-TESTS"
    axis: str                  # identity | crew | budget | evidence | human
    marker: str | None         # "deep" | "standard" | None -- DECLARED ON THE GROUP,
                               # so label registration cannot be forgotten (§12.2)
    requested_turns: int | None
    requested_effort: str | None
    receipt_only: bool         # True until an argv flag AND an enforcement site exist
    evidence_key: tuple[str, ...]

@dataclass(frozen=True)
class ObligationSet:
    groups: frozenset[str]
    reasons: tuple[tuple[str, str], ...]      # (group, why) -- deterministic order
    resolved_turns: int
    resolved_effort: str
    role_capability_classes: Mapping[str, str]
    derived_tier: str                          # projection, never an input

def resolve_task_obligations(recommendation, *, task, predicted_change_surface,
                             committed_path_probe) -> ObligationSet: ...

def resolve_integration_obligations(admission: ObligationSet, *, execution,
                                    crew_result) -> ObligationSet: ...   # add-only
```

`TaskRigorDecision` is retained and gains `obligations`. `capability_tier` becomes `derive_label(obligation_set)`. `TierExecutionRoutingPolicy.for_tier` is fed `derived_tier` and stays byte-identical.

**Breaking-change fix required first:** `resolve_execution_route(..., rigor: TaskRigorDecision | None = None)` at `:588` must lose the `None` default (G3). A fail-open default on the function that applies the repository's deterministic minimum is the wrong direction, and it becomes materially more dangerous once the minimum carries five axes instead of one.

### 14.2 The committed obligation table

A new committed JSON/YAML document — `Pipeline/TaskReviewAgent/task_obligation_policy.json` — holding an **ordered** list of `(group_name, axis, marker, predicate_id, discharge_action, evidence_key, receipt_only)`. Predicates are named identifiers resolved to functions in code; the table does not carry executable expressions. Ordering is fixed so the reason list is deterministic.

### 14.3 Route-event schema

`worker_launched` gains:

```json
"obligations": ["ID-CORE", "CREW-AUDIT", "..."],
"obligation_reasons": [["CREW-TESTS", "no committed filter binds NSC-051"]],
"receipt_only_groups": ["CREW-TESTS", "BUDGET-IMPL-HIGH"],
"automated_evidence": "none_bound",
"derived_tier": "fast"
```

`crew_profile` and `validation_profile` remain, as **projections** of the obligation set rather than dict lookups, so existing readers keep working. Version the event.

### 14.4 Contract schema

| Field | Purpose | Replaces |
| --- | --- | --- |
| `required_test_platforms: ["EditMode"\|"PlayMode"]` | explicit, fails closed to both only when genuinely absent | the prose keyword scan at `downstream_pipeline.py:191-202` — **44 of 60 contracts currently default to both** `[REPRODUCED]` |
| `requires_human_observation: bool` | primary signal for H2 | the judgment lexicon, which becomes a fail-closed fallback |
| `exclusive_resources` — no schema change, but **all** prefixes must be consumed | `unity-scene:` and `logical:` currently dropped | `_resource_paths` at `:241-249` — **46 of 95 resources across 35 tasks** `[REPRODUCED]` |

### 14.5 `authoritative_validation_policy.json`

- Add the `decomposition_child_templates` key the reader already requires (G12) — `decomposition_validation_policy_for` at `downstream_resilience.py:322-330` raises without it.
- Add a promotion path: a filter authored by the Test Author and recorded in `crew_result.json` becomes a candidate for binding, so the 58-of-60 unbound population can shrink over time.

### 14.6 Boundary plumbing (the five hops)

| Boundary | File | Change |
| --- | --- | --- |
| 1 | `polling_orchestrator.py:1560-1566` | emit `--crew-roles`, `--role-capability-classes`, `--obligations` |
| 2 | `host_worker_launcher.py:31-53, :60-124` | parse and forward |
| 3 | `Start-GameTaskAgent.ps1` | forward |
| 4 | `run_pipeline_agent.py` → `execution_bridge.py` | forward to compose |
| 5 | `run_crew.py:1253-1254, :519-522, :2120-2233` | honour the role set; stop collapsing capability classes to one model |

Nothing before boundary 5 changes behavior. That is what makes Phase 1 provably a no-op.

---

## 15. Staged implementation plan

### Phase 0 — shape-independent bug fixes, measured before and after

Nothing in Phase 0 depends on the ordinal-vs-obligation decision, and calibrating any obligation table before it lands calibrates against the wrong population.

| # | Fix | Gap |
| --- | --- | --- |
| 0.1 | `_resource_paths` harvests `unity-scene:` and `logical:` | G4 — **moves the census from 29 deep to 46 deep** `[REPRODUCED]` |
| 0.2 | Feed `effective_surface`, not `advisory.predicted_change_surface`, to `resolve_task_rigor` | G2 |
| 0.3 | Remove the `None` default on `resolve_execution_route(rigor=...)` | G3 |
| 0.4 | Consume `symbols_or_components`; pass `advisory.confidence` | G5 |
| 0.5 | Fix the `.github/` dead branch (`lstrip('./')`) | G5 |
| 0.6 | Case-insensitive path dedupe | G8 |
| 0.7 | Classify extensionless paths explicitly | G7 |
| 0.8 | `.meta` out of `_FAST_SURFACE_SUFFIXES`; companion rule owns it | G6 |
| 0.9 | `override_reasons` records only reasons that actually raised the effective tier above the architect's request | G16 |
| 0.10 | Empty Unity test run fails closed | G13 |
| 0.11 | Add `decomposition_child_templates` to the policy file | G12 |
| 0.12 | Pool: reclaim stranded leases; quarantine on the bridge failure path; fix the probation permanent-denial | G14 |

**Exit criterion:** re-run the 60-contract census and publish the new distribution. If operators accept 46/60 at `xhigh`, the over-escalation argument weakens materially and Phase 2+ should be re-justified.

### Phase 1 — obligation set, derived label, honest receipt. **Provably a no-op on argv.**

Nine mechanical transcriptions of the `raise_floor` sites at `:304, 308, 310, 312, 317, 335, 337, 341, 349` into nine groups, each declaring its own marker. Budget reduction is a **maximum**, never an assignment. Receipt gains `obligations`, `obligation_reasons`, `automated_evidence`, `receipt_only_groups`.

**Immediate payoff is receipt honesty, not savings** — and it must be sold that way. `EV-NO-BOUND-FILTER-RECEIPT` exposes on day one that 58 of 60 tasks have no bound evidence, which the current `validation_profile: full_relevant` actively conceals.

**Acceptance:** `build_worker_command` output is byte-identical for all 60 contracts, before and after.

### Phase 2 — integration-time obligations

`resolve_integration_obligations` inside `CandidateIntegrator.integrate` (`candidate_integration.py:220`), where the receipt already exists. Adds surface-reconcile and serialized-diff review. Requires the §7.3 `escalation_token` and the §11 P2/P3 retirement rules.

### Phase 3 — prompt-context reduction (independent, do it in parallel)

Remove three of the four inline GDD copies; trim the Auditor's dependent-contract payload. **74% of fixed prompt bytes**, tier-independent, no safety property changed. `[LOG-DERIVED]`

### Phase 4 — crew composition and per-role budget actually enforced

The only phase needing new argv (§14.6). Until it lands, every `CREW-*` and `BUDGET-IMPL-HIGH` group ships `receipt_only: true`.

**Non-negotiable rule, carried forward from the judge's verdict:** a group may lose `receipt_only` **only in the same change that adds its argv flag and its enforcement site**, and a test asserts this. This is the specific guard against reproducing `crew_profile` — an axis recorded and never honoured — five times over.

### Phase 5 — the two costs this refactor does not touch

`required_test_platforms` on the completion-gate schema, and a constrained `test_filter`. **These need a named owner and a date.** If nobody owns them, this whole programme optimises the smaller term while the larger one stays broken.

### Explicitly out of scope until Stage 1 and 2 land

**Do not benchmark a trivial synthetic task for speed yet.** Today a `fast` task and a `deep` task run the same four provider roles and the same (usually zero) Unity validation; a benchmark now measures supervisor reasoning effort and host observation latency, not rigor.

---

## 16. Deterministic regression-test plan

### 16.1 The cross-product enumeration — the replacement for the free monotonicity proof

Must be red/green **before** any predicate is added beyond the nine mechanical transcriptions.

```
for s in product(
    execution_scope in {single_agent, other},
    decomposition_state in {concrete, other},
    path_patterns in {(), ("Assets/**",)},
    shared_systems in {(), ("fader",)},
    serialized in {none, companion, substantive},
    exact_path_root in {none, .github/, Packages/, Pipeline/, ProjectSettings/, AGENTS.md},
    suffix in {lean, .unity, .prefab, .asset, .meta, ...},
    path_count in {<=4, >4},
    architect_tier in {fast, standard, deep},
):
    assert derived_tier(s) == resolve_task_rigor(s).effective_capability_tier
    assert resolved_turns(s)        >= today_turns(s)
    assert effort_index(s)          >= today_effort_index(s)
```

≈10³ vectors. Lives beside the existing per-branch cases at `Pipeline/TaskReviewAgent/tests/execution_routing_smoke_test.py:540-910`.

### 16.2 Phase-1 no-op proof

Generate `build_worker_command` output (`polling_orchestrator.py:1538-1651`) for all 60 committed contracts before and after, and diff. **Any byte difference means the derived label is not a faithful projection and the change is not ready.**

### 16.3 Existing assertions that must keep passing unchanged

Measured on this checkout: `[REPRODUCED]`

| File | `capability_tier` | `crew_profile` | `validation_profile` |
| --- | --- | --- | --- |
| `execution_routing_smoke_test.py` | 32 | 8 | 5 |
| `polling_orchestrator_smoke_test.py` | 11 | 2 | 2 |
| `architect_preflight_smoke_test.py` | 6 | 0 | 0 |

**Correction to the judge's migration analysis:** it cited Gauntlet consumers at `scheduler_adapter.py:1511-1517` and `manifest.py`. At this commit the only Gauntlet reference is `Gauntlet/SoftwareArchitectAcceptance/scheduler_adapter.py:1514`, which **writes** a hardcoded `"capability_tier": "standard"` rather than reading one, and there is no `manifest.py` under `Pipeline/`. The conclusion — the Gauntlet is not a migration cost — holds, and for a stronger reason than stated. Confirmed independently: `capability_tier` appears in exactly **three** non-test modules (`architect_preflight.py`, `execution_routing.py`, `polling_orchestrator.py`), and `crew_profile`/`validation_profile` in exactly **one** (`execution_routing.py`).

### 16.4 New deterministic tests, per gap

| Test | Asserts | Fails before Phase 0 |
| --- | --- | --- |
| `unity-scene:`/`logical:` reach the floor | NSC-052 routes `deep`, not `fast` | yes |
| `effective_surface` reaches the resolver | a resumed task's actual paths change the tier | yes |
| `resolve_execution_route` requires `rigor` | `TypeError` without it | yes |
| `.github/workflows/x.yml` escalates | `deep` | yes |
| Case-variant paths dedupe to one | `Assets/A.cs` + `assets/a.cs` counts as 1 toward the 4-path bound | yes |
| `Makefile` does not escalate by empty suffix | `fast` | yes |
| Scene `.meta` declared only in `exact_paths` escalates | not `lean` | yes |
| `override_reasons` empty when nothing was overruled | with architect `deep` + `>4` paths | yes |
| Zero-test manifest is a failure | `total == 0` ⇒ not passed | yes |
| Decomposition policy resolution does not raise | `decomposition_child_templates` present | yes |
| Every registered group is reachable | no dead predicate | n/a |
| No group loses `receipt_only` without an argv flag and an enforcement site | grep-level structural test | n/a |

### 16.5 Failing-before / passing-after discipline

Every test above is specified as a defect reproduction first: it must be demonstrated **red at `6e91288`** and green only after its named Phase 0 fix. A test that passes before the fix is not evidence of the fix.

---

## 17. Uncertainties and decisions requiring Codex review

### 17.1 Facts I could not establish `[UNCERTAIN]`

| # | Unknown | Why it matters | How to settle |
| --- | --- | --- | --- |
| U1 | **Does the operator's live environment export `NSC_ROUTE_*`?** No occurrence exists in the repository, so all three tiers resolve to the same models — but `load_execution_routing_policy` reads `os.environ` when no mapping is supplied (`:706`). | If set, the tier genuinely selects different models, the budget axis is materially expensive, and the "receipt honesty, not savings" framing in §15 Phase 1 is **wrong**. | `Get-ChildItem Env:NSC_ROUTE_*` in the operator's real shell and in the compose stack. |
| U2 | **Is `max_turns` ever actually reached?** It is a ceiling with an early terminal return and a 12-turn no-progress cutoff. | If a real `deep` run consumes >40 turns on work a `fast` run finishes, the 40-vs-120 coupling costs real money and the budget axis matters more than credited. | Turn counts from real receipts. |
| U3 | **Does the architect ever return `standard` or `deep`?** The census holds it at `fast` and lets the floor do the work. | If it always returns `fast`, the entire recommendation-versus-floor apparatus is over-built and a plain deterministic policy with no architect tier is simpler. If it routinely returns `deep`, the max is doing more than measured. | Advisory records across recent runs. |
| U4 | **Is there an out-of-repository consumer of `crew_profile`/`validation_profile`?** None inside the repo. | If an operator dashboard or log pipeline parses them, converting them to projections is a breaking change requiring a versioned event. | Operator confirmation. |
| U5 | **No scheduler `events.jsonl` exists** in any readable location. | Several event-level timing claims could not be checked. | Confirm whether it is written at all. |
| U6 | **Defect rate of the 19 `fast`-routed tasks vs the 29 `deep` ones.** | If `fast` tasks show higher human-rejection rates, the ordinal is under-protecting in a way the obligation model — which preserves the same nine predicates by transcription — would *also* under-protect. The fix would then be new **signals**, not a new **shape**. | Issue history. |

### 17.2 Decisions that are not mine to make

| # | Decision | Options | My recommendation |
| --- | --- | --- | --- |
| D1 | **Adopt the hybrid, or fix the gap and keep the ordinal?** | (a) hybrid derived-label-over-obligations; (b) thread the existing profiles through and stop | (a), but **only after Phase 0 is measured**. Two independent adversarial passes converged on (a); the honest counter is that if operators accept 46/60 at `xhigh`, (b) is enough. |
| D2 | **Is 46 of 60 contracts at `xhigh` supervisor reasoning acceptable** once `unity-scene:` is honoured? | accept / re-tune the deep triggers / split budget from evidence | This is the single question whose answer most changes the plan. It is a cost-tolerance judgment, not an engineering one. |
| D3 | **Which crew role may a lean profile drop, and on what evidence?** | Test Author only when a bound filter exists (my answer) / Validator under stricter conditions / none | Test Author only, and note that this is reachable for **2 of 60** tasks today. **Do not answer "the Contract Locality Auditor" because it is the biggest prompt** — it is a hard gate and the only independent contract reader. |
| D4 | **Should escalation be permitted mid-flight at all**, against `IMPLEMENTATION_SEQUENCE.md:73-76` ("one route… held through the work")? | permit add-only escalation with a token / keep the freeze and block instead | Permit add-only escalation. But this is a deliberate reversal of a stated design principle and needs an explicit decision, not an implementation detail. |
| D5 | **Who owns `required_test_platforms` and the `test_filter` constraint?** | rigor workstream / a separate one | Separate owner, dated. These are larger than the tier question and no rigor change touches them. |
| D6 | **Is `human_verification_policy` ever allowed to become conditional?** | keep the hard pin / allow an explicit contract-asserted exception | **Keep the pin.** If it is ever relaxed, key it on an explicit contract assertion that the acceptance criteria are machine-decidable — never on tier, diff size, or a passing test count. |

### 17.3 The four decisions, kept separate — a closing check

The brief required that these never collapse into one. Restating where each is answered:

| Decision | Answered by | Never answered by |
| --- | --- | --- |
| Architect recommendation | the architect, additively, budget axis only | any floor; it can only raise |
| Deterministic minimum tier | committed contract facts + predicted surface, host-owned | architect prose |
| Post-implementation validation | the evidence axis: bound filters, actual-diff triggers, evidence keys | the tier label, crew size, or budget |
| Human verification | the human axis: unconditional floor + contract-asserted judgment needs | passing tests, small diffs, or a `fast` label |

**A lean crew does not mean fewer required tests** — §8.2 makes crew leanness *conditional on* a bound filter existing, so the cheaper crew is available only where the evidence is stronger. **Passing tests do not waive visual or experiential review** — §10.3 H1 makes the human floor unremovable by any other axis. **The architect cannot waive repository-owned safety policy with prose** — §4.1 makes its recommendation additive-only and confines it to one axis.

---

## 18. Checkout, SHA, working-tree status, report path

| Item | Value |
| --- | --- |
| Checkout | `C:\NSC\ClaudeRigorPolicy\NoSafeCircle` |
| Branch | `claude/rigor-policy-review` |
| Reviewed SHA | `6e9128848a471e0150a3287a9a33cf520914c003` |
| HEAD commit | "Preserve Codex session identity across failed turns", 2026-09-04 13:51:41 -0500 |
| Working-tree status | **CLEAN** - `git status --porcelain=v1 --untracked-files=all` returned no output |
| Report path | `C:\NSC\CLAUDE_RIGOR_PIPELINE_POLICY_REVIEW.md` (untracked, outside the checkout, **not committed**) |
| Source bundle | `C:\NSC\verified-core-6e912.bundle` |
| Prior Task 5 checkout, preserved | `C:\NSC\ClaudeRigorPolicy\NoSafeCircle-prior-970b370` |

Nothing was pushed. No branch was created or switched in `C:\NSC\NSC\NoSafeCircle` or `C:\NSC\Rehearsal\*`. No GitHub Issue, remote branch, container, or rehearsal artifact was touched. No global `safe.directory` exception was added; the clone was made from the bundle above.

### Provenance summary

| Tag | Meaning | Count of load-bearing claims |
| --- | --- | --- |
| `[REPRODUCED]` | derived from code at this commit by me or a grounded agent, or personally executed | the census (29/12/19 and 46/12/2), the 95/46/35 resource drop, the 44/16/0 platform split, 13/60 lexicon hits, nine `raise_floor` sites, the `NSC_ROUTE_*` absence, the test-assertion counts, and the single-file `crew_profile` consumer |
| `[LOG-DERIVED]` | from a named run artifact | all of section 13; artifacts named in 13.6 |
| `[PROPOSED]` | design, not implemented | all of sections 4-7, 9.2, 10.3, 11.3, 14, 15, 16 |
| `[UNCERTAIN]` | needs live validation or product judgment | U1-U6 in section 17.1 |

No proposed behavior is described anywhere in this document as implemented behavior.

