# Gauntlet fixture defect: a rewritten dependent's decomposition template is never re-pinned

**Commit** `1dae47bea3625280e27170ea398aef9d881d744f`
**Parent** `027e7879715633119cfc1b65179882d91843a361` (`throughput/gauntlet-trial`)
**Branch** `throughput/gauntlet-trial-fixes` (worktree `C:\nscrev\gauntlet-fixes`, not pushed, not merged)
**Author line** `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`

Files in the commit (exactly three):

| File | Change |
| --- | --- |
| `Pipeline/TaskReviewAgent/decomposition_policy_audit.py` | new `plan_decomposition_template_repin`; one docstring paragraph amended; `deepcopy`/`Iterable` imports; `__all__` entry |
| `Pipeline/TaskGraph/graph_apply_materialize.py` | new `_repinned_decomposition_policy`; one call site inside `materialize_graph_apply`; `sys` import |
| `Pipeline/AssistantControl/test_decomposition.py` | new `DecompositionTemplateRepinTests` (5 tests) + 4 module-level fixture helpers; 3 imports widened |

`git diff 027e787 HEAD --check` → clean (no output). Working tree clean. All three files keep `i/lf w/crlf`.

---

## 1. The defect, reproved from live evidence

In the 1140 trial Source (`C:\NSC\GauntletFresh1140-20260912-1`, branch `gauntlet-trial/fresh-e90670d`) the decomposition job for NSC-1146 died in preflight:

```
ValidationPolicyAuditError: decomposition template for NSC-1146 is stale: it names parent contract '555810312bd6f5dd094dd3ca6e0ddba6a74a230d6329ba6b94d6cd8df113468f'; the committed contract is '529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f'
```

Read-only replay of the Source's committed history (generator commit `bdaaa2d153a050…`, apply commit `1289283a58a96b…`) against the fixed code, with the pre-apply policy bytes staged in a throwaway directory because the Source has since moved on:

```
generator commit  = bdaaa2d153a0504c471fbd66afd70f1984b171d9
apply commit      = 1289283a58a96bbc38d606300c7197635c8484ed
AT GENERATION: audit PASSES, 12 templates audited, templates_required=['NSC-1107', 'NSC-1108', 'NSC-1121', 'NSC-1122', 'NSC-1124', 'NSC-1140', 'NSC-1145', 'NSC-1146', 'NSC-998']
policy bytes unchanged by the apply commit: True
AFTER THE APPLY (today): ValidationPolicyAuditError: decomposition template for NSC-1146 is stale: it names parent contract '555810312bd6f5dd094dd3ca6e0ddba6a74a230d6329ba6b94d6cd8df113468f'; the committed contract is '529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f'
stand-in policy equals the committed pre-apply policy: True
REPIN: entries changed = ['NSC-1146']
REPIN: new pin         = 529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f
REPIN: NSC-1146 post-apply semantic hash = 529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f
REPIN: `tasks` map untouched  = True
REPIN: schema_version kept    = '1.0'
AFTER THE REPIN: audit PASSES, 12 templates audited
  NSC-1140: decomposed=True parent_contract_sha256=5f0e09f23444d4e0466c27944ea7f00f45898d77629e0df3e59ea5312dbf6f2c
  NSC-1145: decomposed=True parent_contract_sha256=eac97b1679921601f1e90eb2763cb66129d29570d0a00731ba501b2da3d8ca83
  NSC-1146: decomposed=False parent_contract_sha256=529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f
REPIN of the decomposed parent NSC-1145 returns None: True
```

Contract identities at those two commits (same read-only script):

```
NSC-1146 @ bdaaa2d: rev=1 state=concrete hash=555810312bd6f5dd094dd3ca6e0ddba6a74a230d6329ba6b94d6cd8df113468f
NSC-1146 @ 1289283: rev=2 state=concrete hash=529eeffa5377db6da2c6bcfb30942e9d2fb93e220c2067b61f61c40d90c4e38f
  depends_on before=['NSC-1145'] after=['NSC-1150', 'NSC-1151']
  keys added=[] removed=[]
NSC-1145 @ bdaaa2d: rev=1 state=concrete hash=eac97b1679921601f1e90eb2763cb66129d29570d0a00731ba501b2da3d8ca83
  NSC-1150 provenance.parent_contract_sha256=eac97b1679921601f1e90eb2763cb66129d29570d0a00731ba501b2da3d8ca83
  NSC-1151 provenance.parent_contract_sha256=eac97b1679921601f1e90eb2763cb66129d29570d0a00731ba501b2da3d8ca83
  template NSC-1145 pin = eac97b1679921601f1e90eb2763cb66129d29570d0a00731ba501b2da3d8ca83
```

