```text
VERDICT: FIX FIRST
```

The fix closes the gap on both launchers, the tests fail before and pass after, and `--env` lets nothing extra through. Three things need fixing before merge: a new refusal on the live pooled path, the commit identity, and the missing report.

## Findings (most severe first)

- **[major] `Pipeline/TaskDecomposition/live_decomposition.py:245,282` — `_SAFE_MODEL` now also gates the pooled path.** That path is used at `host_decomposition_launcher.py:175` and `decomposition_transport.py:92`.
  - A pooled run is byte-identical to base only when the model id fits `[A-Za-z0-9._:-]`. **Reproduced, base vs head, on the production builder.**
  - With `NSC_CLAUDE_MODEL=claude-opus-5[1m]` (a real Claude Code id form), `anthropic/claude-opus-5` or `…@20260801`, base builds the pooled argv for `claude,claude` and `codex,claude`. Head raises `ValueError: model value … is not one plain model id`.
  - The AssistantControl builder uses the same renderer and refuses these ids when called directly. My pooled AssistantControl probe stopped earlier, at the fake lease path.
  - `provider_configuration` and the pool both accept these ids, so the refusal fires after the leases are reserved.
  - Theoretical, from reading the code, not run:
    - In the production launcher the error escapes `except OSError` at `:629`. `_cancel_unstarted_pool` never runs, so the reservation is stranded until reclaim. The outer handler at `:1469` still releases the task lease.
    - In AssistantControl, `_proves_nothing_started` is false for a `ValueError`, so both conversations are settled and retired on every attempt.
  - Today's ids (`claude-opus-5`, `claude-sonnet-5`) pass, so nothing live breaks now.
  - This is a new blocking gate reachable from operator input, with no recorded agreement from Vincent. The character check adds no safety here: argv is a list, there is no shell, and the value always follows `NAME=`.
  - To fix, validate where the model is resolved, before reservation or claim. Or keep the value regex on the unpooled branch only and leave the pooled renderer as it was (`if value:`). Add a pooled test with a `[1m]` id whichever you choose.

- **[major] Commit identity.** `38a9f1e94` is authored and committed as `Pipeline Maintainer Agent <pipeline-maintainer@nsc.invalid>`.
  - `validated_agent_git_identity()` returns `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`.
  - The `nsc.invalid` domain appears nowhere in main's last 40 commits. Guide 2.1 says "never invent one".
  - Fix with `git commit --amend --reset-author` using the validated identity. **Reproduced.**

- **[major] The fix report and problem entry do not exist.**
  - `C:/nscrev/reports/mixed-provider-model-env-report.md` is absent.
  - A 0-byte `mixed-provider-model-env-review-20260918.md` sits in that folder, and `nsc-pipeline-problems.md` has no entry for this defect.
  - Guide 2.5 requires the report: reproduced or theoretical, failing-before and passing-after per test, risks, and Vincent's agreement to new gates.
  - I reviewed against the brief and the commit message instead. **Reproduced.**

- **[minor] `mixed_provider_mutation_check.py:170-186` — the harness never runs the unmutated copy first.**
  - "Caught" only means a non-zero exit. **Reproduced.**
  - In my first replay I put `temp` inside the copy root. The pool smoke suite then failed with "pool state must be stored outside the repository working tree", and all four production mutations read as "caught" for that unrelated reason.
  - Under the harness's own sibling layout the baseline is green and every catch is real, so today's 11/11 claim holds.
  - Add one baseline run that must pass before any mutation. For the script suites, check that the expected test name appears in the output.

- **[minor] Test and harness details.**
  - `mixed_provider_mutation_check.py:80` — the "empty values forwarded" label is wrong. With that mutation an empty value is refused by `_SAFE_MODEL`, not forwarded. The test still goes red, so the drop behaviour is pinned.
  - `:9` — the docstring says "COPY of the two files"; it copies all of `Pipeline/`.
  - `:143` — the added `subprocess.run` has no `CREATE_NO_WINDOW` (checklist item 6). It is a console dev tool, but the rule says every added subprocess.
  - `decomposition_session_pool_smoke_test.py:610` — `except BaseException: pass` swallows `KeyboardInterrupt` and `SystemExit`. Use `Exception`.
  - That same test checks only that both names reach the builder non-empty. It does not check they equal the host's resolved values. Pin the environment and compare.

- **[minor] Propagation.**
  - `Pipeline/TaskDecomposition/README.md:37` still documents the model variables without saying the launchers now forward them.
  - The new record key `provider_environment` has no reader, and pooled records carry no model. There is no closed schema, so nothing breaks.
  - `decomposition_transport.py:33,119` adds an alias and a `MODEL_ENVIRONMENT_NAMES` re-export that nothing uses.
  - Behaviour change to note in the report: a host `NSC_CLAUDE_MODEL=""` on an unpooled run used to fall through to the container default. It now raises `DecompositionPreflightError` on the host. This is arguably better, but it is a change.

