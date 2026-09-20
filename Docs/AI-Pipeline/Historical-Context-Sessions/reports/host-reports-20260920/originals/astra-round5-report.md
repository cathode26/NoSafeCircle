# Round-5 repair of the remaining P1 — for Codex / Astra

**Exact commit:** `e90670da5b5fc19567e1efe1cb655c43de292f4e`
on `throughput/background-decomposition` in the isolated clone `C:\nscrev\throughput`,
directly on top of `ca56dc7f075f1b2fa064b34751cb9878787bc849`.
Not pushed, not merged. No live run, task contract, Unity Asset, Docker container, GitHub
branch or main checkout was touched; no provider was invoked; no `docker` command was
executed — every Docker interaction in the tests and in the behavioural script goes
through the fixture Docker.

**Files changed (5):**

| File | What changed |
|---|---|
| `Pipeline/AssistantControl/background_jobs.py` | the repair |
| `Pipeline/AssistantControl/test_background_jobs.py` | 1 new regression; `FixtureDocker` answers and records `stop --time 10 <id>` |
| `Pipeline/AssistantControl/README.md` | background-jobs section |
| `Pipeline/AssistantControl/CURRENT.md` | dated round-5 section at the top of the background-job entries |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | numbered item 7 |

---

## Failing-before evidence

Method: `git worktree add --detach /c/nscrev/before-ca56dc7 ca56dc7`, the **final**
`test_background_jobs.py` copied in unchanged, only the new test run there; worktree
removed afterwards.

`test_cooperative_stop_verifies_ownership_before_stopping_any_container`, every subtest
and the body:

```
AttributeError: module 'Pipeline.AssistantControl.background_jobs' has no attribute 'cooperative_stop'
```

(6 errors: `container='no labels'`, `'another checkout'`, `'another job'`,
`'another compose project'`, `'another service'`, and the top-level body.)

The seam does not exist on `ca56dc7`, so — as you anticipated — the behavioural proof is
an ad-hoc script (`behaviour_finding_cooperative_stop.py`). It builds a real ticket,
creates a container under that ticket's **exact name carrying another checkout's
ownership label**, replaces `subprocess.run` with a recorder that answers from the fixture
Docker (so nothing real is executed), and calls the child's own
`_interrupt_for(request)()`. On `ca56dc7`:

```
ticket container name  : nsc-decompose-04fa228923e58bcf15861515
foreign container id   : dc01df26b22e46b7
foreign checkout label : aaaaaaaaaaaaaaaa

docker commands issued :
    ['docker', 'stop', '--time', '10', 'nsc-decompose-04fa228923e58bcf15861515']
inspected first        : False
stop issued            : True
stop target            : nsc-decompose-04
stop named the NAME    : True
stop named an exact id : False
interrupt returned     : None
decision recorded      : False
```

No inspect, no ownership check, the stop issued **by name**, and nothing recorded. The
same script on `e90670d`:

```
docker commands issued :
    ['docker', 'container', 'inspect', '--format', '{"id":{{json .Id}},…,"job":{{json (index .Config.Labels "com.nosafecircle.assistant.job")}},"checkout":{{json (index .Config.Labels "com.nosafecircle.assistant.checkout")}}}', 'nsc-decompose-5db87f0986b3c814dd4f1743']
inspected first        : True
stop issued            : False
fixture stopped ids    : []
interrupt returned     : {'decision': 'refused', 'reason': 'other_identity', 'stopped_id': None}
decision recorded      : True
```

---

## Exact behaviour now

`_docker_stop(name)` is gone. The child's cooperative interrupt is
`cooperative_stop(request, docker=None)`:

1. **The ticket is the source of truth.** `_ticket_container_name(request)` and
   `_ticket_container_labels(request)` are unchanged and still decide what the child may
   touch. A ticket whose recorded name, compose project or labels are not the ones this
   job id and checkout derive stops nothing and **asks Docker nothing**:
   `decision: "refused"`, `reason: "ticket_does_not_authenticate"`.
   `_interrupt_for` still calls `_ticket_container_name` at construction, so a bad ticket
   fails the child before it starts working, exactly as before.
2. **One inspect, the reconciliation's own.** `_inspect_container` now takes a
   `DockerRunner` instead of a `JobHost` (its single existing caller,
   `reconcile_provider_container`, passes `host.docker`), so the cooperative stop uses the
   same `_CONTAINER_INSPECT_FORMAT` and the same absent/unreadable/failure parsing. A
   Docker failure is `decision: "refused"`, `reason: "docker_cannot_answer"` with the
   Docker error text; an absent container is `decision: "absent"`,
   `reason: "no_such_container"`.
3. **Ownership before anything destructive.** The container must match the exact name, the
   ticket's compose project, a `-decompose` service for the decompose kind, and **both**
   ownership labels
   (`com.nosafecircle.assistant.job` = the job id, `com.nosafecircle.assistant.checkout`
   = the sha256 of Source + checkout root) as recorded in the ticket's
   `provider_container`. A missing label reads as absent and fails. Any mismatch is
   `decision: "refused"`, `reason: "other_identity"`, with the same
   `container '<name>' carries other identity (…)` wording the removal path uses, suffixed
   `; not stopped`.