So the chain is exactly as described: the apply rewrote NSC-1146 (revision 1→2, `depends_on` NSC-1145 → NSC-1150/NSC-1151), its hash moved, and nothing re-pinned its template. NSC-1145's own pin still equals what its children recorded, which is why its applied branch held and only the downstream parent blocked.

One correction to the brief: the `bdaaa2d → 1289283` diff of `Tasks/NSC-1146.yaml` adds and removes **no** keys (`basis` is present in both; the raw diff shows it only because the apply rewrites the file in a different key order). The two keys the apply *adds* are on NSC-1145: `decomposition_children` and `decomposition_requirement_sha256`. Nothing in the fix depends on either reading, because the new pin is taken from the post-apply contract whatever it contains.

## 2. The invariant and the seam

**Invariant.** A decomposition template's `parent_task_contract_sha256` is the semantic hash of the contract that will actually be decomposed, and that is the same value that parent's children later write into `provenance.parent_contract_sha256`.

**Seam chosen: the TaskGraph materializer (`graph_apply_materialize.materialize_graph_apply`), not `AssistantControl.decomposition.apply`.** Reasons:

- The commit is created inside `apply_graph_delta`, and `_require_same_clean_head` runs before materialization, so AssistantControl *cannot* pre-write the policy file — a dirty tree is refused. Writing it after the commit would mean two commits, which breaks the atomic "one `taskgraph: apply …` commit" boundary `_verify_commit_boundary`, `undo_graph_delta`, `decomposition_replay.find_exact_d1c_commit` and `local_rehearsal.rebind_after_local_decomposition` all rely on.
- An artifact returned inside the materializer is staged into the temp staging root, hashed (`output_sha256`), published by `os.replace`, carried through `changed_paths` → `_expected_changed_paths` → `_stage_and_check` → `_create_commit` → `_verify_commit_boundary`, and restored by `_restore_precommit_materialization` on a failed commit — with no new code in any of those. The re-pin therefore inherits every existing atomicity and rollback proof instead of needing its own.
- `local_decomposition_apply` and `graph_apply_smoke_test`-style callers benefit without passing anything, because they all go through the same primitive.

**Where the proof runs.** Before staging, not merely before the commit. `_repinned_decomposition_policy` is called while the artifact list is still being built, so a document that cannot be proven raises `GraphApplyMaterializationError` with zero files staged and zero published — stronger than "no commit, no partial write".

**What computes the re-pin.** `plan_decomposition_template_repin` in `decomposition_policy_audit.py`, so template identity keeps exactly one definition. It:

1. returns `None` when the target repository has no committed policy file;
2. returns `None` when no rewritten dependent has a `decomposition_child_templates` entry — the document is not even shape-checked in that case, so behaviour is byte-for-byte unchanged;
3. skips any rewritten dependent that is already `decomposition_state: decomposed` (its template stays bound to what its committed children record — the audit's applied branch);
4. skips an entry that already names the rewritten contract, and returns `None` if that leaves nothing to change;
5. re-pins the rest to `parent_semantic_hash(rewritten contract)` taken from the **post-apply overlay** (`proposed_by_id`), i.e. the contract the commit will contain, not current HEAD;
6. runs the unchanged `_audit_one_template` on every entry it re-pinned, and raises on refusal.

`parent_semantic_hash` and the audit's rules are unchanged. The only edit to existing behaviour in that file is one docstring paragraph, because "never repairs one" is no longer literally true: the module now *computes* one re-binding (it still never writes the file).

`TaskGraph → TaskReviewAgent` is a new direction, so the import is function-local and only reached when the plan rewrites at least one dependent: the low-level primitive stays free of `downstream_pipeline`/`issue_workflow` on every other apply. It costs ~3.8 s of import once per process on the re-pin path.

## 3. Interaction with `_source_advancement_proof`

`Pipeline/AssistantControl/decomposition.py:105` diffs `Tasks`, `Pipeline/TaskGraph` **and** `Pipeline/TaskReviewAgent/authoritative_validation_policy.json` to compute `authoritative_graph_inputs_unchanged`. **The validation policy file is part of that input set.** Therefore a published re-pin makes every other decomposition proposal reviewed before that commit refuse to apply (`_verify_review` raises `TaskGraph inputs changed after the decomposition proposal`) until it is re-reviewed. That is the correct fail-closed direction — a proposal reviewed against the old template map must not apply against the new one — and it is harmless under the trial branch's one-proposal-in-flight rule (`bdc9a92 AssistantControl: hold the Source lane while a decomposition proposal is in flight`). It is also not a new class of refusal: the same apply already rewrites `Tasks/*.yaml` and `WORK_ID_MAP.json`, which are in the same input set, so any concurrent proposal was already invalidated by the apply itself. `test_the_policy_file_is_one_of_the_authoritative_graph_inputs` pins this behaviour directly.

## 4. Tests

New class `DecompositionTemplateRepinTests` in `Pipeline/AssistantControl/test_decomposition.py`. Fixture: `create_repository` (`Pipeline/TaskDecomposition/tests/test_support.py`) already ships NSC-010 as a decomposition parent and NSC-012 as its active direct dependent, and `decomposed_result` already carries the NSC-012 inbound rewrite. The tests add `provenance.gauntlet_id` to both (machine authority, which is what makes a template required and permitted), turn NSC-012 into a decomposition parent with one exclusive resource, and commit a real `authoritative_validation_policy.json` with generator-shaped templates for both.

| Test | Proves |
| --- | --- |
| `test_an_applied_rewrite_repins_the_dependents_own_template` | audit accepts the dependent's template after the apply; policy file is in the apply commit; the document differs from before in exactly the one entry's one field (asserted structurally *and* as exactly one `-`/`+` diff line); the decomposed parent's entry is untouched; the dependent's own later apply records children whose `provenance.parent_contract_sha256` equals the re-pinned value, and the audit's applied branch then resolves it |
| `test_a_dependent_without_a_template_leaves_the_policy_byte_identical` | a policy file exists but holds no template for the rewritten dependent: apply commit does not touch it, bytes identical, tree clean |
| `test_a_repository_without_a_policy_file_publishes_only_the_graph` | no policy file: published and committed sets are exactly the five graph paths in the historical order |
| `test_a_repin_that_still_fails_the_audit_refuses_the_whole_apply` | a template that claims a resource its parent does not own: `materialization_failed`/`materialization`, `published_paths == ()`, `new_commit_sha is None`, HEAD and tree unmoved, tree clean, policy bytes unchanged |
| `test_the_policy_file_is_one_of_the_authoritative_graph_inputs` | the advancement-proof interaction in section 3 |

### Failing-before (detached worktree at `027e787`, only the test file copied in)

`git worktree add --detach /c/nscrev/before-027e787 027e787`; `git status --porcelain` → `M Pipeline/AssistantControl/test_decomposition.py`; removed afterwards with `git worktree remove --force` + `git worktree prune`.

```
test_a_dependent_without_a_template_leaves_the_policy_byte_identical ... ok
test_a_repin_that_still_fails_the_audit_refuses_the_whole_apply ... FAIL
The shape every disposable TaskGraph fixture and a bare Source has. ... ok
test_an_applied_rewrite_repins_the_dependents_own_template ... ERROR
A re-pin commit is a graph-input change, so other proposals fail closed. ... ok

ERROR: test_an_applied_rewrite_repins_the_dependents_own_template
Pipeline.TaskReviewAgent.decomposition_policy_audit.ValidationPolicyAuditError: decomposition template for NSC-012 is stale: it names parent contract 'af0e973303ec0b5d41907019841b220de336073e72037327c9a2d976572c2895'; the committed contract is '39baafdb58bc447915c445e4f0419d548ab4a962a775b599841fcba064de94ab'

FAIL: test_a_repin_that_still_fails_the_audit_refuses_the_whole_apply
AssertionError: 'materialization_failed' != 'applied'

Ran 5 tests in 13.228s
FAILED (failures=1, errors=1)
```

The synthetic fixture reproduces the live failure sentence exactly. The three unchanged-behaviour guards pass at `027e787` as well as after, which is what makes them guards rather than new behaviour.

### After (at `1dae47b`)

```
test_a_dependent_without_a_template_leaves_the_policy_byte_identical ... ok
test_a_repin_that_still_fails_the_audit_refuses_the_whole_apply ... ok
The shape every disposable TaskGraph fixture and a bare Source has. ... ok
test_an_applied_rewrite_repins_the_dependents_own_template ... ok
A re-pin commit is a graph-input change, so other proposals fail closed. ... ok
Ran 5 tests in 16.005s
OK
```

```
$ python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_gauntlet_replay
Ran 24 tests in 54.347s
OK

$ python Pipeline/TaskReviewAgent/tests/decomposition_policy_audit_smoke_test.py
TaskReviewAgent decomposition policy audit smoke tests: PASS (13 tests)      [exit 0]

$ python Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py
synthetic gauntlet setup tests: PASS (9 tests)                               [exit 0]

$ python Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py
decomposition_graph_semantics_smoke_test: PASS                               [exit 0]

$ python -m unittest Pipeline.TaskReviewAgent.tests.generated_child_scope_test
Ran 4 tests in 3.575s  OK

$ python -m unittest Pipeline.TaskReviewAgent.tests.generated_child_fenced_scope_test
Ran 2 tests in 6.409s  OK

$ python -m unittest Pipeline.TaskReviewAgent.tests.local_decomposition_head_drift_test
Ran 4 tests in 2.165s  OK

$ git diff 027e787 HEAD --check
(no output)
```

## 5. Pre-existing red suites at `027e787` — read this before rerunning

**`python Pipeline/TaskGraph/graph_apply_smoke_test.py` is already broken at the parent commit, before any change of mine**, and so are four sibling suites. A pristine detached worktree at `027e787` with zero modifications gives:

```
$ python Pipeline/TaskGraph/graph_apply_smoke_test.py
  File ".../graph_apply_smoke_test.py", line 200, in create_fixture
    result = validated_result(source.plan)
  File ".../graph_delta_smoke_test.py", line 125, in validated_result
    return validate_decomposition_result(
  File ".../Pipeline/TaskDecomposition/policy.py", line 146, in validate_decomposition_result
TaskDecomposition.policy.DecompositionPolicyError: Child exclusive_resources must exactly partition the parent exclusive_resources (missing=[], extra=['logical:new-shared', 'logical:new-shared'])
[exit 1]
```

Cause: `379685b decomposition: validate complete child resource partitions` added an exact multiset rule that the shared fixture `graph_delta_smoke_test.validated_result` (child resources `["logical:shared","logical:new-shared"]` + `["logical:new-shared"]` against a parent owning only `logical:shared`) violates. It dies in the first fixture, so no test in these suites runs at all:

| Suite | `027e787` | `1dae47b` |
| --- | --- | --- |
| `Pipeline/TaskGraph/graph_delta_smoke_test.py` | exit 1, partition error | exit 1, identical |
| `Pipeline/TaskGraph/graph_apply_plan_smoke_test.py` | exit 1, partition error | exit 1, identical |
| `Pipeline/TaskGraph/graph_apply_materialize_smoke_test.py` | exit 1, partition error | exit 1, identical |
| `Pipeline/TaskGraph/graph_apply_smoke_test.py` | exit 1, partition error | exit 1, identical |
| `Pipeline/TaskGraph/graph_undo_smoke_test.py` | exit 1, partition error | exit 1, identical |
| `Pipeline.TaskReviewAgent.tests.local_decomposition_apply_test` | `Ran 21 tests … FAILED (failures=1, errors=20)`, same partition error | identical failure set (21 signatures, `diff` empty) |
| `Pipeline.TaskReviewAgent.tests.task_id_width_smoke_test` | exit 1, `unexpected child allocation: ['NSC-1140' … 'NSC-1155']` | exit 1, identical |

I did **not** repair that fixture: the one-line change flips resource ownership, and `graph_apply_smoke_test` asserts on `logical:new-shared` resource-group publication at lines 1528/1576, so the repair has its own blast radius and belongs in its own commit.

**Because those two suites are the ones that would normally guard the materializer, I proved non-regression another way.** In a throwaway detached worktree at `027e787` I applied a temporary, never-committed one-line workaround to `graph_delta_smoke_test.validated_result` (child 0 takes `["logical:shared"]`, child 1 takes `[]`), ran the suites, then copied in only my two source files and ran them again:

```
=== BASELINE (027e787 + fixture workaround, no fix) ===
materialize EXIT=0 | graph_apply_materialize_smoke_test: PASS
graph_apply  EXIT=0 | graph_apply_smoke_test: PASS

=== WITH THE FIX (same fixture workaround) ===
materialize      EXIT=0 | graph_apply_materialize_smoke_test: PASS
graph_apply      EXIT=0 | graph_apply_smoke_test: PASS
graph_undo       EXIT=0 | TaskGraph graph undo smoke tests: PASS (2 tests)
graph_apply_plan EXIT=0 | graph_apply_plan_smoke_test: PASS
graph_delta      EXIT=1 | KeyError: 'logical:new-shared'
```

The `graph_delta` `KeyError` is my crude workaround, not the fix: with the workaround alone and both source files reverted, that suite fails identically (`BASELINE graph_delta (workaround only) EXIT=1 | KeyError: 'logical:new-shared'`). So all five TaskGraph suites behave identically with and without this commit, including `EXPECTED_PUBLICATION_ORDER`, the CRLF/artifact-comparison cases, the rollback cases and the undo boundary. The worktree was removed with `git worktree remove --force` + `git worktree prune`.

## 6. Residual risks

1. **The re-pin rewrites the whole policy file through `canonical_json_text`** (`json.dumps(…, indent=2, ensure_ascii=False) + "\n"`, no `sort_keys`). Verified byte-equal to both the committed file on this branch and the live Gauntlet policy at `1289283`, so a re-pin is a genuine one-line diff today. If a future generator ever writes that file with different formatting (e.g. `sort_keys=True`), the first re-pin would reformat the whole file — still semantically correct and still provable, just a noisy diff. The tests assert the one-line shape, so such a drift would surface there.
2. **A corrupt but present policy file now fails an apply that rewrites a dependent.** Absent file → skip; present-and-unparseable → `ValidationPolicyAuditError` → the apply refuses. I chose fail-closed over silent skip because the decomposition preflight already proved that file parseable at proposal time, so unparseable-at-apply means something moved underneath the proposal. This is the one behaviour change reachable without any template.
3. **Layering.** `Pipeline/TaskGraph` now imports `Pipeline/TaskReviewAgent` lazily. It is guarded (`dependent_ids` non-empty) and inserts the repository root into `sys.path` the way `decomposition_policy_audit` and `context_builder` already do, but it is a new direction and an import failure there would surface as a materialization failure (fail-closed) rather than an obvious import error.
4. **The whole-map audit is not re-run by the apply**, only the entries it re-pinned. Deliberate: running the full audit inside the apply would make an unrelated stale entry (production `main` carries twelve template entries) refuse an otherwise valid apply. The full audit still runs in `decomposition_preflight` before any decomposition starts.
5. **No re-pin for a dependent rewritten by something other than a graph apply.** If a human or another tool ever edits a templated task's contract directly, its template goes stale again and the preflight refuses it — unchanged, and correctly fail-closed.
6. **`plan_decomposition_template_repin` reads the target repository's working-tree policy file**, which is the right source inside an apply (the tree is proven clean and equal to HEAD beforehand) but means it cannot be pointed at a historical commit; the live replay staged the pre-apply bytes in a throwaway directory for that reason. Adding a `document=` parameter (mirroring `audit_decomposition_policy`) would remove that wrinkle if a caller ever needs it.
7. The suites in section 5 remain red for reasons that predate this work; the 1140-shaped chain is covered by the five new tests and by the section 1 replay, not by them.
8. **No CI workflow runs `Pipeline/AssistantControl/test_decomposition.py`** — `grep -rn "unittest" .github/workflows/*.yml` finds only the GauntletView discover row, so the whole AssistantControl unittest family (the 19 pre-existing tests included) is operator-run, not gated. The five new tests therefore only run when someone types `python -m unittest Pipeline.AssistantControl.test_decomposition`. I did not add a CI row: that would newly gate CI on a module nobody gated before, which is an infrastructure decision outside this repair. If you want them gated, that row is a one-line addition to `.github/workflows/d1b2-core-deterministic.yml`.
