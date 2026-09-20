# D1B.2 bounded revision review: binding design contract

Published by the coordinating session on 2026-09-13 at about 19:45 UTC. It is the architect's read-only design (section 1 onward, reproduced verbatim), plus the coordinator's binding amendments below. Where an amendment and the design differ, the amendment wins. Astra's requirements are in `C:\nscrev\reports\astra-1165-revision-review-requirements.md`.

## Coordinator amendments (binding)

1. **D1C tests do not use the broken shared fixture.** `decomposition_authorization_smoke_test.py` and `local_decomposition_apply_test.py` fail at base before any authorization code runs: the shared TaskGraph `graph_delta_smoke_test` fixture violates the exact `exclusive_resources` partition rule from `379685b` (`DecompositionPolicyError` on `logical:new-shared`). The D1C developer must NOT add tests to those modules and must NOT repair or edit the shared fixture. Instead, add new self-contained test modules next to them (for example `decomposition_authorization_revision_review_smoke_test.py` and `local_decomposition_apply_revision_review_test.py`), whose graph-plan fixtures satisfy the exact partition rule. Prove at base that the two existing modules fail identically, and report any existing D1C coverage that is therefore unverified locally. Section E's D1C test-file line is superseded by this amendment.
2. **No developer edits documentation or CI.** Nobody edits `README.md`, anything under `Docs/`, or `.github/workflows/*`. Section E's "README counters section" and "one CI workflow line" for the producer move to the coordinator's merge commit. Each developer lists proposed documentation text and CI steps in their report.
3. **Sequencing without blocking.**
   - The producer commits **C0 first** on its branch: only the constants in `round_robin_decomposition.py` (text identical, literals replaced), plus new `Pipeline/TaskDecomposition/tests/revision_review_fixtures.py` and `revision_review_fixtures_smoke_test.py`. Keep in-progress P1 changes out of C0, for example by stashing that file's P1 hunks first. Announce the C0 SHA to the coordinator with `SendMessage` to `main`, then continue P1 on top of C0.
   - The D1C and AssistantControl developers start immediately from `ade5bca` in their own worktrees. When the coordinator relays the C0 SHA, they `git cherry-pick <C0>` onto their branch. C0 touches none of their files. Only then do they run tests that import the fixtures.
   - Author guidance is already committed as `13618d8ca80e19085c07f90cb3a0ae9c56627511` on `ade5bca`. The coordinator checked it against section E's frozen interface: no signature changes, and the asserted substrings are kept.
4. **Integration tests I1.** The AssistantControl developer does not start I1 until the coordinator relays the P1 and D commit SHAs. Then it cherry-picks C0, P1, D and G onto its branch and adds I1. The coordinator builds the final integration branch.
5. **Branches and worktrees.**

   | Developer | Worktree | Branch |
   |---|---|---|
   | Producer (P) | `C:\nscrev\revision-review-fix` | `throughput/decomposition-revision-review` |
   | D1C consumer (D) | `C:\nscrev\d1c-consumer-fix` | `throughput/decomposition-d1c-consumer` |
   | AssistantControl consumer (A) | `C:\nscrev\ac-consumer-fix` | `throughput/decomposition-ac-consumer` |
   | Author guidance (G) | `C:\nscrev\author-guidance-fix` | `throughput/decomposition-author-guidance` (`13618d8`) |
   | Integration (coordinator) | to be created | `throughput/decomposition-revision-review-integration` |

6. **Constraints for everyone.**
   - Nothing under `C:\NSC` is written, run, cleared or relaunched; reading retained evidence is allowed.
   - No Docker, providers, GitHub, push or merge.
   - CRLF files: never `sed -i`; verify with `git diff --check` and `git ls-files --eol`.
   - Test modules import helpers as module objects only.
   - Failing-before evidence comes from a detached worktree at `ade5bca` plus C0.
7. **Evidence already gathered.**
   - The producer reproduced the earlier draft's defect. With an author correction and then a round-2 revise, the draft made 4 provider calls, wrote 4 round records with counters 2/1/1, and published a `review_ready` proposal. The current producer makes 3 calls and ends `needs_human` with nothing published.
   - The producer also found that AssistantControl is the only default route to a two-call, non-pooled, cross-provider circuit. Explicit `--max-calls 2` polling-orchestrator runs are pooled and never qualify.
   - Accepted defaults from section G are kept, including G3, the clean-pass rule.

---

# Design contract: D1B.2 bounded revision review (NSC-1165)

**What this is.** A read-only design; I changed no files. It is based on commit `ade5bca`. It adopts the producer draft now uncommitted in `C:\nscrev\revision-review-fix`, with the deltas marked **[delta]**. The earlier consumer draft is superseded.

**Coordinator inputs.**
- **Call ceiling (adopted).** There are two separate rules:
  - **General rule**, for any `max_calls` from 2 to 12: at most `max_calls + 1` physical provider calls, and at most one bounded extra call. Four rounds are normal when `max_calls` is 4.
  - **Two-call rule**, for `max_calls == 2`: at most 3 provider calls and at most 3 round records.
  - The revision review exists only when `max_calls == 2`.
- **Producer draft choices (adopted).** One correction to the coordinator's wording:
  - If round 2 does not grant the review, the run ends exactly as it does today.
  - If a condition fails at call time, after the grant (the re-check, or the route identity), the run ends `rejected` with an internal-error reason and no call is made. That is what the draft code and its tests do. It is sound: a condition changing between grant and call is an internal inconsistency, not a human-review state.

---

## A. Behaviour

### A1. Grant (evaluated at the end of ordinary round 2)
The draft's `_revision_review_refusal(...)` must return `None`, and all of these must hold:

1. `max_calls == 2`.
2. Round 2 is an ordinary `decomposition_reviewer` round with `verdict == "revise"` and `status == "revised_candidate_valid"`.
3. Round 2 completed cleanly: `round_rejections == []`, run `rejection_reasons == []`, and the `AgentResult` succeeded.
4. The run is not pooled: `lease_bundle`, `pooled_sessions` and `independent_codex_roles` are all absent or false.
5. `author_corrections_used == 0` and `revision_reviews_used == 0`, both exact ints.
6. Exactly 2 physical calls have been made.
7. The latest candidate is `version == 2`, authored by the round-2 provider.
8. The reviewer `order[2 % len(order)]` is not the reviser.
9. The reviewer's pre-run-validated runtime identity is a string that differs from the reviser's `AgentResult.provider`.