4. **The exact id, never the name.** Only then does it run
   `docker stop --time 10 <container id>` — the same semantics as before, applied to the
   id the inspect returned. A container that vanished between the inspect and the stop is
   `decision: "absent"`, `reason: "gone_before_stop"`, `stopped_id: None`; any other
   non-zero exit is `decision: "refused"`, `reason: "docker_stop_failed"`.
5. **Recorded, never raised.** The decision — `container_name`, `expected_labels`,
   `inspected` (id, name, project, service, both labels), `decision`, `reason`,
   `stopped_id`, `error` — is written with `write_record` to
   `cooperative-stop.json` in the run root and returned. `cooperative_stop` catches every
   `Exception` from the decision (recording `reason: "unexpected_error"`) and every
   exception from the record write (adding `record_error`), so the interrupt can never
   raise into `_StopWatch._run`, never becomes `watch.error`, and therefore never turns
   the child's own `stopped` receipt into a `failed` one. The child's receipt path is
   unchanged.
6. **Seam.** `docker` defaults to `_run_docker`, so the child process keeps the real
   runner and the decision is unit-testable with the fixture Docker.
   `cooperative_stop` is exported.

Operator sees: `<run root>/cooperative-stop.json` stating exactly what was inspected and
why nothing was stopped, alongside the unchanged receipt; the container it refused to
touch is still running and still belongs to whoever owns it.

---

## Tests

New regression (fails on `ca56dc7`, passes on `e90670d`):
`test_cooperative_stop_verifies_ownership_before_stopping_any_container`, which asserts:

- five foreign containers under the ticket's exact name — no labels, another checkout's
  labels, another job's label, another compose project, another service — are each
  inspected and **not** stopped; the calls made are exactly one
  `container inspect --format <the reconciliation's format> <name>` and nothing else;
  `FixtureDocker.stopped` stays empty and the container is still `running`;
- the ticket's own correctly labelled container is stopped by its exact id: the calls are
  exactly `[inspect by name, stop --time 10 <id>]`, `FixtureDocker.stopped == [id]`, and
  the container stays present with `running` false;
- an absent container (`absent`/`no_such_container`), a container that vanishes between
  the inspect and the stop (`absent`/`gone_before_stop`), and an unreachable Docker
  (`refused`/`docker_cannot_answer`, error naming Docker Desktop) all stop nothing;
- a ticket whose own labels are not derived from this checkout is refused with **zero**
  Docker calls;
- every decision is written to `cooperative-stop.json` under the run root and equals the
  returned value;
- the real wiring (`_interrupt_for(request)()` with `_run_docker` patched to the fixture)
  routes through the same decision, returns rather than raises, and leaves
  `receipt.json` absent;
- across the whole test, the only things ever named to Docker are this ticket's own name
  and ids found under it — a second ticket's container name never appears.

`FixtureDocker` gained `stopped` and answers `stop --time 10 <id>` by marking that
container not running and keeping it present, as Docker does.

Results on `e90670d`:

```
python -m unittest Pipeline.AssistantControl.test_background_jobs
Ran 54 tests in 108.566s
OK

python -m unittest Pipeline.AssistantControl.test_graph_controller
Ran 33 tests in 45.354s
OK

python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_cli_worker Pipeline.AssistantControl.test_worker_control
Ran 17 tests in 15.593s
OK
```

`git diff --check`: clean, exit 0 — the only output is the expected
`LF will be replaced by CRLF` notice for the two LF files.

---

## Residual risks, stated plainly

- The cooperative stop now makes up to two Docker calls instead of one, each bounded by
  `_DOCKER_TIMEOUT_SECONDS` (60 s), so the stop-watch thread can spend up to about two
  minutes where it previously spent one. That thread is a daemon, it does not block the
  child's work or `watch.close()`, and the controller's own grace period and Job Object
  termination are unaffected — but a very slow Docker delays the *cooperative* half
  proportionally.
- There is a TOCTOU window between the inspect and the stop: a container could in
  principle be replaced by another under the same name in that instant. The window is now
  narrow and the stop targets the inspected **id**, so the worst case is stopping an id
  that no longer exists (recorded as `gone_before_stop`), never a different container.
  The name being checkout-exact since round 4 makes a hostile collision impossible in
  practice.
- The decision record lives only in the run root. It is not merged into the job index or
  the controller journal, so an operator or a later diagnosis reads it from
  `<run root>/cooperative-stop.json`. A repeated interrupt would overwrite it, but
  `_StopWatch` fires the interrupt exactly once per child.
- `_container_ownership_problem` deliberately duplicates the shape of the checks inside
  `reconcile_provider_container`'s watch loop rather than refactoring that loop to share
  it; the messages are identical in form, but the two code paths remain separate.
- The real `docker` CLI path is still exercised read-only. The new stop path has never
  been run against a live daemon in this clone, by instruction.
- The round-4 merge burden is unchanged and still applies: tickets written before
  `ca56dc7` do not authenticate and must be archived by hand before this branch is merged
  onto a checkout that has any.

---

Requesting Astra's re-review of **`e90670da5b5fc19567e1efe1cb655c43de292f4e`** before merge.
