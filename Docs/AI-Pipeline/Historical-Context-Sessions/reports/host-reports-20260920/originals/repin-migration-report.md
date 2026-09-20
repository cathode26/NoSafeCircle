# Repin migration: authenticated re-pin of the validation-policy bindings an apply invalidates

- Branch `throughput/repin-migration`, worktree `C:\nscrev\repin-migration`
- Commit `36a000c3918680b150d950104c1b21724c0a3dd0`, parent `027e7879715633119cfc1b65179882d91843a361` (the reviewed trial head)
- Files: `Pipeline/TaskGraph/decomposition_policy_repin.py` (new), `Pipeline/TaskGraph/graph_apply_materialize.py`, `Pipeline/TaskGraph/apply_graph_delta.py`, `Pipeline/AssistantControl/test_decomposition.py`, `Docs/AI-Pipeline/Stage5-Decomposition-Design/D1C_GRAPH_APPLICATION_DESIGN.md`. `git diff 027e787 HEAD --check` is clean; `graph_delta_smoke_test.py` is absent from `git diff 027e787 HEAD --stat`.
- Not pushed, not merged. Nothing under `C:\NSC` was written. Live-run inputs were read only with `git --no-optional-locks show/ls-tree` and from run 1's `-Checkouts-5` artifacts.
- `1dae47b` was not built on; it was used only for failing-before evidence.

## 1. The defect, verified from the live Source history

Applying a decomposition rewrites every active dependent of its parent inside the apply's own commit (`graph_delta._rewrite_dependent`: the dependency moves to the children and `contract_revision` is bumped). Any committed validation binding pinned to the dependent's previous contract becomes stale. Both faces are reproduced below from `C:\NSC\GauntletFresh1140-20260912-1` history.

| Run | Apply commit | Dependent | Binding | Pin | Hash of pre-apply contract | Hash of rewritten contract | Policy changed by apply |
|---|---|---|---|---|---|---|---|
| 1 | `1289283` (NSC-1145) | NSC-1146 | `decomposition_child_templates` (semantic hash) | `555810312bd6...` | `555810312bd6...` (matches) | `529eeffa5377...` | no |
| 2 | `1175937` (NSC-1166) | NSC-1167 | `tasks` (SHA-256 of bytes) | `76e17a2b045d...` | `76e17a2b045d...` (matches) | `8f7a5bfd43c4...` | no |

Policy health on the same history: at `1175937^` (`2c5c006`), 27 `tasks` entries, 0 stale, 0 orphaned. At `1175937` and at current HEAD `62b2af5`, exactly one is stale: `NSC-1167`, caused by the apply itself. Every machine-approved task (41) carries exactly one binding, never both and never neither. `NSC-042` is the one human-authority `tasks` entry. The same holds at `027e787`: 22 entries, 12 templates, 0 stale, 0 orphaned, 33 machine-approved tasks each bound once. The committed policy is already in `canonical_json_text` form at `027e787`, `1175937` and `1289283`, and all 102 committed contracts at `027e787` are too.

### Real-data replay of run 1

Script: `scratchpad\repin-migration-agent\replay_run1.py`. It builds a scratch repo from the graph inputs at `ccc1889`, the commit run 1's apply was bound to (`1289283^`), then applies run 1's own reviewed `graph_delta.json` and `decomposition_result.json` through the real D1C boundary.

- With `027e787` code: `apply status=applied`, 5 committed paths, NSC-1146 pin unchanged. `post-apply audit: REFUSED: decomposition template for NSC-1146 is stale: it names parent contract '555810312bd6f5dd094dd3ca6e0ddba6a74a230d6329ba6b94d6cd8df113468f'; the committed contract is '529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f'`. This is the live sentence.
- With this commit: `apply status=applied`, 6 committed paths (policy `2 +-`). `post-apply NSC-1146 template pin=529eeffa5377...`, `post-apply audit: PASS`.

Run 2 (the `tasks` face) was not replayed. Its reviewed artifacts live under the live run's `-Checkouts-6`, which I was not allowed to read. Run 2 is covered by the history measurements above and by the tests.

## 2. Specification extended to a second face, and why

