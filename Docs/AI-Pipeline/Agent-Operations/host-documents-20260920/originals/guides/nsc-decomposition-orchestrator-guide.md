# Decomposition Orchestrator: operating guide

The **Decomposition Orchestrator** splits a task that is too big for one execution crew into child tasks. It works only on tasks marked `execution_scope: needs_execution_decomposition`.

It runs one bounded, two-provider D1B.2 proposal. One model authors the split and a different model reviews it. It then presents the reviewed plan to Vincent, applies exactly that plan to local `main` after his exact-plan approval, and releases the children.

Read `C:\NSC\nsc-pipeline-runbook.md` first: Docker logins, Unity rules, shared rules.

Written 2026-09-16. Commands and guards are verified against `Pipeline/AssistantControl/decomposition.py` and `__main__.py` on `main` `22955c5a8`, plus the live NSC-015 run of 9/15 and the NSC-025/NSC-014 runs of 9/13-9/14.

---

## 1. Authority

**You may, without asking:**
- read everything;
- run zero-cost checks: `taskcontrol`, `inspect-decomposition`, reading round artifacts;
- prepare a proposal brief;
- write your journal sections;
- tell the Task and GER Orchestrators what changed.

**Ask Vincent first:**
- **every paid `decompose` launch.** Get an explicit "go NSC-0xx" in chat, per launch. On 9/14 Claude's permission guard refused a launch even under a delegated role and after another agent claimed standing authorization. On 9/15 it ran after Vincent said "ok decompose 015". Never work around a refusal;
- **every `apply-decomposition`.** That needs Vincent's approval of the *exact* plan (section 6). A `review_ready` result is review-only and authorizes nothing;
- moving a failed decomposition record aside so a task can be retried (section 7).

