# The mixed-provider model gap — fix report (2026-09-18)

**Clone:** `C:\nscrev\mixed-provider-env` · **Branch:** `fix/mixed-provider-model-env` @ `cf2ddc5f3`
· two commits off main `255951482`, applies with zero conflicts.
(`38a9f1e94` in round 1 became `b7625cb1d` when its invented committer identity was corrected.)
**Asked for by:** Vincent, 2026-09-18, chosen over two alternatives because it goes live tomorrow.

## What was wrong

A decomposition launched **without a pool assignment** carried no `--env` at all. The container
then ran `live_decomposition.provider_configuration`, which reads `NSC_CLAUDE_MODEL` /
`NSC_OPENAI_CODEX_MODEL` — variables that exist on the host and not in the container — and
returned its documented defaults, `claude-sonnet-5` and `gpt-5.6-sol`.

Nothing failed. The run reported success at a model nobody chose. **The escalation ladder's top
rung is the mixed-provider rung**, so the rung whose entire purpose is escalating to a stronger
model was the one that silently did not.

It was invisible because every run since the ladder was written is `claude,claude`, which is
pooled, and the pooled path did forward the models. The first Codex account returns **2026-09-19**,
which is when `claude,codex` becomes possible again.

## It was in both launchers, in the same shape

`provider_environment` was read only from inside `if pool_assignment is not None:`.

| launcher | unpooled route | status before |
|---|---|---|
| `Pipeline/AssistantControl/decomposition_transport.py` | a mixed pair, which is **forbidden** a pool assignment | unreachable code path for the model |
| `Pipeline/TaskReviewAgent/host_decomposition_launcher.py` | any run without `--enable-decomposition-session-pool` | same, and reachable from the CLI |

Fixing only the first would have left the production launcher broken. The handoff's own lesson —
introduce or fix something, then re-grep for every other place it appears — is what found the
second one.

**One thing I had backwards at first, corrected by reading the code:** the two launchers do *not*
agree about pooling a mixed pair. AssistantControl forbids it; the production launcher allows it
(`decomposition_session_pool_smoke_test` pools `codex,claude` today). So the production launcher's
gap was on its *unpooled* route generally, not specifically on mixed pairs.

## The fix

The allow-list, the renderer and the host-side resolution now live beside `provider_configuration`
in `live_decomposition.py`, so the two launchers cannot answer differently:

- `PROVIDER_MODEL_ENVIRONMENT` / `MODEL_ENVIRONMENT_NAMES` — the two variables, one definition.
- `resolve_provider_model_environment(provider_order)` — the model each named provider resolves to
  on this host, through `provider_configuration`, so the unpooled answer and the reserved answer
  come from one function. Only providers actually in the run are named.
- `model_environment_arguments(environment)` — renders `--env NAME=value`, refusing any other
  variable and any value that is not one plain model id. `--env` is a hole into the container, so
  it is an allow-list and not a passthrough.

Both launchers forward those on the unpooled path, and **refuse** a run that is both pooled and
handed models: a pooled run's model is part of the identity its leases were reserved for, and two
sources would either lose silently or make the container fail closed.

**This is deliberately not a `compose.yaml` passthrough.** On the pooled path a host value
disagreeing with the reservation makes the container fail closed — which is exactly why the
standing instruction is "no `NSC_CLAUDE_MODEL` in compose.yaml", and why this forwards only when
there is no reservation.

The AssistantControl record now carries `provider_environment`, so an unexpected result can be
traced without re-deriving what the host's environment was at launch.

## Evidence

| suite | before | after |
|---|---|---|
| `test_decomposition_transport` | 9 | **15** |
| `test_decomposition` | 37 | **40** |
| `decomposition_session_pool_smoke_test` | 10 | **14** |
| `host_decomposition_launcher_smoke_test` | 20 | 20 (unchanged, still green) |

Also green, unchanged: `test_background_jobs` (67), `live_decomposition_smoke_test`,
`pooled_decomposition_smoke_test` (18), `decomposition_authorization_smoke_test` (59),
`task_id_width_smoke_test` (28).

**Failing-before is proven, not asserted.** `Pipeline/AssistantControl/mixed_provider_mutation_check.py`
reverts each of the 11 pieces of the fix on its own and confirms a named test goes red:

    all 11 pieces of the fix are pinned by a test