## Your six questions

1. **Gap closed on both launchers?** Yes.
   - The AssistantControl caller and transport, and the production call site and builder, all forward the models.
   - Reverting any one of them turns a named test red.
   - There is no third builder. `round-robin-decompose` and `*-decompose` commands are built only in those two files.
   - `local_execution_fence.py:560` already accepts the model `--env` pairs without requiring a lease mount.
   - `compose.yaml` has no passthrough for the model variables, so the root cause as described holds.

2. **Pooled path broken?** Not for today's ids. It is for the ids in finding 1.
   - You have forbids and allows the right way round. AssistantControl refuses a mixed pair with a pool assignment.
   - Production builds a pooled `codex,claude` argv and resolves on the host only when `pool_assignment is None`.

3. **Harness.**
   - All 11 anchors match exactly once in the current files, and none is a no-op.
   - It copies only `Pipeline/` into a `TemporaryDirectory` under `TEMP`. It never writes to the clone.
   - A kill mid-run can only orphan that temp folder. The clone was clean after my run and nothing was left in `TEMP`.
   - Its weaknesses are in the fourth and fifth findings above.

4. **`--env` hole.** Nothing got through. I tried:
   - a third name, a lowercase name, trailing space, NUL, and `NAME=x` as a name;
   - an `=` inside the value (refused, so Docker's first-`=` split never sees it);
   - a leading dash, whitespace, newline, shell metacharacters and non-ASCII;
   - 129 characters (128 passes);
   - int, bool, bytes, list and a `str` subclass as the value.
   - Mixed-type keys raise `TypeError` rather than `ValueError`; they are still refused.

5. **Resolving on the host.**
   - Reservation and launch both call `provider_configuration` in the same process, moments apart, so I see no real window where they disagree.
   - The record holds the resolved dict, and the renderer either forwards exactly that or raises.
   - The key is written before `build_compose_command` runs, so a refused launch leaves it on a record marked `failed`.

6. **Tests.**
   - Retargeting the old argv test was the right call. Nothing was lost: the verbatim no-model argv survives in `test_cross_provider_command_without_models_is_unchanged`, and the pool refusal has its own test.
   - Against base production code only `test_cross_provider_launch_carries_both_resolved_models` is a behavioural FAIL; it reproduces the bug. The rest error because the new API does not exist yet, which is expected for a new parameter.
   - `test_cross_provider_launch_names_only_the_providers_in_use` tests only the resolver, despite its name.

## Tests re-run by reviewer

`TEMP` and `TMP` were `C:/nscrev/tmp/rev-mpe`.

- **Head, author's clone:**
  - `test_decomposition_transport` 15 OK
  - `test_decomposition` 40 OK
  - `decomposition_session_pool_smoke_test.py` 14 PASS
  - `host_decomposition_launcher_smoke_test.py` 20 PASS
  - `mixed_provider_mutation_check.py` 11 of 11 caught, exit 0
  - `git diff --check` clean; `compileall` rc 0
- **Base `255951482`, my clone `C:/nscrev/review-tmp/mixed-provider-env-base`:**
  - transport 9 OK
  - pool smoke 10 PASS
- **Base production code with head's tests:**
  - transport failed with 12 errors
  - `test_decomposition` failed with 1 failure and 2 errors
  - pool smoke exit 1
- **Not run:** `taskcontrol validate`, the GauntletView suites, Docker, Unity, providers.
- **Not verified:**
  - the in-container half of the root cause, which is reasoned from `compose.yaml` and the code;
  - the lease outcomes in finding 1 for both launchers, reasoned from the code;
  - the pooled refusal through the AssistantControl builder, which shares the renderer.

## Scope check

- **Intended files only:** yes. Eight files under `Pipeline/`, no whole-file churn, no BOM, and CRLF blobs consistent with their siblings.
- **New blocking gates:** yes, three, none recorded as agreed with Vincent.
  - The pooled-plus-`provider_environment` refusal cannot be reached from the real callers.
  - The name allow-list is harmless, because the pool only emits the two model names.
  - The value regex is finding 1.
- **Temp under `C:\NSC`:** none. I only read there.
- **Identity:** not OK (second finding).
- **Windows:** no `DETACHED_PROCESS`. The one added subprocess, in the harness, lacks `CREATE_NO_WINDOW`.
- **Author's clone:** still clean at `38a9f1e94` on `fix/mixed-provider-model-env`. My `compileall` run wrote git-ignored `__pycache__` folders there, which I left in place.
- **My scratch:** the base clone stays under `C:/nscrev/review-tmp` for the re-check. I removed my mutation copy.