Mid-task, the coordinator reported run 2: NSC-1167 terminally `validation_failed` with `authoritative validation policy for NSC-1167 is stale`. This is the same defect class. The pin is the SHA-256 of the raw contract bytes (`gauntlet_replay._policy_entry`), and `downstream_resilience.validation_plan_for` compares it with `load_committed_task`'s SHA-256 of the committed blob. A `sync_candidate` cannot help because the pin itself is stale. The migration was therefore extended to every rewritten dependent's `tasks` entry: it is re-pinned to the SHA-256 of the exact contract bytes the apply commits. Codex's five rules apply unchanged to both binding kinds.

## 3. Codex's five requirements: what enforces each

Line numbers are at `36a000c`. `DPR` = `Pipeline/TaskGraph/decomposition_policy_repin.py`, `GAM` = `graph_apply_materialize.py`, `AGD` = `apply_graph_delta.py`.

### 3.1 Verify the old binding first
- The rewritten dependents' pre-rewrite contracts are read from Git at the captured commit (`load_committed_tasks`, DPR:317), never from the overlay or the working tree.
- Missing binding:
  - A machine-approved eligible decomposition parent without a template refuses (DPR:381). This is the audit's own `requires_decomposition_child_template`.
  - A machine-approved dependent with neither binding refuses (DPR:388).
  - A machine-approved dependent in a repo that commits no policy refuses (DPR:330-343).
- Stale binding:
  - Template: must equal `parent_semantic_hash(committed pre-rewrite contract)`, else refuse (DPR:403).
  - Task entry: must equal the SHA-256 of the committed pre-rewrite bytes, else refuse (DPR:422).
  - A stale pin is never re-pinned.
- Refusal path: `DecompositionPolicyRepinError` becomes `GraphApplyMaterializationError` (GAM:588-592). It is raised before the first `os.replace`, so `apply_graph_delta` returns `materialization_failed` and its pre-commit rollback finds nothing to restore.

### 3.2 Read trusted policy bytes
- Bytes and blob ID come from the captured commit (`GitRepository.read` and `.blob`, DPR:205-221). The document is parsed from those bytes (DPR:348-354) and shape-checked by the reader's own `require_decomposition_policy_document`.
- The working-tree file must be one regular file whose Git clean-filter blob ID equals the committed blob ID, else refuse (DPR:224-253). The comparison goes through the clean filter because these checkouts are `core.autocrlf=true`, where raw bytes differ by CRLF while committed content is identical. This is the same technique as `decomposition_replay._working_file_matches_committed_blob`.
- An untracked policy file present when the policy is not committed also refuses (DPR:332-337).
- The captured commit is the immutable HEAD the materializer's committed baseline already resolved (GAM:579). `apply_graph_delta` proves it equals its own `old_head` (which equals `expected_head`) at the staging boundary (AGD:1184). The materialize seam signature `(slice1_result, root)` is used by existing fault-injection seams, so the commit could not be passed in without breaking them.

### 3.3 Make one narrow change
- Only `parent_task_contract_sha256` (DPR:412) and `task_contract_sha256` (DPR:431) of proven entries change.
- Already-decomposed dependents are skipped for both maps (DPR:396-400).
- Narrow-change proof: restoring exactly the re-pinned fields in the proposal must reproduce the trusted document, else refuse (DPR:441-455).
- If nothing is re-pinned, the result is `None` and the policy stays byte-identical. An apply that rewrites no dependent never reads the policy (GAM:575-576).

### 3.4 Audit the entire resulting policy
- `audit_decomposition_policy(root, document=updated, tasks=proposed_tasks)` runs over the complete proposed graph (DPR:456-464). This is every template, variant and resource rule, unchanged. `proposed_tasks` is the overlay map `_validate_exact_task_change_set` returns: parent, children, rewritten dependents, everything else.
- `_audit_contract_entries` (called at DPR:465-472, defined at DPR:525-617) proves every `tasks` entry:
  - Well-formed key and 64-hex hash.
  - A task this apply publishes must name the SHA-256 of the published bytes.
  - Every other task in the graph must still name its committed bytes (one `cat-file --batch`). An entry valid before cannot be left invalid after.
  - Entries for decomposed aggregates, which are never focus-validated, and for tasks absent from the graph are reported and left as committed.
- Any refusal anywhere rejects the whole apply.