It works on a copy of `Pipeline/` (30 MB, not the checkout's 221 MB) and never touches the working
tree, so being killed mid-run cannot leave a guard disabled — a hazard a reviewer found in an
earlier harness of mine today.

The most important of the eleven is `caller passes no models`, which restores the original defect
exactly: the transport fix alone, with the caller passing nothing, is worth nothing.

## One test was retargeted, not extended

`test_cross_provider_command_is_unchanged_and_refuses_a_pool_assignment` asserted the mixed-provider
argv verbatim, under the name *"keeps the exact argv it has always built"*. The argv it pinned was
the defect. Its pool-assignment half is kept; the verbatim-argv half is replaced by
`test_cross_provider_command_without_models_is_unchanged`, which still pins the old argv for a
caller that passes no models. Nothing was lost, and the reason is written into the test.

## Not done

- **`NSC_*_EFFORT`** is reserved for codex at the pool level (`provider_models` carries `"high"`)
  and is not forwarded on either path. Whether an unpooled codex round should get its effort is a
  real question and a separate change; I did not widen the allow-list to guess.
- I have **not run a real mixed-provider decomposition**, because Codex quota is out until
  2026-09-19. Everything above is the command that would be built, proved at the argv level on
  both launchers plus one real `_run_proposal` drive. The first live `claude,codex` run should
  check `actual_model` in the run result, which is the ladder's own verification step.

---

# Round 2 — answering the review (2026-09-18)

Review: `C:\nscrev\reports\mixed-provider-model-env-review-20260918.md`, VERDICT FIX FIRST.
Branch is now two commits: `b7625cb1d` (the fix) and `cf2ddc5f3` (this round).

## [major] The value check also gated the live pooled path — fixed

This was mine, introduced by the fix itself, and it is the finding that mattered.

`_SAFE_MODEL` was `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` and the shared renderer is used by the
**pooled** path too — the one that carries every run today. It rejected real model id forms:
`claude-opus-5[1m]` (the Claude Code long-context id), `anthropic/claude-opus-5`,
`claude-opus-5@20260801`. And it rejected them *after* the leases were reserved, so the
reservation would strand rather than refuse cleanly.

The character rule bought nothing: the value is concatenated after `NAME=` into an argv **list**,
so there is no shell to inject into and a leading dash cannot be read as a flag. It is now a
well-formedness check — not a string, empty, whitespace anywhere, a control character, or absurdly
long — none of which can express a model choice. Nothing that could be a real model id is refused
on either path.

`test_model_values_cannot_smuggle_an_argument` loses its `--privileged` case and gains
`test_a_dash_leading_value_is_a_value_not_a_flag`, pinning that value as **accepted** so the false
threat model cannot return. Real-id coverage added on both the pooled and unpooled paths, in both
launchers.

## [major] Commit identity — fixed

`pipeline-maintainer@nsc.invalid` was invented. The repository's convention is
`No Safe Circle <Role> <role@nosafecircle.invalid>` (27 commits as Contract Maintenance, 5 as Game
Agent, 4 as TaskReviewAgent, 3 as Documentation Agent on the last 40). Both commits are now
`No Safe Circle Pipeline Maintainer <pipeline-maintainer@nosafecircle.invalid>`.

## [minor] The harness never proved the baseline green — fixed

It now runs every suite unmutated first and stops if any is red. The reviewer's own replay is why:
putting the scratch temp inside the copy made the pool suite refuse before a single assertion, and
all four production mutations read as "caught" for that unrelated reason. `caught` only ever meant
a non-zero exit, so without a baseline the whole run could be theatre. Also corrected: the
docstring said "a COPY of the two files" (it copies `Pipeline/`), and the "empty values forwarded"
label described the wrong effect.

## [major] "The fix report does not exist" — it did, and this was my fault

`mixed-provider-model-env-report.md` was written at 15:40; the review was launched at ~15:39 and
ran to 15:49. The reviewer looked into a window I created by launching before writing, and the
0-byte file it found was that review's own `tee` target. Nothing to fix in the branch — the
process lesson is write the report first, then commission the review.

## State after round 2

| suite | before the fix | round 1 | round 2 |
|---|---|---|---|
| `test_decomposition_transport` | 9 | 15 | **19** |
| `test_decomposition` | 37 | 40 | 40 |
| `decomposition_session_pool_smoke_test` | 10 | 14 | **15** |
| `host_decomposition_launcher_smoke_test` | 20 | 20 | 20 |

`pooled_decomposition_smoke_test` (18) and `live_decomposition_smoke_test` green and unchanged.
Mutation harness: baseline green, **11/11 caught**.

## Still open from the review, deliberately

- **`NSC_*_EFFORT` is still not forwarded** on either unpooled path. Codex effort is carried at the
  pool level (`provider_models` holds `"high"`), and widening the allow-list to guess at it is a
  separate decision.
- **No live mixed-provider run yet.** Codex returns 2026-09-19. The first `claude,codex` run should
  check `actual_model` in the run result.
