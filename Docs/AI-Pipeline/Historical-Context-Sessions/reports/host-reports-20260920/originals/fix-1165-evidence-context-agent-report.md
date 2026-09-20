# Codex blocker 3, child GDD evidence by context (developer E): final report

Received 2026-09-13 at about 23:20 UTC and recorded in summary by the coordinating session. The full text is in the agent transcript. Measurement scripts and outputs are in `C:\nscrev\evidence-context-measure`.

## Commit

- **Commit:** `3c64631f65535b3b9d6fd1a6d27ba005f2a366d5`, parent `fce5398`, on branch `throughput/decomposition-evidence-context` (worktree `C:\nscrev\evidence-context-fix`). Not pushed.
- **Change size:** 10 files, +2182/-130. `git diff --check` is clean.
  - `child_gdd_evidence.py` (new, +966)
  - `child_gdd_evidence_smoke_test.py` (new, +923)
  - guidance test +163/-80
  - `prompts.py` +45/-22
  - `context_builder.py` +26/-3
  - `automation_policy.py` +23/-22
  - `round_robin_decomposition.py` +17
  - `live_decomposition.py` +16/-1
  - `review_prompts.py` +2/-1
  - `test_support.py` +1/-1
- **Stacked copies:**
  - on `live/run1-20260913`: `9dee4a6`
  - on A's branch: `efc498a`
  - on D's branch: `2461142`

## Design

### Classification
- **Functions:** `synthetic_fixture_marker` and `is_explicit_synthetic_fixture` copy `is_synthetic_gauntlet` line for line.
  - NSC-042 is human-only.
  - The origin must be `human_approved_synthetic_gauntlet`, or `gauntlet_id` must be in {`synthetic-architect-gauntlet-v1`, `assistant-control-local-replay-v1`}.
  - A task whose origin is `progressive_decomposition` inherits the result from its parent.
- **Delegation:** `automation_policy.is_synthetic_gauntlet` now calls this code. A test compares it with a verbatim copy of the old function over 80 cases.

### Resolver
- **Anchors** come from the committed GDD: every `#` heading, with and without its "N." prefix; labels that open a paragraph or bullet; and the first cell of each table row. The real GDD yields 200 anchors, sha `d0e85a7f...`.
- **Phrase rule:** every non-filler word must be covered by a complete anchor phrase that appears contiguously in the reference.
- **Allowed filler words:** gdd, section(s), and, row(s), table, bullet(s), role, paragraph, the GDD path, and heading numbers 1-13.
- **Word splitting:** dots, underscores and slashes join words, so `provenance.origin` can never match.

### Rule
- **`synthetic_fixture`:** children may have empty evidence, but every entry they cite must be inherited or must resolve.
- **`real_task`:** each child needs at least one entry, and each entry must be inherited (exact match to a selected reference) or resolve. Empty selected evidence is no exemption.

### Enforcement
- **Validator:** `validate_child_gdd_evidence(result, *, policy)` runs right after `validate_decomposition_result` in `round_robin._validate_candidate`. That covers round 1, the correction, the reviewer revision and the reviewer-replay A/B.
- **Also enforced in:** `live_decomposition`, plus a policy preflight parse.
- **Failures:** an evidence failure is an ordinary round rejection, so the bounded author correction applies.
- **Unchanged signatures:** `validate_decomposition_result`, `plan_graph_delta` and `plan_graph_apply`.

### Context binding
- **Schema 1.1** adds a `child_gdd_evidence_policy` block: task, classification, marker, lineage, references, GDD path and sha, resolver version, anchor count and anchor sha.
- **Coverage:** `context_sha256` covers the block.
- **Legacy contexts (schema 1.0)** have no block, and records say so.

### Consumer API
`require_committed_child_gdd_evidence(result, *, source_root, source_commit, context_json: bytes, context_sha256)`, with all arguments required. It:
1. checks that the context bytes hash to the recorded sha;
2. checks that the Source commit and parent identity match;
3. rebuilds the policy from `Tasks/` and the GDD at that commit;
4. for a 1.1 context, requires the stored block to equal the rebuilt one (no way to skip this);
5. validates the children.

It returns `{context_schema_version, legacy_context_without_policy, child_gdd_evidence_policy}`.

### Context identity audit
- Nothing rebuilds an existing run's context identity.
- The golden fixture hashes are unchanged.
- The retained NSC-1165 contexts still hash-match.