### 3.5 Verify publication
- Before writing, the plan binds the canonical text, its SHA-256 and its `git hash-object --filters` blob ID into `PolicyRepinPublication` (DPR:474-500). It also confirms the serialization reproduces the document and differs from the trusted bytes.
- `_append_policy_artifact` (GAM:595-629) requires each re-pinned contract artifact's text to equal the text the pin was computed from, and to hash to the pin.
- The policy is published last, through the same staging-dir and `os.replace` path as every other artifact.
- Immediately before `git add`, `_require_policy_inputs_unchanged` (AGD:1166-1219) re-checks:
  - the binding names `old_head` and a path in the change set
  - `git rev-parse HEAD` still equals `old_head`
  - the committed policy blob at `old_head` still equals the migration's input
  - the working-tree policy's SHA-256 equals the audited SHA-256
- Immediately after `git add`, `_require_staged_policy_publication` (AGD:1222-1251) re-checks:
  - the `git ls-files -s` blob of the policy equals the audited blob ID
  - each re-pinned contract's staged blob content (`cat-file blob`) hashes to the value the policy now names, which is exactly what `load_committed_task` will compute after the commit
- Both run inside the existing `try` around `_stage_and_check` (AGD:1726-1737). Any discrepancy returns `materialization_failed` through `_materialization_failure_result`, which restores the published set and requires a clean committed HEAD (`_restore_precommit_materialization`, AGD:943). No commit is made.
- `_policy_publication` (AGD:1078-1144) type-checks a seam-supplied binding exactly, so malformed input becomes a rollback, never an escaping `TypeError`.

## 4. The seam

`materialize_graph_apply` is the only phase that can add a file to the D1C change set. `_stage_and_check` requires the dirty set to equal `changed_paths`, and `_verify_commit_boundary` requires the commit to equal it. So the migration is computed there, after all graph artifacts and before staging (GAM:761-770), and verified at the staging boundary in `apply_graph_delta`. `GraphApplyMaterializationResult` gains `policy_publication: PolicyRepinPublication | None = None` (GAM:78). The default keeps every existing construction and `replace()` call working.

- **`local_decomposition_apply` (production local path).** `_apply_reviewed_plan` calls the same `apply_graph_delta(context.source_root, ..., expected_head=context.source_head)` (local_decomposition_apply.py:382), so it gets identical protection. `rebind_after_local_decomposition` (local_rehearsal.py:936-1000) checks only subject, parent, cleanliness, children and the contract change set, so an extra policy path does not affect it. `local_decomposition_apply_test` passes (section 6).
- **AssistantControl `decomposition.apply`.** It runs under `_source_integration_lock`, then `apply_graph_delta(..., expected_head=review["apply_source_commit"])` (decomposition.py:496).
- **`_source_advancement_proof` (decomposition.py:93-117) and `local_decomposition_apply._graph_inputs_unchanged` (113-124).** Both already list the policy file among the authoritative graph inputs. A re-pinning apply therefore makes any other proposal reviewed against an earlier head fail `authoritative_graph_inputs_unchanged` and require re-review. This is not a new staleness class: every apply already changes `Tasks/` and `Pipeline/TaskGraph/WORK_ID_MAP.json`, which are in the same input set.
- **Undo.** `undo_graph_delta` (undo_graph_delta.py:173-190, 265-297) reverts the apply commit's own path set, and requires the reverted tree to equal the source tree exactly. Undoing a re-pinning apply therefore restores the old pins together with the old dependent contracts. No change needed.

## 5. Tests

Location: `Pipeline/AssistantControl/test_decomposition.py`, class `DecompositionPolicyRepinMigrationTests`. It is 12 tests (13 cases including subtests) on its own committed-graph fixture (`TaskDecomposition/tests/test_support.create_repository` plus bindings), not the broken `graph_delta_smoke_test` fixture.

Each test runs the real `apply_graph_delta`, or `materialize_graph_apply` directly for dirty input. Every refusal test asserts: HEAD and commit count unchanged, empty `git status`, empty index, unchanged tracked content, and the policy equal to the committed bytes.

Tracked content is compared Git-normalized (CRLF to LF). Under `core.autocrlf=true`, the rollback's `git restore --worktree` rewrites published LF files as CRLF without changing tracked content. Empty `git status` and index are asserted alongside.

