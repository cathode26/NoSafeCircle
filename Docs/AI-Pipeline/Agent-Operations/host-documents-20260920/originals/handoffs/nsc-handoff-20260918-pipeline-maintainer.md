# Pipeline Maintainer handoff — 2026-09-18

The queue, the branches and the test results are in `C:\NSC\agent-state\pipeline-maintainer-agent.md`.
This file is only the part a successor cannot recover from the guide, the memory, the branches or the
code — and, mostly, the part where **the code itself will mislead them**.

## 1. Things in main that are false, and will be believed

A newcomer reads these and stops. Every one cost real time this week.

- **`run_crew.py`'s budget comment says a host `NSC_<ROLE>_TIMEOUT_SECONDS` "never crosses the
  boundary" into a containerised crew.** It is false and always was.
  `execution_bridge.py:468-472` forwards every variable of that shape with `--env`, and has since
  `6ec42e371` on 2026-09-12 — five days *before* the comment denying it was written. Corrected only
  on branch `fix/crew-resume-interrupted-role`; **main still lies**. `docker compose run --env`
  supplements a service's static `environment:` block rather than being blocked by it, which is the
  single fact that would have prevented two separate false alarms.
  **If a peer asks you to add an `NSC_*` passthrough to `compose.yaml`, they have read that comment.
  The fix is to the comment, not to the config** — and on the decomposition service specifically,
  adding one would break a working path (§2). Two peers have asked so far; both were right that
  something was wrong and wrong about what.
- **`worker_state`'s docstring says settle "verifies the host process and the run's containers are
  gone".** Overstated: `worker_settlement.py:84-90` swallows the container inventory's RuntimeError.
  The host check is real; the container check is best-effort.
- **A merged commit (`b7be8f6ad`) cites `source_update._require_settled_worker` as precedent** for
  treating a settled worker as proof for a launch sharing its run id. That function never consults
  `worker_history` and refuses the retired shape outright. The precedent does not exist.
- **`fee7f98cb` claims retire leaves "the prepared record a fresh preparation would produce".**
  It does not: `scope` remains, and until `c92d141bb` so did `launch`.
- **The contract locality auditor looks live.** `run_crew.py:2701` guards it with
  `if "contract_locality_auditor" in required_roles:` and **no profile has carried that role since
  `6e718ece2` on 2026-09-14** — the prompt, schema, role class and audit block are all unreachable.
  **The deletion is already made and staged**, on `fix/retired-auditor-test-debt` (`55f61230c`
  removes the code, `ca13f7511` and `c0d6dc1e2` fix the tests that expected it). That branch also
  makes `execution_crew_smoke_test` pass, so it clears one of the five red suites. Verify whether it
  merged — `git branch --contains 55f61230c` — before touching anything here. Do **not** resolve the
  question by quietly editing tests to match main, and do not re-decide it: I made that call on
  09-17 and then forgot, and told two peers it was open.
- **`exclusive_resources` obeys two different rules, and reading the wrong one sends you the wrong way.**
  `work_graph_validate.py:442-461` permits a resource claimed by several tasks provided a
  `resource_groups` entry matches the claiming set exactly — so the graph allows sharing. The
  decomposition path enforces something stricter: children must **exactly partition** the parent's
  resources, and a child naming a file the parent does not list fails with
  `missing=[] extra=[...]`. Four NSC-007 round-2 rejections were that, not duplication. A newcomer
  who reads only the validator will conclude sharing is fine and misdiagnose every one of them.
  Related and still true but NOT the cause: `round_robin_decomposition.py:568-583` gathers child
  claims with a set union, so it cannot see a resource claimed twice. Latent, unfiled.

- **`TaskDecomposition/README.md:37`** documents `NSC_CLAUDE_MODEL (default claude-sonnet-5)` and is
  silent on host versus container. That silence *was* the question in a three-round argument.

## 2. Fixes deliberately NOT made — do not "finish" these