## Measurement

| Repository | Tasks | References (distinct) | Phrase rule | Looser bag-of-words |
|---|---|---|---|---|
| game `886bb81` | 84 | 194 (123) | 170 (102) | 175 (106) |
| pipeline `fce5398` | 102 | 158 (99) | 149 | 154 |

- **Looser-only references (4):**
  - NSC-016 "Enemy health and defeat ownership; Active Enemy Registry"
  - NSC-026/039 "GDD - Required feedback and character presentation"
  - NSC-028 "Section 4 — Dungeon Encounter Agent / Ownership Invariants"
  - NSC-013 "Section 5 — Runtime Implementation (enemy movement paragraph)"
- **Unresolved in the game repo:** 21 distinct references (24 occurrences), none of them a GDD heading citation. Examples: Design/Approved WebGL artifact references, "Human-approved ... flow, 2026-09-12", task-ID references such as "NSC-029 VAL-001; ...", and paraphrases for NSC-061..077. These stay valid only through inheritance.
- **Rejected fabrications:** provenance strings, run IDs, "Section 3 — Gauntlet Acceptance Rules", "Frost Systems Player", "Section 42 — ...", bare "GDD" or "Section 3", and "NSC-1165 VAL-001".
- **The 47 pipeline tasks with empty evidence:** 41 are synthetic. 6 are real (NSC-056..060 and NSC-901), all cancelled in the pipeline repo. NSC-056..060 are still active in the game repo with no evidence.
- **NSC-025 and NSC-014:** every reference is inheritable and resolves. Sample decompositions pass; an empty or provenance-citing child is rejected.
- **NSC-057** (active, `human_integration_required`, no evidence):
  - Its references are Engineering Standards, not GDD.
  - The GDD has nothing relevant, although "API and Tool Constraints" would pass deterministically.
  - It is not decomposable anyway: `plan_graph_delta` refuses any parent that is not `needs_execution_decomposition`.

## Tests

- **New module:** 17/17 at `3c64631`. At `fce5398`, 13 fail: 7 on behaviour, 6 because the code is absent. The 4 guards pass there.
- **Guidance test:** 11/11 at `3c64631`; 7 fail at `fce5398`.
- **Suites** (identical at `fce5398` and `3c64631`):
  - all TaskDecomposition suites pass, including revision_review (21), pooled (17) and fixtures (12);
  - graph_controller 33, test_decomposition 57, IT 7, needs_human 37;
  - D1C revision-review 59, local-apply revision-review 7.
- **Pre-existing failures** (identical at both commits): test_viewer 39 with 1 timing error; graph_delta and graph_apply fail on D's fixture, which F fixes.
- **Test hygiene:** no suite that writes under `C:\NSC` was run.

## Consumer wiring (report section 6)

- **A (AssistantControl `_review_ready_proof`):** after the plan freshness and parent-semantic checks:
  - read `context_bytes` from `authenticated.result_path.parent/"context.json"`;
  - call `require_committed_child_gdd_evidence(decomposition, source_root=manager.source, source_commit=record["source_commit"], context_json=context_bytes, context_sha256=run_result["context_sha256"])`;
  - add `context.json` to `artifact_sha256` and `child_gdd_evidence` to the proof;
  - the fixtures need a real `context.json` and its hash.
- **D (local apply, `review_local_decomposition_plan`):** the same call at `bound_head`, refusing with "stored decomposition child GDD evidence is invalid". Coordinator decision: this moves to a follow-up (option B), because the shared fixtures have no GDD or `context.json`.
- **`host_decomposition_launcher.py`:** the same call inside the existing try, after preflight is fresh (about line 852). Not assigned; follow-up.
- **`synthetic_gauntlet_approver.py`:** only if its handoff artifacts carry `context.json`.
- **Unchanged:** `validate_decomposition_authorization` stays pure.

## Residual risks

- **Existence, not relevance:** the resolver proves a heading exists, not that it supports the child.
- **Easy short citations:** 24 single-word anchors make short citations easy to satisfy.
- **Resolver version:** any change to anchor extraction must bump `GDD_HEADING_RESOLVER_VERSION`.
- **Paraphrasing authors** may use up the bounded correction more often.
- **Local-apply handoff** does not bind the run result's bytes.
- **Classification trusts committed provenance.**
- **Fixture change:** the `test_support` fixture GDD gained "## Synthetic GDD".