| Codex test | Test name(s) |
|---|---|
| valid old binding updates successfully | `test_valid_template_binding_is_repinned_in_the_same_commit`; tasks face `test_valid_task_entry_binding_is_repinned_in_the_same_commit` |
| missing binding refuses | `test_missing_template_binding_refuses_the_apply`; tasks face `test_missing_task_entry_binding_refuses_the_apply` |
| stale binding refuses | `test_stale_template_binding_refuses_the_apply`; tasks face `test_stale_task_entry_binding_refuses_the_apply` |
| dirty policy input refuses | `test_dirty_policy_input_refuses_the_migration` |
| mutation between audit and staging refuses | `test_policy_mutation_between_audit_and_staging_refuses_the_apply` |
| unrelated invalid entry refuses the complete apply | `test_unrelated_invalid_policy_entry_refuses_the_complete_apply` (subtests: template naming a task outside the graph; `tasks` entry stale against an untouched contract) |
| multiple dependents update correctly | `test_multiple_dependents_of_both_binding_kinds_are_repinned` (NSC-012 template + NSC-004 `tasks` entry in one commit) |
| already-decomposed dependents remain unchanged | `test_already_decomposed_dependent_keeps_its_historical_binding` |
| failure leaves no staged files, commit, or partial graph change | `test_refused_migration_leaves_no_staged_file_commit_or_partial_change`, plus `_assert_nothing_changed` in every refusal test |

Both "valid" tests also prove the fix end to end:
- Template test: asserts the old document refuses with `decomposition template for NSC-012 is stale` against the new graph, and that `audit_decomposition_policy(commit=new_head)` passes.
- Tasks test: `validation_plan_for` resolves the rewritten contract at the new head, where before it raised the run 2 stale sentence.

### 5.1 Failing-before evidence

Each baseline got a detached worktree (`git -C C:\nscrev\throughput worktree add --detach /c/nscrev/before-<sha> <sha>`). Only the final `test_decomposition.py` was copied in, and only `DecompositionPolicyRepinMigrationTests` was run. Output went to `scratchpad\repin-migration-agent\before-027e787.txt` and `before-1dae47b.txt`. Both worktrees were then removed with `worktree remove --force` and `worktree prune`.

**At `027e787`: `Ran 12 tests`, `FAILED (failures=13)`.** Every failure is an assertion, with no import or fixture errors.

| Test | Failure |
|---|---|
| valid template | `'Pipeline/TaskReviewAgent/authoritative_validation_policy.json' not found in [...'Tasks/NSC-012.yaml', 'Tasks/NSC-1001.yaml']` (no re-pin committed) |
| valid task entry | same |
| multiple dependents | same |
| already decomposed | same (the NSC-012 re-pin the test also requires is absent) |
| missing template / missing task entry / stale template / stale task entry / unrelated (both subtests) / no-partial-change | `'materialization_failed' != 'applied'` (the apply committed a stale or missing binding) |
| dirty input | `GraphApplyMaterializationError not raised` |
| mutation | exact-reason assertion failed: the apply did refuse, but for an unrelated reason (`Materialized working-tree paths differ from the exact Slice 2 change set`), because at `027e787` the policy is not part of the change set at all |

**At `1dae47b`: `Ran 12 tests`, `FAILED (failures=11)`.** Two pass: valid template and already decomposed. The rejected commit did implement the template re-pin and the decomposed-dependent skip, and neither is a safety test.

Safety tests, failing because the rejected implementation blesses or consumes what it should refuse:
- missing template: `'materialization_failed' != 'applied'` (a missing binding blessed)
- stale template: `'materialization_failed' != 'applied'` (a stale pin overwritten without proof)
- dirty input: `GraphApplyMaterializationError not raised` (the working-tree bytes were consumed)
- unrelated invalid template, and unrelated stale `tasks` entry: `'materialization_failed' != 'applied'` (only the re-pinned entry was audited)
- mutation between audit and staging: `'materialization_failed' != 'applied'` (the mutated policy was committed)