- **`scope` refusing a settled-but-unretired worker is correct.** It is not the third instance of a
  defect family. The explicit acknowledgement is the design; the bug was that `retire-worker` did
  half the job. A branch that fixed `scope` (`fix/settled-worker-not-underway` 7165353ae) was
  dropped on purpose, and the reason survived only inside one session's transcript — which is how it
  came back to its own author as though someone else had decided it.
  **You will recognise this by the refusal text:** `worker or candidate work is already underway;
  previous scope preserved`. That sentence means *run `retire-worker <task> --run-id <id>` first*,
  and it is the single most misleading string in the system — three agents read it as a defect in
  one night. Making it say what to do is §7 item 3.
- **Do not add an `NSC_CLAUDE_MODEL` passthrough to `compose.yaml`.** On the pooled path the
  transport already injects it, and a host value disagreeing with what the leases were reserved for
  makes the container fail closed. **This is not in tension with the mixed-provider gap in §3, and a
  reader who takes it as a blanket "the model always arrives" has the same false belief this entry
  exists to prevent.** Pooled same-provider runs get the model; mixed runs get nothing, and the fix
  for those belongs in the transport, not in compose. The model is part of the `SessionScope` identity, so a rung is chosen at *reservation*:
  export before `prepare`, not before the run.
- **Do not build a zero-test-selection guard for Unity.** `run_unity_tests_clean.ps1:524` and
  `record_delivery.py:405` both already refuse `total == 0`. The bare `exit 0` people see is raw
  Unity's, not the gate's. (`Stop-WithCode` writes only to stderr while "VALIDATION PASSED" goes to
  stdout — that asymmetry is what makes the gate look absent. One line would fix it.)
- **Do not build a general `--dry-run` that explains refusals.** 61 `ExecutionBridgeError`, 233
  `CrewBlocked` and 20 `CrewWorkerError` sites; it would become a second implementation that drifts.
  A narrow `explain-launch` sharing `_command()` is the defensible version.
- **The record repair script is no longer owed.** `d6f3edd01` made the readers discount a launch the
  record proves finished, so records retired in the old flat shape (NSC-046) are correct as they sit.

## 3. Known, unfiled, and dated

- **2026-09-19: a latent defect becomes live.** (Corrected 2026-09-18: there are two Codex
  accounts, resetting on the 19th and the 22nd. Documents naming only one date were each right about
  a different account. The trigger here is whichever reset lets a mixed-provider run start, so the
  19th.) `decomposition_transport.py:50-58` injects
  `provider_environment` **only when the run is pooled**; pooling is forced for same-provider pairs
  and forbidden for mixed. Every run today is `claude,claude` and works. When Codex returns,
  `claude,codex` runs get no `--env` and silently fall back to `claude-sonnet-5`. **The escalation
  ladder's top rung is a mixed-provider rung, so it is the rung that silently does not escalate.**
- **A worker's lifetime and the sum of its role budgets are unrelated numbers.** Lifetime is 3600s;
  the role walls already sum to 16800s. A role hitting its own wall ends cleanly and writes
  `crew_result.json`; the bridge lifetime kill writes nothing. Raising a role budget therefore trades
  a loud failure for a silent one — which is what `b35e8c40b` did, and why `fix/validator-wall-budget`
  must not merge.
- **`prepared_refresh` and `worker_launcher` still disagree, in the opposite direction**, over a
  `spawn_failed` launch that settle has settled. Spawn failure plus a source advance reproduces the
  NSC-046 hole.
- **Retiring forecloses `restore-candidate`** and retire has no undo. Restore *before* retiring if a
  rejected run's patch might still be wanted.
- **`graph_controller` still has its own `worker or launch` fallbacks** (:763, :969, :1248, :1757),
  unconverted. Inert while dispatch is DISABLED; a real defect if the controller is unparked.
- **Five suites are red on main**, all pre-existing: `test_viewer` (CI runs 2 of its 57 methods by
  name), `test_scope`, `execution_crew_smoke_test`, `prompt_context_reduction_smoke_test`, and
  `process_runner_smoke_test` (`signal.SIGKILL` does not exist on Windows).

## 4. The habit that caused most of tonight

Four wrong runtime diagnoses in one evening, by three agents, every one from reading a single static
artefact and stopping: a code comment, a compose file, one stream of a process's output. Each was
settled in seconds by reading the launcher or running `docker inspect` on a live container. **Never
conclude what a process receives from the config it nominally uses — read the code that builds its
command.** And a test can be theatre: three of five hunks in one of my own commits were pinned by no
test at all, and a new test passed against unfixed code until it was registered in a suite's
hand-written `main()` list. Revert each hunk alone and confirm something fails.