**Never:**
- hand-edit or renumber `decomposition_result.json` or `graph_delta.json`;
- hand-write child task files;
- edit the parent contract yourself (that is the GER Orchestrator's job);
- run crews;
- push;
- apply two proposals built from the same graph without replanning the second.

---

## 1a. Standing duty: triage every task that still needs work (Vincent, 2026-09-18)

His words: *"The decompositions job should be to read every task that still needs work, then decide if the task is too hard for the
agents to complete. A bench mark for too hard to complete was NSC-007."*

**This is a standing duty, not a request you wait for.** Nobody else reads the whole backlog for buildability. The GER Agent writes
contracts one at a time and the Game Agent dispatches what is eligible; **you are the only role that looks across all of them and asks
whether a crew can actually finish this.**

### What made NSC-007 the benchmark

Measured from its contract **as dispatched at revision 5** - the shape that failed - and from the runs that followed. **Pin a benchmark to a revision, not to a task id:** NSC-007 is now at revision 8 with 13 non-meta resources, and quoting today's numbers would describe a contract nobody tried to build. Four decomposition attempts failed in total:

| Signal | NSC-007 |
|---|---|
| Non-`.meta` `exclusive_resources` | **11 at revision 5** (13 at revision 8; the contract has moved since) |
| Acceptance criteria | **11** |
| Distinct areas touched | **5** (Scripts, Tests, Editor, input actions, the committed scene) |
| Contract revisions | **5 at first dispatch; 8 now**, after four failed decomposition attempts |
| Shape | **deletes existing behaviour and creates its replacement** in the same run |
| Outcome | role budget exhausted at 1200s, then again; never produced a candidate |

**The shape matters as much as the size.** A task that removes a working thing while building its replacement has no safe half-way
point: the crew cannot land part of it. Two of the eleven criteria also depended on files claimed by other tasks.

### The triage, and how to run it

```bash
python -B C:/nscrev/gdd-edit-tmp/too_hard_benchmark.py
```

It ranks every remaining active implementation task against the benchmark on three measurable axes - resources, criteria, areas - and
marks anything meeting or exceeding NSC-007 on two or more. **As of 2026-09-18 that is five tasks: NSC-007, NSC-078 (109 resources),
NSC-098 (37), NSC-009, NSC-077 (7 areas, revision 10).**

**Read the contract before trusting the count.** The axes find candidates; they do not make the decision. A task with 100 resources that
writes 100 independent PNGs is easy; a task with 8 that rewires a scene, a builder and a test fixture at once is not.

**A fourth signal the script cannot see: revision count.** A contract on its seventh or tenth revision is usually a contract nobody can
pin down, which is the same problem arriving by a different road. NSC-077 is on revision 10, NSC-008 and NSC-049 and NSC-055 on 8.

### What to do with a finding

1. **Say which axis fired and why you agree or disagree with it.** "Eleven criteria" is a prompt to read, not a verdict.
2. **Propose the split shape**, not just the split: which half is independently landable, and what the seam is.
3. **Send it to the GER Agent**, which owns contracts. You do not revise contracts yourself.
4. **Never triage a task while a crew is running on it.** A revision mid-run is the one thing everyone here has committed not to do.
5. **Flag the opposite case too.** A task that is too *small* to deserve a crew - code already on main, only a record missing - wastes a
   run just as surely. That is the evidence-pass distinction, and it cost a dispatch on 2026-09-17.

---

## 1b. Escalation ladder: a failed decomposition gets a smarter model (Vincent, 2026-09-18)

His words: *"if decomp fails, use smarter agents. IF those agents fails escalate again to smarter agents."*

### First, decide which kind of failure it was — this is what makes the ladder cheap or wasteful

| Failure | Escalate? |
|---|---|
| **Judgement**: a revise verdict, a split that doesn't hold up, a reviewer rejecting the author's shape | **Yes.** A stronger model is exactly the lever |
| **Mechanical**: a timeout, a gate refusal, a HEAD race, a stale record, a container that never mounted | **No.** Fix the cause and re-run at the same model |

**A smarter model cannot pass a gate that refuses on a field value.** All four failures on 2026-09-17 were mechanical, and escalating any of
them would have spent Opus to hit the same wall. Read `run_result.json` and the progress log before reaching for the ladder.

### The ladder

| Rung | Model | How |
|---|---|---|
| 1 | `claude-sonnet-5` | the default |
| 2 | `claude-opus-5` | `NSC_CLAUDE_MODEL=claude-opus-5` |
| 3 | `gpt-5.6-sol` (Codex) | `--providers claude,codex` with `NSC_OPENAI_CODEX_MODEL`, once Codex quota is back |
| 4 | **Ask Astra, don't run on it** | a read-only advice job (`nsc-codex-jobs-guide.md` 4.4). `gpt-6-astra` runs only through the Codex app's bundled CLI, so it is not a decomposition provider |
| 5 | Vincent | with the three run reports and what each rung actually produced |

**The mechanism, verified at `Pipeline/TaskDecomposition/live_decomposition.py:199-212`:**

```python
model = os.getenv("NSC_CLAUDE_MODEL", "claude-sonnet-5")      # claude
model = os.getenv("NSC_OPENAI_CODEX_MODEL", "gpt-5.6-sol")     # codex
```

All three capability classes (`low_cost`, `standard`, `high_reasoning`) are set to that one value, so **the capability class is a no-op and
the environment variable is the only lever.**

### How the model is actually chosen: at reservation, and only at reservation

Traced end to end, because two agents gave two wrong answers before this one:

```
decomposition.py:44        imports provider_configuration from TaskDecomposition.live_decomposition
decomposition.py:190       calls it ON THE HOST while building the pool owner
live_decomposition.py:203  model = os.getenv("NSC_CLAUDE_MODEL", "claude-sonnet-5")   <- the host variable IS read
decomposition.py:196-200   that value becomes provider_models on the pool owner
pool                       publishes it as the assignment's provider_environment
transport.py:73-76         injects THAT reserved value with --env
```

**So: export `NSC_CLAUDE_MODEL` before the reservation and the ladder works end to end.** No compose change is needed and none should be made.

### DEFECT WITH A DATE: rung 3 will silently run at Sonnet from 2026-09-19

**`--env` injection happens only on the pooled path**, and only same-provider pairs pool (`decomposition.py:563`, `same_provider_role_pair`;
`decomposition_transport.py:60,73-76`, where the injection sits inside `if pool_assignment is not None`).

| Providers | Pooled | Model reaches container | Result |
|---|---|---|---|
| `claude,claude` | yes | **yes**, `--env` injected | the ladder works - this is every run today |
| `claude,codex` | no | **no `--env` at all** | container falls back to `os.getenv("NSC_CLAUDE_MODEL", "claude-sonnet-5")` |

**So rung 3 of the ladder - the mixed-provider rung - drops silently to Sonnet.** It cannot bite today because Codex is out of quota, and it
starts biting the moment mixed runs resume - **2026-09-19**, not the 22nd: there are two Codex Pro accounts, resetting on the **19th** and the **22nd 18:55 local**. Fix the forwarding before using rung 3, or skip straight from Opus to an
Astra advice job.

**Detection either way:** `decomposition.py:505` records `actual_model`. On a mixed run today it would read `claude-sonnet-5` while you believed
you had escalated.

*(History: this was first reported as a universal defect, corrected to "no defect", and finally resolved by an adversarial review as
path-dependent. The universal claim and the universal denial were both wrong; the table above is the measured shape.)*

**The rung is chosen at reservation, so export the variable in the same shell before you run `decompose`.**

**There is no separate step to sequence around, and do not go looking for one:** `prepare` here is `owner.prepare(...)` called *inside* the decompose run (`decomposition.py:629`). **`taskcontrol prepare` is a different, unrelated CLI command** (`__main__.py:53`, creates an isolated task project) - running that instead will not set a model and will confuse the record.

`decomposition.py:190` constructs the pool owner during `prepare`, and the model it reads there becomes part of the **session scope identity**:
`decomposition_session_pool.scope_for` (:393-398) takes `model, effort = self.provider_models[provider_name]` and builds the `SessionScope` from
it. A conversation reserved under `claude-sonnet-5` therefore **cannot** be matched or resumed for `claude-opus-5` — different scope, no match,
and a check-in naming a different model is refused and the conversation withdrawn.

**Two consequences worth knowing:**
- **There is no silent downgrade.** You cannot ask for Opus and quietly get Sonnet's conversation; `provider_environment` and `scope_for` read
  the same `provider_models` on the same owner, so what the transport injects and what the leases were reserved for agree by construction.
- **A variable exported between `prepare` and the run simply has no effect.** Nothing refuses it; it just doesn't reach the scope. That ordering
  is unstated and unenforced in the tooling, which is the only real gap here — and `decomposition.py:505`'s recorded `actual_model` is how you
  detect it after the fact.

So escalating a rung means **a fresh reservation with the new model exported first**, which is not merely the tidy way to do it — it is the only
way the scope can carry the new model.
**Two wrong diagnoses preceded this, both from reading one file:**
- *"`compose.yaml` has no passthrough, so the variable can't reach the container"* (Documentation Agent) — wrong: the transport injects `--env`
  at the command line, which supplements the static block.
- *"the host's variable is ignored by design"* (Pipeline Maintainer) — wrong: `decomposition.py:190` calls the function that reads it, on the host.

The Decomposition Agent settled it by inspecting a live container rather than arguing from source, which is the cheapest evidence available and
should have been the first move for all of us.

**Still verify which rung ran:** `docker inspect` proves the variable arrived; `decomposition.py:505` records
`"models": [author.actual_model, reviewer.actual_model]`, which proves what the provider used. Quote the second one.
### Reporting an escalation

Say which rung, why you judged the failure to be judgement rather than mechanical, and what the stronger model actually did differently.

**The stopping signal is the same validation RULE failing twice, not the same split.** This was first written as "the same split", which
almost never happens, and the mistake cost a real escalation to learn.

**Before a second escalation, if one deterministic validation rule has failed twice - even with different specific values - stop and check
contract completeness instead.** The question: **does the parent offer enough distinct claimable resources for the shape being proposed?**
One test file cannot serve three children, because each child's proof then lives in a file another child owns.

**Worked example, NSC-007, 2026-09-18.** Four attempts failed the exact-partition rule, each naming different files, which read like a
construction or mechanism bug. It was not: revision 7 listed **one** Play Mode test file for a split needing one per child. The GER Agent
added the missing files as revision 8, and **the very next attempt - same model, same command - succeeded clean.** Sonnet to Opus genuinely
helped, producing further and cleaner failures, but it was never going to be the fix.

**The cost asymmetry is why the ordering matters:** the completeness check costs minutes of reading; another escalation costs 15-20 minutes
of run time and a pool session, and may not be the right lever at all.

**And note what caught it:** the misdiagnosis was found by an outside consult, not by the agent that had run all four attempts. See
`C:\NSC\CLAUDE.md`, "Ask a subagent to check your work".

---

## 2. Prerequisites

1. **Docker running**, with both credential volumes logged in: `nosafecircle_claude-config` and `nosafecircle_codex-config` (runbook sections 3.1-3.3). `decompose` runs the `round-robin-decompose` compose service under project `nosafecircle`, which mounts both.
2. **The Source must be clean and on `main`.**
   - `decompose` refuses with `Source must be clean before decomposition`, and `apply-decomposition` needs a clean Source too.
   - Close Unity on `C:\NSC\NSC\NoSafeCircle` first.
   - On 2026-09-16 the Source has **36 phantom-modified wizard and tile files** (line-ending churn). They will block you until Vincent says how to clear them (runbook section 6).
   - On 9/15 a Unity import left 98 untracked `.meta` files; they had to be committed first, as `981002959`.
3. **Codex quota.** Check the Codex app's usage; a run that dies mid-way is paid and still fails.
4. Read:
   - `AGENTS.md`, lines 58-62 (decomposition rules);
   - `Pipeline/TaskDecomposition/README.md`;
   - `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`;
   - `Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md`;
   - the parent contract (`python -B Pipeline/TaskGraph/taskcontrol.py show NSC-0xx`);
   - the journal's newest sections.

---

## 3. The queue on 2026-09-16

`git grep '"execution_scope": "needs_execution_decomposition"' main -- Tasks/` returns:

| Task | Record in `.assistant-control` | State | Next |
|---|---|---|---|
| **NSC-015** Melee Enemy Pursuit, Close-Range Attack and Gameplay Prefab (rev 6, `6fb702b5`) | `NSC-015.decomposition.json` = **failed**, run `nsc015-d1b2-20260915b` | Claude authored, Codex reviewed: **revise**. The two-child split was judged sound, but the candidate (a) weakened several parent validation gates and (b) hid Vincent's open decisions and made an unsupported delivery claim. The reviewer's replacement restores the full parent test surface. Findings: `decomposition-runs\nsc015-d1b2-20260915b\rounds\02\review.json`. | Decide with the GER Orchestrator whether the contract needs a clarification first. Then get Vincent's OK to archive the failed record (section 7), then his go for a new run. |
| **NSC-033** | no record | Contracts corrected 9/14 (`6ba930473`, rev 7). Never run on main. | **After** NSC-015 is applied: NSC-015's split rewrites NSC-033's dependencies. |

Already decomposed (for reference): NSC-014 into NSC-091 and 092; NSC-025 into NSC-089 and 090; plus NSC-016, 021, 026, 029 and 035. `NSC-025.decomposition.json` = failed is a **stale** record from 9/13; NSC-025 was later split by a hand-applied reviewed plan (`2700b0c7`). Leave it.

**Order matters.** Children are numbered against the graph at plan time, and an applied split rewrites dependents' `depends_on`. Decompose, apply, re-check the graph, then start the next one: **NSC-015, then NSC-033**.

---

## 4. Before launching (zero cost)

```powershell
$S = 'C:\NSC\NSC\NoSafeCircle'; $R = 'C:\NSC\NoSafeCircle-AssistantCheckouts'; $REC = "$R\.assistant-control"
Set-Location $S
git status --porcelain                      # must print nothing
git branch --show-current                    # main
python -B Pipeline/TaskGraph/taskcontrol.py validate
python -B Pipeline/TaskGraph/taskcontrol.py show NSC-033      # active, needs_execution_decomposition, decomposition_state concrete
Test-Path "$REC\NSC-033.decomposition.json"  # must be False (any existing record, even failed, blocks a new run)
docker version --format '{{.Server.Version}}'
docker compose -p nosafecircle config --services | Select-String round-robin-decompose
```

Read the parent contract against the policy traps in section 8. If the contract will predictably fail a rule, fix the contract first with the GER Orchestrator. **A rejected run costs about 6-15 minutes of paid provider time.**

Then ask Vincent in chat, briefly:

> "Decompose NSC-033? One Claude author and one Codex reviewer, about 8 min. It proposes only; nothing is applied without your OK on the exact plan."

---

## 5. Launch and monitor

```powershell
python -B -m Pipeline.AssistantControl --source $S --checkout-root $R decompose NSC-033 --run-id decomp-nsc033-20260917a --providers claude,codex --authorize-provider-spend
```

- `--source`/`--checkout-root` must come **before** `decompose`. After it, you get `Specify --checkout-root outside the source project`.
- `--providers claude,codex`: the first is the author, the second the independent reviewer. They must be two distinct providers. `max_calls` is 2.
- The run id must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, and `decomposition-runs\<run-id>` must not already exist.
- **The command's exit code is 0 even when it fails.** Read the JSON it prints: `"status": "review_ready"`, `"failed"`, or `{"status":"command_failed","error":...}`.
- It blocks until the container finishes, so run it in the background and monitor. Container kill timeout is **3600 s**.

Monitor without touching the run:

```powershell
Get-Content "$REC\decomposition-launch\NSC-033\decomp-nsc033-20260917a\stderr.log" -Tail 20   # "D1B.2 round 1 task_decomposer started with claude", "still running: 45s", ...
docker ps --format '{{.Names}}  {{.Status}}' | Select-String decompose                       # nosafecircle-round-robin-decompose-run-<hash>
Get-Content "$REC\NSC-033.decomposition.json" -Raw | ConvertFrom-Json | Select-Object status,run_id,started_at_utc,completed_at_utc
```

- Artifacts: `$REC\decomposition-runs\<run-id>\` holds `context.json`, `decomposition_request.json`, `decomposition_run_result.json`, `progress.jsonl`, and `rounds\01\`, `rounds\02\` (`candidate.json`, `review.json`, `round_result.json`). With a pass it also has `decomposition_result.json` and `graph_delta.json`.
- Timing on 9/15: author 165 s, reviewer 195 s, about 8 minutes end to end.
- Never `docker stop` or `rm` the container. If a run must be stopped, escalate to Vincent.

---

## 6. Outcome: `review_ready`, then Vincent's exact-plan approval, then apply

### 6.1 Present the plan

```powershell
python -B -m Pipeline.AssistantControl --source $S --checkout-root $R inspect-decomposition NSC-033
```

Record from the output: `plan_id`, the artifact SHA-256 values, `apply_source_commit`, the child IDs and each child's title, `depends_on` and `exclusive_resources`.

Summarize for Vincent in plain Unity terms, in a few lines:
- which children;
- what each builds;
- which files each owns;
- how dependencies change.

The full brief goes in a file, for example `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-033\<RunId>\PLAN_SUMMARY.md`.

Ask Vincent to approve **by plan id and hashes**. His rule (9/14): "If anything changed in between, stop; that needs a new plan and my decision."

### 6.2 Re-verify immediately before applying

- `git rev-parse HEAD` equals `apply_source_commit`, and the tree is clean. Otherwise the plan is stale: stop, and report that it needs a replan.
- `inspect-decomposition NSC-033` still reports the same `plan_id` and hashes.
- The child IDs are still unallocated. `taskcontrol.py show NSC-0nn` must fail for each child ID.
- No other agent is mid-way through a Source-moving operation. Check the journal and ask the Task Orchestrator.

### 6.3 Apply (one local commit, never pushes)

```powershell
python -B -m Pipeline.AssistantControl --source $S --checkout-root $R apply-decomposition NSC-033 --run-id decomp-nsc033-20260917a --source-commit <apply_source_commit> --target-branch main
python -B Pipeline/TaskGraph/taskcontrol.py validate
git log --oneline -1
```

It takes the Source integration lock, so it cannot interleave with `integrate` or `sync-candidate`. D1C commits once and fully validates. The record becomes `status: applied` with `applied_commit` and `child_ids`.

### 6.4 Release

- Journal: parent, run id, `plan_id`, `applied_commit`, children with titles, and dependency rewrites.
- Tell the **Task Orchestrator** which children are executable.
- Tell the **GER Orchestrator** about any child whose contract needs design work.
- Children on `main` must be `single_agent`: `Pipeline/TaskDecomposition/policy.py:117` rejects any other child scope. Recursive splitting is **not on `main`**; see the problem list. A child that is still too big needs its contract re-marked `needs_execution_decomposition` through a GER contract revision, then its own run.
- If the parent was GER-held, have the GER Orchestrator `finish` it with `--ready-child` for each executable child.
- Only now start the next queued decomposition. Re-read the graph first.

---

## 7. Outcome: `failed` (a revise verdict, rejection, timeout, or error)

1. **Read why.**
   - The record's `error` field.
   - `rounds\02\review.json`: `verdict`, `summary`, `findings[]` with `finding_id`, `category` and `problem`.
   - `rounds\01\round_result.json`: `rejection_reasons` from deterministic validation.
   - `stderr.log`.
   - A **revise** verdict, like NSC-015's, lands as `failed` because only a clean pass becomes `review_ready`.
   - A legitimate `needs_human` stop **also lands as `failed`** on `main` (a known bug). Read the findings, not the status word.
2. **Classify the failure.**
   - **Contract problem.** The parent's gates are vague, a needed file is not in `exclusive_resources`, or a Vincent decision is missing. Hand it to the GER Orchestrator for a contract revision first. Most failures so far were this.
   - **Author mistake that a clear brief prevents.** For example the author dropped parent gates or claimed delivery. Note the exact findings to feed the retry. The providers see only the contract and repository context, so the fix is usually a contract clarification.
   - **Infrastructure.** Quota, auth, Docker, a timeout. Fix that, then retry.
   - **Design decision needed.** Ask Vincent through the Orchestrator.
3. **Retrying requires archiving the old record.** `decompose` refuses while `$REC\<TASK>.decomposition.json` exists in **any** status ("Decomposition record already exists with status failed; it was preserved"), and there is **no CLI to clear it**. With Vincent's OK:

   ```powershell
   $old = "$REC\NSC-015.decomposition.json"
   $rec = Get-Content $old -Raw | ConvertFrom-Json
   Move-Item $old "$REC\NSC-015.decomposition.$($rec.run_id).$($rec.status).archived.json"
   ```

   - Never delete it, and never touch `decomposition-runs\<old run>`.
   - Journal the move.
   - Relaunch with a **new** run id, for example `...b`, `...c`.

---

## 8. Policy traps that reject real-task splits (read the contract for these first)

These caused most rejections on 9/13-9/14:

- **Exact resource partition.** `policy.py:147`: the children's `exclusive_resources` must **exactly partition** the parent's, with nothing missing and nothing extra.
  - A child that needs a file the parent does not list is rejected.
  - Two children sharing one scene or builder file is rejected.
  - Fix: the parent contract must list every file the split will touch, including new files and `.meta` companions. Each resource must go to exactly one child.
- **Coverage mapping.** Every parent acceptance criterion and validation gate must map to child acceptance criteria of the **same kind**, not to `completion_gates`. Example rejection: "Parent acceptance_criteria/AC-002 must map to child acceptance_criteria entries". Keep parent gates intact; NSC-015's reviewer rejected a split that weakened them.
- **Production-path tests.** Gates must exercise the committed scene (`Assets/Scenes/DoorPrototype.unity`), not an in-memory builder. `DoorSequenceBuilder.BuildCanonical` returns early unless the scene path is canonical.
- **`.asmdef` edits** need an explicit parent claim of that `.asmdef`. NSC-025 was blocked until `3a5651006` added one.
- **New single-owner files are not reserved** by resource groups (the "B2" gap). Name every new file explicitly in child acceptance criteria.
- **Human decisions.** If the parent says a Vincent decision is open, the children must keep that stop. Never claim delivered or verified.
- **Time.** The 3600 s container limit has little headroom for slow provider rounds.
- **Better guidance exists but is not on `main`.** The coverage-mapping and candidate-wide rules (`616ca980`..`c6f7981a` on `codex/coverage-mapping-guidance-20260913`), recursive decomposition and the revision-review third call are unmerged. `main`'s prompts do not contain them; your contract preparation has to compensate.

---

## 9. Other decomposition paths (know they exist; don't use by default)

- **Gauntlet mode** (`run-graph`). The controller runs decomposition as a background job (`nsc-decompose-<hex>`) with one bounded author correction. It is retired for the main project today (runbook section 8).
- **Standalone D1B.2.**

  ```text
  docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id NSC-0xx --providers codex,claude --max-calls 4
  ```

  This is documented in `Docs/AI-Pipeline/START_HERE.md`. It writes to Downloads, has no AssistantControl record, and needs separate D1C application. Note its `nosafecircle-m2a_*` credential volumes differ from the canonical `nosafecircle_*`. Use it only for diagnostics Vincent asks for.
- **Research trees.** `C:\nscrev\realdecomp-tools\`: `rebuild_combined.py`, `run5_launch.ps1`, `offline_preflight.py`, `check_proposal.py`, `peek_round.py`. They were used on 9/13-9/14 to test unmerged guidance on disposable combined clones with their own checkout roots and viewer ports (8823-8826). They are historical; use them only if Vincent wants to test unmerged guidance again.

---

## 10. Reporting

Examples:
- To Vincent: "NSC-015 plan ready (plan `GDP-…`): 2 children, attack cycle and locomotion/prefab. Approve plan `GDP-…`?"
- To Vincent: "NSC-033 rejected: children must split the parent's files exactly. The GER Orchestrator is fixing the contract; nothing needed from you."
- To Vincent: "Need your go to decompose NSC-015 again (~8 min)."

Journal section per run:
- task, run id, providers, Source commit, timings;
- verdict and findings (IDs and one line each);
- the `plan_id` and hashes if ready;
- Vincent's decision (quoted);
- applied commit and children, or the archive move and next step.
