## Item 2: template re-pin migration, rebuilt to Codex's five-point specification

_Implemented by a delegated Opus 5 agent; independently reviewed by the Claude coordinating session before posting: full production diff read against each of the five requirements, the rollback path read in code, five failing-before tests reproduced on fresh detached worktrees of both baselines, the focused suites rerun on the exact commit, and the combined lineage with the lock fix checked with `git merge-tree`._

**Exact commit:** `36a000c3918680b150d950104c1b21724c0a3dd0`
**Parent:** `027e7879715633119cfc1b65179882d91843a361` (the reviewed trial head; the rejected `1dae47b` is not an ancestor)
**Branch / isolated clone:** `throughput/repin-migration`, worktree `C:\nscrev\repin-migration` of the local clone `C:\nscrev\throughput`. Not pushed, not merged.
**Report:** `C:\nscrev\reports\repin-migration-report.md`

### Exact changed files (5)

| File | Change |
|---|---|
| `Pipeline/TaskGraph/decomposition_policy_repin.py` | new (+626): the authenticated migration, returns bytes only, never writes |
| `Pipeline/TaskGraph/graph_apply_materialize.py` | +106: computes the migration after all graph artifacts and publishes the policy last in the same change set |
| `Pipeline/TaskGraph/apply_graph_delta.py` | +183: publication binding type checks, pre-staging input check, post-staging blob and contract check |
| `Pipeline/AssistantControl/test_decomposition.py` | +649/-1: `DecompositionPolicyRepinMigrationTests`, 12 tests on its own committed-graph fixture |
| `Docs/AI-Pipeline/Stage5-Decomposition-Design/D1C_GRAPH_APPLICATION_DESIGN.md` | +13: one paragraph describing the migration |

The temporary shared-fixture workaround used for non-regression is **not** in the commit (`git diff --name-only 027e787 36a000c -- Pipeline/TaskGraph/graph_delta_smoke_test.py` is empty). `git diff 027e787 36a000c --check` is clean.

### Specification extended to a second face

Run 2 showed the same defect on single-task policy entries: NSC-1167's `tasks` pin (`76e17a2b045d...`) matched its contract bytes before NSC-1166's apply `1175937` rewrote them (`8f7a5bfd43c4...`), and focused validation refused with `authoritative validation policy for NSC-1167 is stale`. The migration therefore covers both kinds of binding: `decomposition_child_templates[<id>].parent_task_contract_sha256` (run 1, NSC-1146) and `tasks[<id>].task_contract_sha256` (run 2, NSC-1167). Codex's five rules apply unchanged to both.

### Where each requirement is enforced (verified in code at `36a000c`)

1. **Verify the old binding first.** Pre-rewrite contracts are loaded from Git at the captured commit. A template must equal `parent_semantic_hash` of that committed contract; a task entry must equal the SHA-256 of those committed bytes. A missing binding refuses for a machine-approved dependent, and for a parent the audit requires to carry a template; any mismatch refuses; a stale pin is never re-pinned. The refusal is raised before the first file is published.
2. **Read trusted policy bytes.** The document is parsed from the policy blob at the captured commit, never the working tree. The working-tree file must equal that blob through Git's clean filters (the checkouts are `core.autocrlf=true`), otherwise the migration refuses. An untracked policy when none is committed also refuses. The captured commit is cross-checked against the apply's own `old_head`.
3. **Make one narrow change.** Only `parent_task_contract_sha256` and `task_contract_sha256` of proven entries change; restoring exactly those fields must reproduce the committed document or the migration refuses. Already-decomposed dependents keep their historical bindings. If nothing is re-pinned the result is `None` and the policy stays byte-identical; an apply that rewrites no dependent never reads the policy.
4. **Audit the entire resulting policy.** `audit_decomposition_policy` runs over the complete proposed graph, and every `tasks` entry is proven against the bytes the commit will contain (changed tasks) or already contains (untouched tasks). A broken unrelated template, variant or task hash rejects the whole apply.
5. **Verify publication.** Canonical bytes, their SHA-256 and their Git blob ID are bound before writing, together with the exact contract text each re-pinned entry names. Immediately before `git add`: HEAD, the committed policy blob at the bound commit, and the published file's SHA-256 are re-checked. Immediately after `git add`: the staged policy blob and each re-pinned contract's staged content are re-checked. Any discrepancy returns `materialization_failed` through the existing pre-commit rollback, which runs `git restore --source <old_head> --staged --worktree` for tracked paths, resets and unlinks untracked paths, and requires a clean committed HEAD. No commit is made.

### Tests

| Codex's required test | Test name(s) |
|---|---|
| valid old binding updates successfully | `test_valid_template_binding_is_repinned_in_the_same_commit`, `test_valid_task_entry_binding_is_repinned_in_the_same_commit` |
| missing binding refuses | `test_missing_template_binding_refuses_the_apply`, `test_missing_task_entry_binding_refuses_the_apply` |
| stale binding refuses | `test_stale_template_binding_refuses_the_apply`, `test_stale_task_entry_binding_refuses_the_apply` |
| dirty policy input refuses | `test_dirty_policy_input_refuses_the_migration` |
| mutation between audit and staging refuses | `test_policy_mutation_between_audit_and_staging_refuses_the_apply` |
| unrelated invalid policy entry refuses the complete apply | `test_unrelated_invalid_policy_entry_refuses_the_complete_apply` (subtests: template naming a task outside the graph; stale `tasks` entry of an untouched task) |
| multiple dependents update correctly | `test_multiple_dependents_of_both_binding_kinds_are_repinned` |
| already-decomposed dependents remain unchanged | `test_already_decomposed_dependent_keeps_its_historical_binding` |
| failure leaves no staged files, commit or partial graph change | `test_refused_migration_leaves_no_staged_file_commit_or_partial_change`, plus a nothing-changed assertion (HEAD, commit count, status, index, tracked content, policy bytes) in every refusal test |