## 4b. Vocabulary this file uses as if you know it

A stranger given only these documents could not follow these, and each one is load-bearing above.

- **Pooled.** A run whose provider conversations come from a session pool: the host reserves a lease
  per role before launching, and the container is handed only those leases. Same-provider pairs are
  forced to pool; mixed pairs are forbidden from pooling. It matters because the pooled path is the
  one that forwards `provider_environment` with `--env` (`decomposition_transport.py:50-58`), which
  is why the model reaches a `claude,claude` run and not a `claude,codex` one.
- **The dispatch sequence, which exists in no document and should.** To re-run a task whose previous
  run ended: `settle-worker` (if the run has not been settled) → `retire-worker` → `refresh-prepared`
  → `scope` → `reserve` → `start-worker`. Each refuses if the one before it has not happened, and
  the refusals do not say so. Making that sequence discoverable is §7 item 3 and item 4.
- **"The record proves finished."** The record is the task's JSON under the checkouts `records/`
  directory. A run is proven finished when a worker entry — live in `worker`, or archived in
  `worker_history` — has `status` of `failed` or `stopped`, `capacity_released: true`, and a
  `settled_at` stamp. `settle-worker` writes the last two only after checking the host process is
  gone. The predicates are `is_finished_worker` / `is_finished_launch` in
  `Pipeline/AssistantControl/worker_state.py`; import them rather than writing a fifth answer.
  Caveat already noted in §1: the container half of that check is best-effort.
- **The five red suites are noise for your work and a problem for the fleet.** They fail on main
  without any change of yours, so do not treat one as a regression — but always confirm that by
  running it at the base commit, because I twice assumed and once was wrong. They matter because CI
  does not run them (a hand-maintained list), so nothing else will notice when a real regression
  joins them. One of the five is already fixed on `fix/retired-auditor-test-debt`.

## 5. Operating notes worth the tokens

- Fable runs on the **Gmail** account: `claude -p --model claude-fable-5-1 --agent pipeline-reviewer`.
  Agent-tool subagents spend the scarce desktop account instead. Trust is per-directory; a fresh
  scratch clone needs it again (`C:/nscrev/tmp/trust_clones.py`).
- **Never combine the Bash tool's `run_in_background` with `nohup … &`** — the shell returns instantly,
  the tool sees exit 0, and the job dies. Use the flag alone.
- Give every background reviewer **its own clone**; they check the working tree is clean and will
  report a dirty one against you.
- **There is a git stash in C:/nscrev/ci-134-fix that is already superseded — do not apply it.**
  `stash@{0}` "interrupted-wip-preserve" was taken while rebasing onto a newer main; its content
  was re-derived and committed as `072d9329c`. Applying it would resurrect a stale copy of work
  that is already on `fix/crew-resume-interrupted-role`. A stash is invisible to every check in
  this file, which is why it is written down here.
- Several suites write fixtures under `C:\NSC` unless `TEMP`/`TMP` are redirected.

## 6. Open ideas Vincent raised (from the digest; nothing else owns "ideas")

Never delete a closed one — a deleted idea comes back as a fresh idea at the next digest.

- **OPEN — "Do you want the Docker images updated too? I assume it needs to be"** (2026-09-17
  06:21 UTC, immediately after "Codex has been updated"). I can find no answer to this anywhere in
  the session, and no record of the images being rebuilt. If the images bundle the Codex CLI, they
  are stale by however much Codex moved on 09-17. **Ask him; do not assume it was handled.**
- **OPEN — "What are the changes in the assets? ... Ask the Game Agent"** (2026-09-17 06:26 UTC).
  Whether the Game Agent was asked is not recoverable from my side. Likely belongs to the Game
  Agent now, but it was addressed to me.
- **OPEN — "how can we let agents get information about what the pipeline can do"** (09-18 07:50).
  Answered by a Fable design consultation, not built. Its recommendation is item 1 of §7.