Failing at `1dae47b` only because the `tasks` face does not exist there, not because it blesses anything:
- valid task entry
- missing task entry
- stale task entry
- multiple dependents (dict mismatch on NSC-004's pin)
- no-partial-change (it uses a stale `tasks` entry)

The template-face counterpart of "no partial change" is covered by the `_assert_nothing_changed` assertions inside the missing template, stale template, mutation and unrelated tests, which all fail at `1dae47b`.

### 5.2 Passing-after (exact result lines, on the committed code)

- `python -m unittest Pipeline.AssistantControl.test_decomposition.DecompositionPolicyRepinMigrationTests`: `Ran 12 tests in 54.641s` / `OK`
- `python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_gauntlet_replay`: `Ran 31 tests in 91.182s` / `OK`
- `python Pipeline/TaskReviewAgent/tests/decomposition_policy_audit_smoke_test.py`: `TaskReviewAgent decomposition policy audit smoke tests: PASS (13 tests)`
- `python Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py`: `synthetic gauntlet setup tests: PASS (9 tests)`
- `python Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py`: `decomposition_graph_semantics_smoke_test: PASS`
- `python Pipeline/TaskReviewAgent/tests/automated_decomposition_replay_smoke_test.py`: `PASS automated decomposition replay smoke suite (7 tests)`
- `git diff 027e787 HEAD --check`: clean

## 6. Non-regression for the known-red shared-fixture suites

Without the workaround, `graph_delta_smoke_test.py` dies in the first fixture: `DecompositionPolicyError: Child exclusive_resources must exactly partition the parent exclusive_resources (missing=[], extra=['logical:new-shared', 'logical:new-shared'])`.

Temporary, uncommitted workaround, applied identically in each tree and never staged: `graph_delta_smoke_test.py` lines 116-117 become children `["logical:shared"]` and `[]`. It was reverted in my worktree before committing (`git diff --stat` on the file was empty, and the file is absent from the commit).

| Suite | `027e787` + workaround | this change + workaround (pre-commit worktree) |
|---|---|---|
| graph_delta_smoke_test | exit=1, `KeyError: 'logical:new-shared'` (its own resource-group assertion, line 221, no longer applies to the reshaped fixture) | identical |
| graph_apply_plan_smoke_test | exit=0, `graph_apply_plan_smoke_test: PASS` | identical |
| graph_apply_materialize_smoke_test | exit=0, `graph_apply_materialize_smoke_test: PASS` | identical |
| graph_apply_smoke_test | exit=0, `graph_apply_smoke_test: PASS` | identical |
| graph_undo_smoke_test | exit=0, `TaskGraph graph undo smoke tests: PASS (2 tests)` | identical |
| local_decomposition_apply_test | exit=0, `OK` | identical |
| decomposition_authorization_smoke_test (also imports the fixture) | exit=0, `Decomposition authorization tests: PASS (59 tests)` | identical |
| TaskReviewAgent task_id_width_smoke_test (also imports the fixture) | exit=1, `unexpected child allocation: ['NSC-1140', ... 'NSC-1155']` (pre-existing) | identical |

Committed SHA `36a000c` + the same workaround, in a separate detached worktree (`/c/nscrev/nonreg-36a000c`, removed and pruned afterwards; the workaround never touched `throughput/repin-migration`): identical to both columns above for all eight suites. graph_delta `exit=1 KeyError: 'logical:new-shared'`; graph_apply_plan, graph_apply_materialize and graph_apply `PASS`; graph_undo `PASS (2 tests)`; local_decomposition_apply `OK`; decomposition_authorization `PASS (59 tests)`; task_id_width `exit=1` with the same `unexpected child allocation` assertion. Output: `scratchpadepin-migration-agent
onreg-36a000c.txt`.

## 7. Consumers of the D1C commit and the policy file

- **`undo_graph_delta`**: correct unchanged (section 4).
- **`reset_task`** (reset_task.py:3177-3222): `protected_exact` is the apply's changed paths, so a later commit touching only the policy file now blocks decomposition recovery. This is the fail-closed direction, and any later apply already blocks it through `WORK_ID_MAP.json`.
- **`graph_controller`**:
  - `_GRAPH_PATH_PREFIXES` refuses uncommitted local graph edits and already included the policy.
  - `_test_filters` uses a `tasks` entry only when its hash matches the contract. A rewritten dependent's filters now resolve, where before they silently fell back to completion-gate parsing.
- **`taskcontrol_state`**: a dependent's validation identity changes only when its contract also changes in the same commit.
- **`polling_orchestrator._decomposition_offerable` and `source_commit_snapshot`**: they audit the policy at one exact commit, and now pass after an apply instead of refusing.
- **Docs**: `D1C_GRAPH_APPLICATION_DESIGN.md` "Git commit boundary" gains an IMPLEMENTED note that the canonical commit may carry the policy migration. `Stage5-Decomposition-Design/README.md:85` is a historical gap statement and was left alone.
- **`decomposition_replay._validate_automated_authority`** (decomposition_replay.py:296-304) is affected. See residual risk 1.

## 8. Residual risks

1. **Automated-authority replay after a re-pinning apply now refuses. Reproduced on real data; not changed in this commit.**
   - **Mechanism.** `_validate_automated_authority` is unconditional for `AUTOMATED_DECOMPOSITION_APPLICATION_APPROVED`. It requires the working-tree policy blob to equal the blob at the authorized (pre-apply) head.
   - **Reproduction.** On the two real run 1 replay repos, `_working_file_matches_committed_blob(repo, authorized_head=HEAD^, relative_path=policy)` passes after the `027e787` apply. After this commit's apply it fails, which in the replay raises `working decomposition policy differs from the authorized source commit`.
   - **Where it bites.** Only the GitHub-backed TaskReviewAgent path with machine approvals:
     - `polling_orchestrator.py:1256`: post-apply observation between the D1C commit and `complete_decomposition`. It raises `IntegrationObservationError`, which becomes fatal at `max_consecutive_observation_failures` (3787-3810).
     - `host_decomposition_launcher.py:993`: `already_applied` crash recovery.
     - `host_decomposition_launcher.py:1450`: resume.
   - **Not affected.** The live AssistantControl Gauntlet path and `local_decomposition_apply` never run this replay.
   - **Why not fixed here.** No weakening-free change exists inside that authority module, and it is outside this brief's scope.
   - **Proposed design, needing a coordinator decision and its own tests.**
     - Keep the byte-identity check whenever the policy is unchanged.
     - When it differs, require the inspection to be `already_applied`, locate the exact D1C commit with `find_exact_d1c_commit`, and require the working-tree policy blob to equal the blob at that D1C commit, unchanged since.
     - Require the parent's template entry to be identical at `authorized_head` and at the D1C commit.
     - Re-run `audit_decomposition_policy(commit=<d1c>)`, and resolve the parent template from the `authorized_head` committed document.
2. **A Source that already holds a stale binding refuses every later apply once this code runs there.** This is the whole-policy audit, which is requirement 4. The live Source HEAD `62b2af5` holds exactly such an entry (`NSC-1167`). Deploying this onto that Source requires repairing that pin first; otherwise every subsequent decomposition apply with a bound dependent refuses loudly.
3. **The post-staging blob and contract-content checks have no dedicated failing test.** They run on every successful re-pinning apply in the valid tests. Forcing a divergent staged blob would need a custom clean-filter fixture. The pre-staging SHA-256 check is exercised by the mutation test.
4. **The migration re-serializes the policy with `canonical_json_text`.** The committed policy is canonical at every measured commit, so the diff is exactly the pin lines. A non-canonical committed policy would be reformatted: content-identical, and still audited and narrow-change-proven structurally.
5. **Cost.** Each apply that rewrites a dependent pays for one committed-tree listing, one `cat-file --batch` for the dependents, and one for the unchanged tasks carrying `tasks` entries.

## 9. Interpretations

- **"Missing binding refuses"** is scoped to machine-approved dependents (`uses_automated_decomposition_authority`) and eligible parents that require a template. A non-machine-approved dependent with no binding is not a migration, per the coordinator. On the real graphs every machine-approved task carries exactly one binding.
- **"Validate every task entry"** means identity for every `tasks` entry whose task is in the proposed graph. Entries for decomposed aggregates are treated as historical: the reader never resolves them, and "already-decomposed keep historical bindings" applies to both maps. Entries for absent tasks are reported, not refused. Measured: 0 stale and 0 orphaned at `027e787` and `1175937^`.
- **"Captured Source commit"** is the materializer's resolved HEAD, cross-checked equal to `apply_graph_delta`'s `old_head`, which in turn equals `expected_head` (section 3.2).
- **Trusted-byte comparison** is by Git clean-filter blob identity, not raw bytes, because of the autocrlf checkouts.
- **Commit trailer.** The brief required `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, which differs from the harness default. I followed the brief.

## 10. Reproduce

- Worktree root: `C:\nscrev\repin-migration`, with `PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1`.
- Tests: the section 5.2 commands.
- Live-shape measurements: `scratchpad\repin-migration-agent\live_shape.py`, `live_policy_health.py`, `live_binding_invariant.py`.
- Replay: `replay_run1.py <code-root> <empty-scratch-dir>`.
- Shared-fixture comparison: `run_red_suites.py <tree>`.