If the grant is refused, the outcome is byte-identical to ade5bca: `needs_human` with the call-limit reason.

### A2. Call time (before round 3)
- The same predicate is re-checked before anything for round 3 is published.
- After the bundle is built:
  - The ceiling `provider_calls < max_calls + 1` is checked.
  - The route must still resolve to the validated identity and must not be the reviser's.
- Any failure: `rejected`, an internal-error reason, no provider call, `revision_reviews_used: 0`, no `rounds/03/` directory, no round record.
- A route refusal may already have left `rounds/03-request.json` and a `revision_review_started` event. **[documented, accepted]**

### A3. Performer and inputs
- **Provider:** `order[0]` in a two-provider order, ephemeral (no session binding), role `decomposition_reviewer`.
- **Prompt:** `build_decomposition_reviewer_prompt` with its **frozen ade5bca keyword set**: `round_number=3`, candidate v2, `review_history=[round-2 entry]`, the round-2 outstanding findings, `same_provider_separate_session_review=False`.
- **Schema, budget, validation:** `DECOMPOSITION_REVIEW_SCHEMA`, `reviewer_budgets()`, and `validate_decomposition_review(expected_candidate_sha256=v2.sha256, round_number=3, …)`.
- **Invocation id:** `_round_invocation_id(task_id, run_id, 3, "decomposition_reviewer")`, directory `rounds/03`.
- **Identity check:** the `AgentResult` must name that invocation id, the reviewer role, and the validated identity, and must not be the reviser's identity. Otherwise the review output is never read.

### A4. Round-3 outcomes
Every non-pass outcome leaves `independent_approver_provider` null.

| Round-3 result | Round `status` / `verdict` | `run_status` | `rejection_reasons` |
|---|---|---|---|
| valid `pass` | `independent_pass` / `pass` | `review_ready` (after the existing final Source, author and unresolved checks) | `[]` |
| valid `revise` | `revised_candidate_valid` / `revise`; v3 is adopted as `latest_candidate` | `needs_human` | `[REVISION_REVIEW_REVISED_AGAIN_REASON]` |
| valid `needs_human` (this is "reject"; there is no reject verdict) | `needs_human` / `needs_human` | `needs_human` | `[REVISION_REVIEW_STOPPED_REASON]` |
| provider exception, no result, failed `AgentResult`, or schema-invalid output | `rejected` | `agent_failed` | `"round 3 revision review: " + existing text` |
| identity mismatch, read-only violation, contract- or policy-invalid review or revision | `rejected` | `rejected` | `"round 3 revision review: " + text` |
| Source drift | `rejected` | `rejected` | `"round 3 revision review: source … during provider invocation"`, plus the unprefixed final reasons |

### A5. Exclusions and ceiling
- **Mutual exclusion.** The grant requires no author correction. The correction site also refuses if `revision_reviews_used != 0` or the ceiling is reached. A run with a correction whose round 2 revises ends `needs_human` with reasons `["round 1: initial candidate deterministic validation failed: …", CALL_LIMIT_AFTER_REVISION_REASON]`, after 3 calls.
- **Pooled runs** never grant the review. The outcome is unchanged from today, leases and settlement are untouched, and pool settlement still refuses `round_number > max_calls`.
- **Accounting.** At the end of every run: `provider_calls == calls_used + author_corrections_used + revision_reviews_used`, `author_corrections_used + revision_reviews_used <= 1`, and `provider_calls <= max_calls + 1`. Otherwise the run is `rejected` with `"internal error: provider calls do not equal calls_used plus the bounded extra calls"`.

---

## B. Data contract

### B1. Constants (exported from `round_robin_decomposition.py` in commit C0; literals replaced, text identical)
```python
REVISION_REVIEW_CALL_LIMIT = 2
REVISION_REVIEW_ROUND_NUMBER = 3
CALL_LIMIT_AFTER_REVISION_REASON = "call limit ended immediately after a revision; the latest author may not approve its own candidate"
REVISION_REVIEW_REVISED_AGAIN_REASON = "revision review did not approve the revised candidate: its reviewer revised it again, and the latest author may not approve its own candidate"
REVISION_REVIEW_STOPPED_REASON = "revision review did not approve the revised candidate: its reviewer stopped at a human authority boundary"
REVISION_REVIEW_REJECTION_PREFIX = "round 3 revision review: "
SOURCE_REVALIDATION_REASONS = frozenset({
    "source HEAD changed during provider invocation", "source tree changed during provider invocation",
    "source branch could not be revalidated", "source branch changed during provider invocation",
    "source working tree changed during provider invocation", "source identity could not be revalidated"})
```

**Producer-only internal texts.** These are the draft's f-strings; consumers never match them:
- `internal error: round {n} revision review refused before any call: {refusal}`
- `internal error: round {n} would exceed the {ceiling}-call provider ceiling; no call was made`
- `internal error: round {n} revision review provider route resolved to {x!r}, not the validated independent provider identity; no call was made`
- `internal error: round {n} correction would exceed the bounded provider calls; no call was made`
- The four `revision review result names …` / `revision review ran as …` identity texts.

**No new** statuses, verdicts, finding statuses, `human_next_step` strings, round-record keys or request-file keys are introduced.

**Progress events:**
- `revision_review_started`: `round_number`, `round_role`, `round_provider`, `revision_of_round`, `reviewed_candidate_version`, `reviewed_candidate_sha256`.
- `revision_review_completed`: `round_number`, `round_role`, `round_provider`, `revision_of_round`, `status`, `duration_seconds`.
- `run_completed` gains `revision_reviews_used`.

### B2. Round-3 record
It has exactly the ade5bca `_round_summary` key set (21 keys). Values for pass, revise and needs_human:

| Field | Value |
|---|---|
| `schema_version` | `"1.0"` |
| `round_number` | `3` (int) |
| `correction_of_round` | `null` |
| `role` | `"decomposition_reviewer"` |
| `requested_provider` | `order[0]` |
| `actual_provider` | `"claude-code"` or `"openai-codex"`; equals the runtime identity of `requested_provider`, and differs from round 2's `actual_provider` |
| `actual_model` | string |
| `agent_status` | `"succeeded"` |
| `agent_failure_classification` | `"none"` |
| `duration_seconds` | number |
| `candidate_before` | equals `rounds[1].candidate_after` (the v2 summary) |
| `candidate_after` | `null` for pass and needs_human; the v3 summary (author `order[0]`, `version` 3, `sha256` ≠ v2) for revise |
| `verdict` | `"pass"`, `"revise"` or `"needs_human"` |
| `new_finding_ids` | `[f.finding_id for f in finding_history[1].findings]`, each prefixed `round-03-` |
| `unresolved_finding_ids` | sorted outstanding ids after round 3 (`[]` for pass) |
| `task_execution_request_path` | `"rounds/03/task_execution/<INV3>/task_request.json"` |
| `agent_runtime_result_path` | `"rounds/03/agent_runtime/<INV3>/result.json"` |
| `status` | `"independent_pass"`, `"revised_candidate_valid"` or `"needs_human"` |
| `authority` | `"review_only_not_applied"` |
| `pooled_session` | `null` |
| `rejection_reasons` | `[]` |

### B3. Finding resolutions (existing representation, unchanged)
Resolutions live in three places:
- `rounds/03/review.json.prior_finding_resolutions`
- `rounds/03/review_history_entry.json`
- `finding_history[1].prior_finding_resolutions`

Each entry is `{finding_id, status ∈ {"resolved","withdrawn","still_blocking"}, explanation}`.

**Replay rule (normative for every consumer).** Start with `outstanding = {}` and `known = set()`. For each history entry `k`, in order:
1. `entry.round_number` equals the k-th reviewer round's `round_number`.
2. The resolution ids have no duplicates and their set is exactly `set(outstanding)`: nothing missing, nothing extra.
3. `resolved` and `withdrawn` remove the finding; `still_blocking` keeps it.
4. Each finding id matches `FINDING_ID_RE`, starts with `round-{n:02d}-`, is not in `known`, and is unique within the entry. Blocking findings are added to `outstanding`.
5. The round's `unresolved_finding_ids` equals `sorted(outstanding)`, and its `new_finding_ids` equals the entry's finding ids in order.
6. By verdict:
   - `pass`: `outstanding` is empty and this is the last entry.
   - `revise`: `outstanding` is not empty.
   - `needs_human`: `outstanding` is not empty and this is the last entry.
7. At the end:
   - `review_ready`: `outstanding` is empty.
   - `needs_human`: `unresolved_findings == [outstanding[i] for i in sorted(outstanding)]`.

### B4. Run level
A new key `revision_reviews_used` (exact int 0 or 1, always written) follows `author_corrections_used`. All counters are exact ints. Every row below has `max_calls: 2`, `review_independence: "cross_provider"` and `pooled_sessions: null` unless stated. Order is `[claude, codex]`.

| Outcome | status | calls / corr / rev | rounds / history | approver | latest | unresolved | reasons |
|---|---|---|---|---|---|---|---|
| Round-2 pass | review_ready | 2/0/0 | 2/1 | codex | v1 claude | [] | [] |
| Correction, then round-2 pass | review_ready | 2/1/0 | 3/1 | codex | v1 claude | [] | [] |
| **Round-3 pass** | review_ready | 2/0/1 | 3/2 | claude | v2 codex | [] | [] |
| **Round-3 revise** | needs_human | 2/0/1 | 3/2 | null | v3 claude | round-3 outstanding | [REVISED_AGAIN] |
| **Round-3 needs_human** | needs_human | 2/0/1 | 3/2 | null | v2 codex | round-3 outstanding | [STOPPED] |
| Round-3 provider failure | agent_failed | 2/0/1 | 3/1 | null | v2 | round-2 finding | ["round 3 revision review: …"] |
| Round-3 invalid output or Source drift | rejected | 2/0/1 | 3/1 or 2 | null | v2 | round-2 finding | ["round 3 revision review: …", …] |
| Correction, then round-2 revise | needs_human | 2/1/0 | 3/1 | null | v2 | round-2 finding | ["round 1: initial…", CALL_LIMIT] |
| Pooled or equal-identity round-2 revise | needs_human | 2/0/0 | 2/1 | null | v2 | round-2 finding | [CALL_LIMIT] |
| Call-time refusal | rejected | 2/0/0 | 2/1 | null | v2 | round-2 finding | ["internal error: …"] |

- `decomposition_result_path` and `graph_delta_path` are named only when `review_ready`.
- `human_next_step` is the existing text for each `run_status`.

### B5. Binding and re-verification

| Binding | Producer | D1C re-verifies | AssistantControl re-verifies |
|---|---|---|---|
| Candidate version and SHA | `rounds[2].candidate_before` equals `rounds[1].candidate_after` equals `latest_candidate`; `history[1].reviewed_candidate_sha256` equals v2 SHA; `validate_decomposition_review(expected_candidate_sha256=…)` | round chain, approving round, history binding, SHA recomputed from typed `DecompositionResult` | replay, digest of `decomposition_result.json`, structured output `reviewed_candidate_sha256`, `candidate_sha256` of round 2's `revised_decomposition` |
| Actual provider | pre-run validated route; post-call `AgentResult` identity | `actual_provider` equals runtime identity of the rotation provider; approver checks | replay, plus `result.json.provider` |
| Invocation | deterministic INV3 embedded in both paths | recomputed INV3 equals `record.reviewer_invocation_id` equals both path ids | recomputed id; files exist; `result.json.run_id`; `task_request.invocation.run_id` |
| Source | captured identity, revalidated after every call and at the end; drift means `rejected` | `record.source_head` equals run head; `review_ready` carries no rejection reasons | head and tree equal the record, branch equals the record **(new)**, ancestry with graph inputs unchanged, plan fresh |
| Findings | policy validator | `_blocking_findings_resolved` | B3 replay, plus structured-output equality |

---

## C. Consumer acceptance algorithms

### C1. D1C: `Pipeline/TaskReviewAgent/decomposition_authorization.py`
Classification precedence is unchanged. The ordered review checks in `_review_invalid_reasons`:

1. **Kept:** mode and schema; `authority`; `run_status`; empty `rejection_reasons`; empty `unresolved_findings`; latest-candidate summary; artifact names.
2. **Kept, one addition:** `_validated_provider_order`. `_independent_codex_roles` additionally requires `revision_reviews_used` to be absent or an exact int 0.
3. **Changed: `_call_accounting_valid`.** Existing int, limit and `2 <= calls_used <= max_calls` checks are kept. Then:
   - `rev` is 0 if absent; if present it must be an exact int in {0, 1}.
   - `corr` is 0 if absent; if present it must be an exact int 0. D1C authorizes no correction shape, as today.
   - If `rev == 1`: require `max_calls == 2`, `calls_used == 2`, and the `author_corrections_used` key present.
   - Require `len(rounds) == calls_used + rev` and `len(history) == calls_used - 1 + rev`.
   - Failure reason: `bounded_call_accounting_invalid`.
4. **Kept:** `_round_chain_invalid` (failure reason `round_sequence_inconsistent`).
5. **New, only when `rev == 1`:** `_revision_review_shape_invalid(run, rounds)`, failure reason `round_sequence_inconsistent`. It fails if any of these hold:
   - `review_independence != "cross_provider"`
   - `run.get("pooled_sessions") is not None`
   - any round lacks the `correction_of_round` key, or its value is non-null
   - any round has a non-null `pooled_session`
   - `rounds[2].round_number != 3`
   - `rounds[2].requested_provider == rounds[2].candidate_before.author_provider`
   - `rounds[2].actual_provider == rounds[1].actual_provider`
   - `rounds[1].candidate_after.version != 2`
   - `rounds[2].candidate_before != rounds[1].candidate_after`
6. **Kept:** approver vocabulary, author, and binding checks; approving-round checks, with the invocation id recomputed for that round's number (3); history-tail binding; `_blocking_findings_resolved`; evidence SHA; every artifact-mismatch, parent-chain and graph-plan check. No new reason codes are added.
7. **Frozen names:** `RUNTIME_PROVIDER_IDENTIFIERS`, `_independent_codex_roles`, `_validated_provider_order`.

### C2. D1C developer also owns: `local_decomposition_apply.py::_review_run_result`
After the independence check, add: if `revision_reviews_used` is present and is not an exact int 0, refuse with `"decomposition run result counts a revision review; pooled local application never carries one"`.

### C3. AssistantControl `_review_ready_proof`
`_authenticated_run_result` is unchanged. Messages marked (M*) are exact.

1. **Kept:** `calls_used == 2`, `run_status`, `decision`; empty unresolved findings and rejections.
2. **New:** `source_identity.branch != record["source_branch"]` → (M7) `Decomposition run used another source branch`.
3. **New:** `pooled_sessions is not None` → (M8) `Decomposition review carries pooled sessions`.
4. **Kept:** load the result and graph; parent check; digest.
5. **New counters:**
   - `revision_reviews_used` must be `None` or an exact int in {0, 1}, else (M1) `Decomposition review revision_reviews_used is {v!r}, not 0 or 1`.
   - If it is 1:
     - `author_corrections_used` must be `None` or an exact int in {0, 1}, else (M2) `Decomposition review author_corrections_used is {v!r}, not 0 or 1`.
     - If it equals 1: (M3) `Decomposition review counts both an author correction and a revision review`.
6. **Shape:**
   - If `rev == 1`, require `calls_used == 2`, `len(rounds) == 3` and `len(history) == 2`, else (M4) `Decomposition review counts a revision review its rounds do not carry`.
   - Otherwise the **existing S2/SC code path runs unchanged, with its messages**. A three-round run without the count still fails there with "does not prove exactly one bounded author correction".
7. **New full replay**, all shapes, → (M5) `Decomposition round history does not replay: {detail}`. With P0 and P1 as `record.providers`, the expected sequence of `(round_number, correction_of_round, role, requested_provider, status, verdict)` is:
   - S2: `(1,null,decomposer,P0,candidate_valid,null)`, `(2,null,reviewer,P1,independent_pass,pass)`
   - SC: `(1,null,decomposer,P0,rejected,null)`, `(1,1,decomposer,P0,correction_candidate_valid,null)`, `(2,null,reviewer,P1,independent_pass,pass)`
   - SR: `(1,…,P0,candidate_valid)`, `(2,null,reviewer,P1,revised_candidate_valid,revise)`, `(3,null,reviewer,P0,independent_pass,pass)`

   **Every round:**
   - Round numbers are exact ints.
   - `actual_provider == RUNTIME_PROVIDER_IDENTIFIERS[requested_provider]` (imported from D1C).
   - `agent_status == "succeeded"`, `authority` is the review-only marker, `pooled_session` is null.
   - `rejection_reasons == []`, except SC round 1, which holds exactly one string starting `initial candidate deterministic validation failed: `.
   - Author rounds have empty finding ids.
   - Candidate summaries are exact 5-key dicts with int `version`.

   **Candidate chain:**
   - The author publishes v1 authored by P0.
   - The SR reviser has `candidate_before == v1` and `candidate_after.version == 2`, authored by P1, with a different SHA.
   - The final round's `candidate_before == latest_candidate`, and its `candidate_after` is null.
   - `latest.sha256 == digest` and `latest.graph_delta_plan_id == plan.plan_id`.
   - `independent_approver_provider` equals the final `requested_provider`, and is not `latest.author_provider`.
   - For SR, `rounds[2].actual_provider != rounds[1].actual_provider`.

   **History:**
   - One entry per reviewer round, matched on round number, reviewer provider, reviewed SHA (equal to `candidate_before.sha256`) and verdict.
   - The B3 replay passes.
   - `history[-1].findings == []` (the existing clean-pass rule is kept).
8. **New artifact authentication**, every round, → (M6) `Decomposition round {n} invocation artifacts do not authenticate: {detail}`. The directory is `NN`, or `NN-correction` for a correction round. The expected id is `_round_invocation_id(task, run, n, role, correction=…)`; convert its preflight error to `ValueError`.
   - Both recorded paths must equal the exact producer paths, and both files must be regular files (use `_load_object`).
   - `result.json` must have `run_id` equal to the id, and `role`, `provider`, `model` equal to the round's values, with `status: "succeeded"`.
   - `task_request.json` must have `task_id`, and `task_contract_identity` equal to the run's `task_execution_contract_identity`. Its `invocation` must have `run_id` equal to the id, `role` equal to the round role, and `provider_configuration_key` equal to `f"{requested}-decomposition"`.
   - Reviewer rounds: `DecompositionReviewResult.from_dict(structured_output)` must match the history entry's verdict, summary, reviewed SHA, findings and resolutions. For revise rounds, `candidate_sha256(revised_decomposition)` must equal `candidate_after.sha256`.