- **CLOSED 2026-09-18 — "Do we need a better undo tool?"** Asked which single capability he
  wanted, he chose the record-level reopen. He then widened it in his own words: *"We should be able
  to fuck up in our project and reset."* So it is **both halves for real tasks** — revert the task's
  commits *and* return its record to a dispatchable state — not a choice between them. The reason
  that matters: reverting commits while the record still blocks re-dispatch reproduces the four-gate
  mess of 09-17, and would look like a working reset while leaving the task unrunnable. Relayed
  through the Documentation Agent, board `H-20260918-09`. Design with Astra once Codex returns; see
  `[[record-level-undo-still-owed]]`.
- **CLOSED 2026-09-18 — "do we need clearer instructions or a RAG"** Answered no for behaviour
  questions: three of four wrong answers that day were sitting in authoritative prose, so an index
  would have served them faster and wider. A lexical `git grep` is what settled each one.

## 7. Queued and never built

In the order I would do them. Nothing here exists yet; check before building.

1. **The launch record.** Every compose launcher writes its argv, the environment it forwarded, and
   `env_present_not_forwarded` next to the run record. Vincent endorsed the shape ("examples of what
   works is good"); a Fable design pass ranked it the first thing to build, ~180 lines with tests.
   It is the artifact that would have ended all four of 09-18's arguments in one command.
2. **Lifetime-aware role budgets**, replacing `fix/validator-wall-budget`, which must not merge.
3. **`scope`'s error text** — "a settled worker must be retired before re-scoping: run retire-worker
   <task> --run-id <id>". Agreed with the Game Agent and Documentation Agent; needs no ruling.
4. **The reopen command** (§6, CLOSED item). Smaller than it was: `c92d141bb` and `d6f3edd01`
   already did the launch half. What remains is dropping stale scope and admission, and the refusal
   list — which is the part worth Astra's review after 2026-09-22.
5. **The five outstanding review items on `fix/crew-resume-interrupted-role`**, listed under
   OUTSTANDING in the agent-state file. That branch is not blocked by anything or anyone: address
   the five and send it for re-review. The major one is real — the Claude max-turns classification
   sits on a path only reached when the CLI exits 0, so in production it may never fire while a
   green test says it does. **The resume machinery itself comes after that branch merges**; do not
   start it first, which is the natural reading of "make the crew restartable".
6. Decomposition part 2 — Vincent put it last on 09-18.

**Three tools were queued to this role and never built.** Verified absent on disk 2026-09-18; only
`run_job.py` exists, at `C:/nscrev/job-tools/run_job.py`. Briefs are in `C:\nscrev\reports\handoffs\`:

| tool | board row | brief | why it matters |
|---|---|---|---|
| `ask_astra.py` | H-20260917-19 | `ask-astra-tool-brief-20260917.md` | **Blocks two things.** Both the reset design and every "ask Astra when stuck" escalation are done by hand without it |
| `new_task.py` | H-20260917-25 | (see board) | drafts only; the GER Agent's `new_task_commit.py` stays the committer |
| `task_run.py` | H-20260917-27 | (see board) | — |

A brief existing is not the tool existing, and a board row saying "build X" proves someone was
asked. Check `find C:/nscrev C:/NSC -maxdepth 3 -name '<tool>.py'` before assuming any of them ran.

**Four more in this lane, from a Fable consultation the Decomposition Agent ran** (its relay, not
re-derived by me — verify before building):
1. `review_prompts.py` carries **no resource-ownership rules at all**, while `prompts.py`'s author
   prompt has them at :63-72. Share one fragment between both so they cannot drift.
2. `policy.py`'s partition check — **partly done** by `fix/partition-defect-names-itself`
   (`59d41bf9a`), which splits the message into three named conditions. Still open from its list:
   name the *claiming children*, and add a deterministic `.cs`/`.cs.meta` same-owner check, which
   the author prompt demands in prose and nothing enforces in code.
3. `correction_eligible` (`round_robin_decomposition.py:1127`) requires `round_number == 1`, so a
   round-2 deterministic failure never gets a correction pass.
4. `max_calls=2` is hardcoded (`decomposition.py:353,601,634,662`), and a revise verdict at the call
   limit becomes `needs_human` rather than `review_ready` — so **any** revise verdict on that path is
   structurally doomed even when the revision is correct. Raising it is a bigger call than the rest.

**Two housekeeping items** flagged by the Decomposition Agent's own stranger test, neither verified
by me: a stale pre-pooling copy of `decomposition.py` in a leftover checkout at
`C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\nsc074-unity-validation-f7cb0f47\`
that misleads a grep of the real one; and an unapplied `review_ready` decomposition record appearing
to flip a task's `taskcontrol states` value to `aggregate`, which is in `too_hard_benchmark.py`'s
SKIP set and could hide a flagged task from triage. Observed 2-for-2, not confirmed from source.

## 8. Claims I made that turned out to be false

Every one is corrected with the people who heard it; listed so a successor recognises the shape
rather than to keep score. All four were the same move: read one artefact, stop, assert.

| Claim | Heard by | Reality |
|---|---|---|
| A host `NSC_<ROLE>_TIMEOUT_SECONDS` cannot reach a containerised crew | Vincent, Documentation Agent | `execution_bridge.py:468-472` forwards it; the comment I quoted was false when written |
| A zero-test Unity gate passes silently | fleet memory, Game Agent | Both the runner and `record_delivery` refuse `total == 0`; I propagated a peer's claim before checking |
| The host `NSC_CLAUDE_MODEL` is "ignored by design" | Documentation Agent | `live_decomposition.py:203` reads it on the host; it is the input to the reservation |
| The NSC-046 repair script is still owed | Game Agent | `d6f3edd01` made it unnecessary; the Game Agent was still waiting when I found this |
| The `execution_crew_smoke_test` fix is "staged" in a scratch script | Release Agent | It is committed on `fix/retired-auditor-test-debt` since 09-17; I had forgotten writing it |
| Deleting the unreachable auditor code is "a design call for whoever retired it" | Release Agent, Game Agent | `55f61230c` already deletes it, and it is my own commit |

The last three were found only by the digest pass. **A branch you handed over is invisible to you
once it leaves your context**, and nothing reconciles "suite red on main" against "fix exists on a
branch" — so re-read your own handoff before rebuilding anything.

## 9. Communication profile (built from the job corpus)

Corpus: `C:\nscrev\reports\pipeline-maintainer-job-corpus.md` (45 from Vincent, plus the peer
messages the digest retained — it omits older ones and says how many).

- **"go"** attaches to the specific thing just proposed, not to a category. **A bare "yes"** answers
  the last question asked, nothing wider. **"done"** means he finished a manual step you gave him —
  verify the effect rather than assuming it worked.
- He **types while you are working**, so requests arrive mid-turn. Address them in that turn.
- He **disagrees explicitly and repeats himself when it matters** ("I disagree with this, if the
  task is easy, send it to a cheaper subagent" twice in four minutes). Repetition is emphasis, not
  new information.
- **"How much longer?"** wants a number.
- He **corrects his own typos and expects it noted, not analysed** — "back = bad" was a typo fix and
  I recorded it as a rule, which he had to correct.
- **A short question can carry two readings.** "We want functionality like reset task, but we dont
  need the dummy tasks" meant three different possible builds; asking cost one message and saved a
  wrong one. Ask before designing, not after.
- He runs **Windows PowerShell 5.1**: `&&` is a parse error, use `;`. Give commands in that dialect.
- He asks for **verification by a named model** ("verify your work with Fable") and expects it to be
  adversarial. Fable returned FIX FIRST on every pass and was right every time.

## 10. Re-derive rather than trust (volatile facts)

Branch tips and suite results move. Do not trust the values in any document, including this one:

    cd C:/nscrev/ci-134-fix && git fetch -q origin main && git log --oneline -1 FETCH_HEAD
    git branch --format='%(refname:short) %(objectname:short)' | grep ^fix/
    git merge-tree $(git merge-base main <branch>) main <branch>   # zero conflicts = applies

    export TEMP=C:/nscrev/tmp/x TMP=C:/nscrev/tmp/x PYTHONPATH=C:/nscrev/ci-134-fix
    /c/Python313/python -B Pipeline/AssistantControl/<suite>.py

The five-red-suites claim in §3 was true at ff291624f on 2026-09-18 and one of them
(`execution_crew_smoke_test`) is already fixed on `fix/retired-auditor-test-debt`. Re-run before
repeating it to anyone.