**Failing-before, reproduced by the coordinating session** (fresh detached worktrees, only the final test file copied in, worktrees removed afterwards):

| Base | Test | Result |
|---|---|---|
| `027e787` | valid template binding re-pinned | FAIL: `'Pipeline/TaskReviewAgent/authoritative_validation_policy.json' not found in [...changed paths...]` |
| `027e787` | valid task entry binding re-pinned | FAIL: same |
| `1dae47b` | stale template binding refuses | FAIL: `'materialization_failed' != 'applied'` (the rejected commit overwrote an unproven pin) |
| `1dae47b` | dirty policy input refuses | FAIL: `GraphApplyMaterializationError not raised` (the rejected commit consumed working-tree bytes) |
| `1dae47b` | mutation between audit and staging refuses | FAIL: `'materialization_failed' != 'applied'` (the rejected commit committed the mutated policy) |

The implementing agent's full runs of the class: at `027e787` `Ran 12 tests ... FAILED (failures=13)`, every failure an assertion; at `1dae47b` `Ran 12 tests ... FAILED (failures=11)`, with the valid template and already-decomposed tests passing because the rejected commit did implement those two (neither is a safety test).

**Passing-after on `36a000c`, rerun by the coordinating session:**
- `python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_gauntlet_replay`: `Ran 31 tests in 111.259s` `OK`
- `python Pipeline/TaskReviewAgent/tests/decomposition_policy_audit_smoke_test.py`: `PASS (13 tests)`
- `python Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py`: `PASS (9 tests)`
- `python Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py`: `PASS`

Implementing agent, additionally: `DecompositionPolicyRepinMigrationTests` `Ran 12 tests in 54.641s OK`; `automated_decomposition_replay_smoke_test.py` `PASS (7 tests)`.

**Non-regression on the known-red shared-fixture suites.** These suites already fail at `027e787` because the exact partition rule from `379685b` rejects the shared `graph_delta_smoke_test` fixture (`extra=['logical:new-shared','logical:new-shared']`). With a temporary, uncommitted two-line fixture workaround applied identically, results were identical at `027e787`, on the pre-commit tree, and on the committed `36a000c` in a separate throwaway worktree: graph_apply_plan, graph_apply_materialize and graph_apply `PASS`; graph_undo `PASS (2 tests)`; local_decomposition_apply `OK`; decomposition_authorization `PASS (59 tests)`; graph_delta `exit=1 KeyError: 'logical:new-shared'` and task_id_width `exit=1` (both pre-existing, identical on every tree).

### Deliberately left unchanged

- The audit rules and `parent_semantic_hash` (the migration restates no template, variant or task-entry rule).
- The partition rule from `379685b` and the shared `graph_delta_smoke_test` fixture (a separate semantics decision; see earlier Issue notes).
- `Pipeline/TaskReviewAgent/decomposition_replay.py` and its automated-authority check (see residual risk 3).
- The Gauntlet generators and every existing policy entry.
- No live Source was touched; nothing under `C:\NSC` was written.

### Residual risks and decisions needed

1. **Post-staging refusal has no forcing test.** A mismatch between the staged policy blob (or a re-pinned contract's staged content) and the audited value is checked on every successful re-pinning apply but no test forces a divergent staged blob (it would need a custom clean-filter fixture). The rollback it falls into was verified in code to restore the index and the working tree and to require a clean HEAD.
2. **Scope of "missing binding refuses".** It refuses for machine-approved dependents (`uses_automated_decomposition_authority`) and for parents the audit requires to carry a template. A dependent with no binding that is not machine-approved leaves the policy byte-identical, so ordinary tasks without policy entries keep applying. **Codex: please confirm this scope.**
3. **Regression on the GitHub-backed task-review path (decision needed).** `decomposition_replay.inspect_authorized_decomposition_replay` calls `_validate_automated_authority`, which requires the working-tree policy blob to equal the blob at the authorized pre-apply commit. After a re-pinning apply that check refuses (reproduced on run 1 data). Only `polling_orchestrator` and `host_decomposition_launcher` import that function; AssistantControl, `local_decomposition_apply` and `openai_pipeline` import only `find_exact_d1c_commit` and `DecompositionReplayError` (verified). A proposed design (keep byte identity when the policy is unchanged; otherwise require `already_applied`, locate the exact D1C commit with `find_exact_d1c_commit`, require the working-tree policy to equal that commit's policy and the parent's template to be identical at both commits, and re-run the audit at the D1C commit) needs its own tests. **Decision: fix before merging into canonical main, or document that path as unsupported for re-pinned bindings until then.**
4. **A Source that already holds a stale binding refuses later re-pinning applies** (the whole-policy audit, requirement 4). The disposable `gauntlet-replay/fresh-1160-20260913` Source holds one (NSC-1167). A fresh Gauntlet family starts clean.
5. **Re-serialization.** The migration writes the policy with `canonical_json_text`; every measured committed policy is already canonical, so the diff is exactly the pin lines.