9. **Kept:** plan freshness, parent semantic authorization, child allocation.
10. **Return:** existing keys, except `reviewer_provider` becomes the actual approver and `models` becomes `[model of the round that authored latest, approving model]`. New keys: `author_corrections_used` (int, `None` read as 0) and `revision_reviews_used` (int, `None` read as 0).

### C4. AssistantControl `_needs_human_proof` and `inspect`
1. **Kept:** status, artifacts null, `calls_used`, corrections 0 or 1.
2. **New:** revision count type → `Decomposition needs_human revision_reviews_used is {v!r}, not 0 or 1`.
3. **New:** both counters equal 1 → `Decomposition needs_human counts both an author correction and a revision review`.
4. **New, if `rev == 1`** → `Decomposition needs_human counts a revision review its rounds do not prove`. Required:
   - `calls_used == 2`; corrections present and exact int 0.
   - 3 rounds and 2 history entries; round numbers 1, 2, 3; every `correction_of_round` null; every `pooled_session` null.
   - Round 1: `candidate_valid`, v1 authored by P0.
   - Round 2: P1, `revised_candidate_valid` / `revise`, v1 to v2.
   - Round 3: P0, which is not `candidate_before.author`; `actual_provider` equals the runtime identity of P0; `rejection_reasons == []`; `candidate_before == v2`.
   - Then either:
     - `revised_candidate_valid` / `revise` with `candidate_after` v3 authored by P0, v3 equal to `latest_candidate`, and reasons `== [REVISED_AGAIN]`; or
     - `needs_human` / `needs_human` with `candidate_after` null, `latest == v2`, and reasons `== [STOPPED]`.
   - The B3 replay passes, ending with outstanding equal to `unresolved_findings`, which is not empty.
5. **New, if `rev` is `None` or 0:** any round with `round_number > max_calls` → `Decomposition needs_human carries a round beyond max_calls that no revision review count names`.
6. **Kept:** reasons are stated strings.
7. **New:** a reason whose text, after an optional `round N: `, `round N correction: ` or `round N revision review: ` prefix, is in `SOURCE_REVALIDATION_REASONS` → `Decomposition needs_human retains a Source-movement rejection`.
8. **Kept:** the remaining checks.
9. **Return:** facts gain `"revision_reviews_used"` with the raw value (`None` if absent). No on-disk artifact checks here: needs_human is never applied, and the retained evidence must stay inspectable.

**`inspect` compatibility.** If the retained `needs_human` lacks the key and the re-derived value is `None`, compare with that key removed and return the retained shape. Otherwise use exact equality, as today. This keeps the live `NSC-1165.decomposition.json` inspectable.

### C5. Replay and other readers
- **`decomposition_replay.py`: no change.** It reads only Issue events, `graph_delta.json` and `decomposition_result.json`, never counters, rounds or review evidence. This keeps `5e23243` conflict-free.
- **Audited, no change:**
  - `provider_budget.observe_decomposition_result`: round 3 is ordinary `rounds/03`, so its usage is counted.
  - `decomposition_session_pool`: pooled runs only.
  - `host_decomposition_launcher`: reads status, paths and approver.
  - `GauntletView/server.py`: rounds come from progress events.
  - `viewer.py`, `graph_controller.py`, `background_jobs.py`, the CLI, `run_round_robin_decomposition_rag.py`, `run_reviewer_replay_ab.py`.

---

## D. Golden fixtures

### D1. Shared module
- **Path:** `C:\nscrev\<worktree>\Pipeline\TaskDecomposition\tests\revision_review_fixtures.py`.
- **Creator:** the Producer, in **C0, before anyone else starts** (see amendment 3 for the non-blocking protocol).
- **Imports:** only stdlib, `Pipeline.AgentRuntime` config and fakes, and the producer constants plus `_round_invocation_id`.

**API (exact):**
- `RunBinding(task_id, run_id, source_identity, task_execution_contract_identity, d1a_semantic_parent_identity, context_sha256, candidates: {version: {"sha256","graph_delta_plan_id","decision"}}, provider_order=("claude","codex"), models={"claude":"fixture-claude-model","codex":"fixture-codex-model"})`
- `candidate_summary(binding, version)`: odd versions are authored by `order[0]`, even by `order[1]`.
- Run builders:
  - `pair_review_ready_run` (S2)
  - `corrected_review_ready_run` (SC)
  - `revision_review_ready_run` (SR, golden)
  - `revision_review_revised_again_run` (golden needs_human)
  - `revision_review_stopped_run`
  - `revision_at_call_limit_run` (today's 2-round NSC-1165 shape)
- Provider output builders, identical to the history entries: `round_two_revision_output(binding, v2_payload)`, `round_three_pass_output`, `round_three_revised_again_output(binding, v3_payload)`, `round_three_stopped_output`.
- `round_artifacts(run, *, candidate_payloads)` and `write_round_artifacts(artifact_root, run, *, candidate_payloads)`: write the C3 step-8 files, where `structured_output` is the candidate payload for author rounds or the review dict for reviewer rounds.
- Identity-bound fakes: `RuntimeQueueProvider` and `runtime_provider_factory(providers)` (moved from the draft).
- `ForgedVariant(name, applies_to: frozenset{"d1c","ac_review_ready","ac_needs_human"}, mutate, d1c_status, d1c_reason, ac_message)`, plus `FORGED_REVIEW_READY`, `FORGED_NEEDS_HUMAN`, and `forge(run, variant)` (deep copy, then mutate).
- Finding and summary constants, as shown below.

**Rules for consumer tests:**
- D1C tests always build the authorization record from the **golden** run. The only exception is F11: its forged run head is the drifted value and the record keeps the golden head, which is what produces `source_head_drift`.
- AssistantControl tests write artifacts from the golden run and the forged run result on top.

### D2. Golden `review_ready`
Values in `<>` are computed by the builder. `duration_seconds` is irrelevant and set to 1.0 per round and 3.0 for the run.

```json
{"authority":"review_only_not_applied","author_corrections_used":0,"calls_used":2,"context_sha256":"<CONTEXT_SHA256>",
 "d1a_semantic_parent_identity":{"contract_revision":2,"contract_sha256":"<PARENT_SEMANTIC_SHA256>","task_id":"NSC-010"},
 "decision":"decomposed","decomposition_result_path":"decomposition_result.json","duration_seconds":3.0,
 "finding_history":[
  {"findings":[F2],"prior_finding_resolutions":[],"reviewed_candidate_sha256":"<SHA256_V1>","reviewer_provider":"codex","round_number":2,"summary":"Revision required: the completion gate overstates what its Edit Mode test proves.","verdict":"revise"},
  {"findings":[],"prior_finding_resolutions":[RES2],"reviewed_candidate_sha256":"<SHA256_V2>","reviewer_provider":"claude","round_number":3,"summary":"The revised candidate resolves the round-2 finding and is independently approved.","verdict":"pass"}],
 "graph_delta_path":"graph_delta.json",
 "human_next_step":"Review decomposition_result.json, graph_delta.json when present, and the per-round review history. No graph change has been applied.",
 "independent_approver_provider":"claude","latest_candidate":C2,"max_calls":2,"mode":"round_robin_d1b2","pooled_sessions":null,
 "provider_order":["claude","codex"],"rejection_reasons":[],"review_independence":"cross_provider","revision_reviews_used":1,
 "rounds":[
  {"actual_model":"fixture-claude-model","actual_provider":"claude-code","agent_failure_classification":"none","agent_runtime_result_path":"rounds/01/agent_runtime/nsc-010-d1b2-r01-task-decomposer-25c4585052ac/result.json","agent_status":"succeeded","authority":"review_only_not_applied","candidate_after":C1,"candidate_before":null,"correction_of_round":null,"duration_seconds":1.0,"new_finding_ids":[],"pooled_session":null,"rejection_reasons":[],"requested_provider":"claude","role":"task_decomposer","round_number":1,"schema_version":"1.0","status":"candidate_valid","task_execution_request_path":"rounds/01/task_execution/nsc-010-d1b2-r01-task-decomposer-25c4585052ac/task_request.json","unresolved_finding_ids":[],"verdict":null},
  {"actual_model":"fixture-codex-model","actual_provider":"openai-codex","agent_failure_classification":"none","agent_runtime_result_path":"rounds/02/agent_runtime/nsc-010-d1b2-r02-decomposition-reviewer-f554f938a91e/result.json","agent_status":"succeeded","authority":"review_only_not_applied","candidate_after":C2,"candidate_before":C1,"correction_of_round":null,"duration_seconds":1.0,"new_finding_ids":["round-02-misstated-edit-mode-proof"],"pooled_session":null,"rejection_reasons":[],"requested_provider":"codex","role":"decomposition_reviewer","round_number":2,"schema_version":"1.0","status":"revised_candidate_valid","task_execution_request_path":"rounds/02/task_execution/nsc-010-d1b2-r02-decomposition-reviewer-f554f938a91e/task_request.json","unresolved_finding_ids":["round-02-misstated-edit-mode-proof"],"verdict":"revise"},
  {"actual_model":"fixture-claude-model","actual_provider":"claude-code","agent_failure_classification":"none","agent_runtime_result_path":"rounds/03/agent_runtime/nsc-010-d1b2-r03-decomposition-reviewer-e3faeb5f20eb/result.json","agent_status":"succeeded","authority":"review_only_not_applied","candidate_after":null,"candidate_before":C2,"correction_of_round":null,"duration_seconds":1.0,"new_finding_ids":[],"pooled_session":null,"rejection_reasons":[],"requested_provider":"claude","role":"decomposition_reviewer","round_number":3,"schema_version":"1.0","status":"independent_pass","task_execution_request_path":"rounds/03/task_execution/nsc-010-d1b2-r03-decomposition-reviewer-e3faeb5f20eb/task_request.json","unresolved_finding_ids":[],"verdict":"pass"}],
 "run_id":"assistant-nsc-010-decompose-revision-review","run_status":"review_ready","schema_version":"1.0",
 "source_identity":{"branch":"<BRANCH>","head_commit":"<HEAD_COMMIT>","head_tree":"<HEAD_TREE>"},
 "task_execution_contract_identity":{"path":"Tasks/NSC-010.yaml","revision":2,"sha256":"<CONTRACT_SHA256>"},
 "task_id":"NSC-010","unresolved_findings":[]}
```

**Symbols used above** (`Cn` means `{"author_provider":…,"decision":"decomposed","graph_delta_plan_id":"<PLAN_ID_Vn>","sha256":"<SHA256_Vn>","version":n}`):
- `C1`: author `claude`. `C2`: author `codex`. `C3`: author `claude`.
- `F2 = {"affected_contracts":["<TASK_ID>","proposed:bounded-child"],"category":"candidate_correctness","finding_id":"round-02-misstated-edit-mode-proof","problem":"The completion gate says its Edit Mode test proves a public static class; the test only reads the public static Value field.","required_resolution":"Keep the public static class requirement in the acceptance criterion and state only the test oracle in the completion gate.","severity":"blocking"}`
- `RES2 = {"explanation":"The revised completion gate states only what its Edit Mode test proves.","finding_id":"round-02-misstated-edit-mode-proof","status":"resolved"}`

The invocation ids above are verified against the formula, which reproduces the real `…-480002b8eecc`, `…-58fb5ebd4a02`, `…-66352580e24d` and `…-e609c2e9b5c9`.

### D3. Golden `needs_human` (round-3 revise)
All fields are identical to D2 except the following:

```json
{"decomposition_result_path":null,"graph_delta_path":null,
 "human_next_step":"Inspect unresolved_findings and round artifacts. The bounded independent-review circuit reached a human authority boundary; no candidate was approved or applied.",
 "independent_approver_provider":null,"latest_candidate":C3,"run_status":"needs_human","unresolved_findings":[F3],
 "rejection_reasons":["revision review did not approve the revised candidate: its reviewer revised it again, and the latest author may not approve its own candidate"],
 "rounds[2]": {...D2 rounds[2] with "candidate_after":C3,"new_finding_ids":["round-03-gate-still-overstates-proof"],"status":"revised_candidate_valid","unresolved_finding_ids":["round-03-gate-still-overstates-proof"],"verdict":"revise"},
 "finding_history[1]": {"findings":[F3],"prior_finding_resolutions":[RES2],"reviewed_candidate_sha256":"<SHA256_V2>","reviewer_provider":"claude","round_number":3,"summary":"The revision still overstates what the test proves and has been replaced.","verdict":"revise"}}
```

- `F3 = {"affected_contracts":["<TASK_ID>","proposed:bounded-child"],"category":"candidate_correctness","finding_id":"round-03-gate-still-overstates-proof","problem":"The revised completion gate still names a type check the test does not make.","required_resolution":"Name only the Value field read in the completion gate.","severity":"blocking"}`
- **Stopped variant** (`revision_review_stopped_run`): round 3 is `needs_human` / `needs_human` with `candidate_after` null; the finding is `F3S = {"affected_contracts":["<TASK_ID>"],"category":"authority_conflict","finding_id":"round-03-authority-gap","problem":"Approved authority does not settle which completion gate wording binds.","required_resolution":"A person must choose the binding completion gate wording.","severity":"blocking"}`; the summary is `"The revision needs a human decision on the binding completion gate wording."`; `latest` is C2; reasons are `[STOPPED]`.

### D4. Forged variants every applicable consumer must refuse
Each variant is applied to a deep copy of D2. In the D1C column, "RI" means status `review_invalid` with that reason code required in `reason_codes`. The AssistantControl column is the error message.

| ID | Mutation | D1C | AssistantControl |
|---|---|---|---|
| F1 | remove `rounds[2]` and `history[1]`; count stays 1 | RI `bounded_call_accounting_invalid` | M4 |
| F2 | delete `revision_reviews_used`, or set it to 0 | RI `bounded_call_accounting_invalid` | existing "does not prove exactly one bounded author correction" |
| F3 | round 3 by the reviser: requested `codex`, actual `openai-codex`; history reviewer `codex`; approver `codex` | RI `reviewer_is_latest_candidate_author` | M5 |
| F4 | `rounds[2].actual_provider` set to `"openai-codex"`, or to `"fake"` | RI `independent_pass_round_invalid` | M5 |
| F5 | `author_corrections_used: 1` | RI `bounded_call_accounting_invalid` | M3 |
| F6 | a fourth round and history entry added (round 4, codex); count 1, or count 2 | RI `bounded_call_accounting_invalid` | M4 (count 1), M1 (count 2) |
| F7 | counters `True`, `1.0` or `"1"` for revisions; `False` for corrections; `calls_used: True` | RI `bounded_call_accounting_invalid` | M1, M2, or existing "calls_used is True, expected 2" |
| F8a | `rounds[2].candidate_before.sha256` set to `"0"*64` | RI `independent_pass_round_invalid` | M5 |
| F8b | `history[1].reviewed_candidate_sha256` set to V1 | RI `review_history_does_not_bind_reviewed_candidate` | M5 |
| F8c | `latest_candidate.sha256` set to `"0"*64` | RI `independent_pass_round_invalid` | M5 |
| F8d | revision identical: V1 SHA used in round-2 after, round-3 before, latest and history | RI `round_sequence_inconsistent` | M5 |
| F9 | `history[1]` resolutions set to `[]`, or to `still_blocking`, or given an extra id, or given status `"fixed"` | RI `review_history_resolution_semantics_invalid` | M5 |
| F10 | round 3 numbered 4, or `"3"`; rounds 2 and 3 swapped; round 3 `correction_of_round: 2`; history round number 4 | RI `round_sequence_inconsistent` (history round number 4: `review_history_does_not_bind_reviewed_candidate`) | M5 |
| F11 | run `head_commit` set to `"0"*40`; the record keeps the golden head | `stale_binding` `source_head_drift` | existing "used another source commit or tree"; D1C does not apply to the AssistantControl-only branch variant, which gives M7 |
| F12a | run `rejection_reasons: ["round 3 revision review: source HEAD changed during provider invocation"]` | RI `d1b_run_reported_rejection_reasons` | existing "carries unresolved findings or rejections" |
| F12b | `rounds[2].rejection_reasons: ["source HEAD changed during provider invocation"]` | RI `independent_pass_round_invalid` | M5 |
| F13 | `pooled_sessions: {}`, or a non-null `rounds[2].pooled_session` | RI `round_sequence_inconsistent` | M8 or M5 |
| F14 | `review_independence: "same_provider_separate_sessions"` | RI `round_sequence_inconsistent` | existing authentication message |
| F15 | `max_calls: 3` | RI `bounded_call_accounting_invalid` | existing "max_calls is 3, expected 2" |
| F16 | `rounds[2]` result path uses INV2 under `rounds/03` | RI `reviewer_invocation_identity_mismatch` | M6 |
| F17 | round 3 status and verdict set to `needs_human` while run is `review_ready` | RI `independent_pass_round_missing` | M5 |
| F18 (AC only) | on disk: `result.json.provider` wrong; structured-output resolutions `[]`; `result.json` deleted | not applicable | M6 |

**`FORGED_NEEDS_HUMAN`** (AssistantControl `_needs_human_proof`, through `run` or `inspect`; D1C refuses every needs_human run with `d1b_run_status_not_review_ready`):
- **Revision-review shape message:**
  - N1: `revision_at_call_limit_run` with count 1.
  - N3: round 3 by the reviser.
  - N6: reasons set to `[CALL_LIMIT]`.
  - N7: round 3 `candidate_before` set to v1.
  - N9: missing resolution.
  - N10: four rounds.
  - N11: round 3 numbered 4.
- **Round beyond max_calls:** N2, D3 with the count removed or set to 0.
- **Both counters:** N4.
- **Count type:** N5, counts `True`, `2`, `"1"` or `1.0`.
- **Source movement:** N8, `revision_at_call_limit_run` plus `"round 2: source HEAD changed during provider invocation"`, or plus the unprefixed `"source working tree changed during provider invocation"`.

---

## E. Work breakdown and file ownership
All paths are under the repository root. There is no shared ownership of any file. Amendments 1, 2 and 4 modify this section.

- **Producer (P).**
  - **C0:** `round_robin_decomposition.py`, constants only. New `tests/revision_review_fixtures.py`. New `tests/revision_review_fixtures_smoke_test.py`, which covers:
    - builders satisfying B3 and B4;
    - invocation ids;
    - every forged variant differing from golden;
    - `SOURCE_REVALIDATION_REASONS` pinned, via AST, to `context_builder.source_revalidation_reasons`;
    - `RUNTIME_PROVIDER_IDENTIFIERS` pinned to `live_decomposition`.
  - **P1:** finish the draft in `round_robin_decomposition.py` (use the constants). `review_contracts.py`: no change required; if it is touched, `REVIEW_VERDICTS`, `FINDING_RESOLUTION_STATUSES` and the finding and resolution field sets must stay identical.
  - **P1 tests:**
    - `revision_review_smoke_test.py` (draft);
    - a new **golden-conformance case**: the producer's SR and revised-again output, using the fixture output builders and identity-bound fakes, equals the builder output with `duration_seconds` normalized;
    - `round_invocation_id_smoke_test.py`, adding round 3.
    - (The README counters section and the CI workflow line move to the coordinator's merge commit per amendment 2.)
  - Existing `round_robin_decomposition_smoke_test.py` case 4 needs no change: it uses `"fake"` on both sides, so the grant is refused.
- **D1C (D).** `Pipeline/TaskReviewAgent/decomposition_authorization.py` and `local_decomposition_apply.py`, with NEW self-contained test modules per amendment 1 (SR authorizes; D4 variants refused; existing tests untouched).
- **AssistantControl (A).** `Pipeline/AssistantControl/decomposition.py`, `test_decomposition.py`, `test_decomposition_needs_human.py`, and after the P and D commits (amendment 4), the new `test_decomposition_revision_review_integration.py`.
  - Expected fixture churn: `BoundedAuthorCorrectionReviewTests` and `ReviewReadyUnchangedTests` move to full builder shapes, plus `write_round_artifacts` and a source branch; `expected_facts` and the facts key-set test gain `revision_reviews_used`.
- **Author guidance (G).** `prompts.py`, `review_prompts.py`, and only new test files.
  - **Frozen interface:** the keyword sets of `build_decomposer_prompt`, `build_decomposer_correction_prompt` and `build_decomposition_reviewer_prompt`. Optional keywords with defaults are allowed, but P passes none.
  - These existing asserted substrings must be kept: `You are the independent D1B.2 decomposition reviewer for round {n}.`, `The provider that most recently authored a candidate may not approve`, `The conversation that most recently authored a candidate may not approve`, `duplicate responsibility`.

---

## F. Merge and integration plan
1. P commits C0 on a branch from `ade5bca`. D and A cherry-pick C0 (amendment 3); G stays on `ade5bca`. The existing draft worktree is left untouched as reference.
2. Integration branch from C0: merge **P1, then D, then A, then G, then A's integration commit I1**. No conflicts are expected; the only cross-module imports are the frozen names above.
3. **I1 tests** (synthetic repository; never the retained NSC-1165 plan):
   - **IT1.** Identity-bound fakes run the real producer inside fake compose with `decomposition.run`, and the record is `review_ready`. `_verify_review` equals `inspect` equals the record's review, with reviewer `claude` and `revision_reviews_used: 1`. D1C `validate_decomposition_authorization` is `AUTHORIZED` with this record:
     - `reviewer_provider` = approver
     - `reviewer_invocation_id` = INV3
     - `review_evidence_sha256` = `semantic_sha256(finding_history[-1])`
     - `decomposition_result_sha256` and `reviewed_candidate_sha256` = `candidate_sha256`
     - `graph_delta_canonical_sha256` = `sha256(plan.canonical_json())`
     - `task_contract_sha256` and `source_head` taken from the run
     - `record_sha256` = `authorization_record_sha256`

     Then `apply` commits the v2 children. Exactly 3 provider calls.
   - **IT2.** A normal two-call pass through the same path: authorized and applied, 2 calls.
   - **IT3.** Round-3 revise: needs_human, the facts include the count, `inspect` is stable, `apply` is refused, D1C refuses, and there is no `rounds/04`.
   - **IT4.** Correction plus round-2 revise: needs_human with the call-limit reason, 3 calls.
   - **IT5.** Every D4 variant on the IT1 artifacts, refused by each applicable consumer.
   - **IT6.** A `Tasks/` commit after the proposal makes `apply` fail with "TaskGraph inputs changed…", and D1C with the new head gives `stale_binding`.
   - **IT7.** The legacy NSC-1165 record (no count) still inspects.
4. **Failing-before evidence.** Run in a detached worktree at `ade5bca`+C0, because C0 is inert and the imports need it. These must fail before and pass after:
   - P's SR, ceiling and identity cases;
   - D's SR authorization;
   - A's SR acceptance, F3, F4, F9, F10, F16, F18, N1–N11 and facts preservation;
   - IT1 and IT3.

   Controls that pass before and after: two-call pass, pooled runs, longer limits.

---

## G. Open questions and risks (with defaults)
1. **"reject" verdict.** There is none. **Default:** map it to `needs_human`; no schema change.
2. **D1C scope.** D1C still refuses author-correction runs and still accepts `max_calls ≥ 3` three-round chains. **Default:** preserve both; they are out of scope.
3. **Clean-pass rule.** AssistantControl's rule refuses a round-3 pass that carries advisory findings, although the producer calls that run `review_ready`. This could fail the NSC-1165 rerun closed. **Default:** preserve.
4. **Timeout.** AssistantControl's compose timeout is 3600 s, but the worst case is 1440 + 1200 + 1200 s (the correction path already reaches 4080 s). A timeout fails closed. **Default:** no change here; raise it in a follow-up.
5. **Launcher runs.** A non-pooled `host_decomposition_launcher --max-calls 2` run can now hand off a plan approved in round 3; the human approval event remains the gate. **Default:** no change.
6. **Final prompt wording.** The round-3 reviewer is not told it has the final call. **Default:** accept; G may add an optional keyword later, which P would pass in a later commit.
7. **Stray artifacts on route refusal.** `rounds/03-request.json` and the start event may remain. **Default:** accept, documented.
8. **Commit shape for #36.** **Default:** keep per-developer commits on the integration branch and report the range and head; squash only if Astra asks.
9. **Not-yet-applied `review_ready` records at merge time.** They still verify, because real runs have runtime identities and artifacts, and an absent count is read as 0.

### Critical files for implementation
- `Pipeline/TaskDecomposition/round_robin_decomposition.py`
- `Pipeline/TaskReviewAgent/decomposition_authorization.py`
- `Pipeline/AssistantControl/decomposition.py`
- `Pipeline/TaskDecomposition/tests/revision_review_fixtures.py` (new, C0)
- `Pipeline/TaskReviewAgent/local_decomposition_apply.py`
