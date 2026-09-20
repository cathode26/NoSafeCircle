# Astra: investigate two live Gauntlet defects, NSC-1163 and NSC-1165

Fresh agent. Read-only investigation. **Do not stop, settle, revise, clear or otherwise
mutate the live run, and do not modify the Gauntlet project.** Do not push, merge or change
GitHub state. If you want a mutation performed, say exactly which command you want and why,
and I will run it.

## What is running

A disposable AssistantControl Gauntlet, started 2026-09-13 13:34:19 UTC, still live.

| | |
|---|---|
| Project (Source) | `C:\NSC\GauntletFresh1160-Reviewed-Standalone` |
| Branch | `gauntlet-test/reviewed-async-1160` |
| Control head | `ff5e328be8aa53813b87ad17f0b9c5334dbb3b6e` |
| Checkout root | `C:\NSC\GauntletFresh1160-Reviewed-Standalone-Checkouts` |
| Records | `<checkout root>\.assistant-control` |
| Journal | `<records>\graph-controller-events.jsonl` |
| Targets | NSC-1160 through NSC-1167, plus decomposition children NSC-1168 through NSC-1171 |
| Viewer | http://127.0.0.1:8819 |

Health at 13:56: five tasks integrated (NSC-1161, NSC-1162, NSC-1164, NSC-1168, NSC-1169),
twenty background jobs launched, one failed, five lock deferrals every one recovered at one
of six, five Source-lane holds. Two tasks are stuck, and they are what I want you to
investigate.

**Neither defect is in the stack you are re-checking.** That stack is
`86068e6490c33bb71b025cbe1b6de204859a24af` (re-pin migration, lock deferral, your two
blocker fixes). The project above additionally carries `5e23243b11d4788e2de550a96582d23571e8f179`,
"require exact policy re-pin replay diff", whose parent is `86068e6`. Both defects below are
in paths that no commit in either set touches. Please treat them as new findings, not as
regressions, and please keep your verdict on `86068e6` separate from this investigation.

---

## Defect 1: NSC-1163 finished its work, then died holding nothing, and the controller waits forever

### What happened, in order

1. The task was prepared, scoped, reserved and its worker started at 13:35:48 UTC.
2. The execution crew **succeeded**. Its host log ends:

```
[2026-09-13T13:38:11Z] Validator 1 completed: succeeded (74.3s)
[2026-09-13T13:38:21Z] Validator 1 completed: pass
[2026-09-13T13:38:32Z] ExecutionCrew completed: review_ready
RESULT: REVIEW_READY
ARTIFACT: C:\NSC\GauntletFresh1160-Reviewed-Standalone-Checkouts\NSC-1163\Pipeline\ExecutionCrew\outputs\nsc-1163-20260913t133611z\candidate.patch
```

3. The host then tried to record that result and died.
   `<records>\worker-runs\NSC-1163\c957f9501d3572c377f702bfc66f5323e3506010e4b4c7424fd3bf6185e7bf3c\launcher.status.json`:

```json
{
  "status": "child_failed",
  "pid": 42248,
  "error": "[Errno 10060] timed out after 10s waiting for exclusive file lock: 'C:\\NSC\\GauntletFresh1160-Reviewed-Standalone-Checkouts\\.assistant-control\\checkouts.lock'"
}
```

4. PID 42248 is gone. That worker run directory has no `receipt.json`, no `run_result.json`,
   no `progress.log`. Its newest files are `launcher.status.json` and `stderr.log`, both
   written at 13:38 local, nothing since.
5. The durable checkout record `<records>\NSC-1163.json` still says
   `worker.status = "running"` at `pid 42248`, `launch.status = "ready_pending"`, and
   `status = "prepared"`.
6. The controller has planned `wait_worker` for NSC-1163 continuously ever since, 138 times
   and counting, each completing with `result_status = "progress"`. Most recent at 13:56:41.
   It will never converge.

### The two code sites I believe are responsible

Paths are in the running project, `C:\NSC\GauntletFresh1160-Reviewed-Standalone`.

**Child side**, `Pipeline\AssistantControl\worker_control.py` lines 102 and 140:

```python
with _exclusive_file_lock(checkouts.records / "checkouts.lock", timeout_seconds=10):
```

A flat ten second timeout with no retry, on the path the host uses to record its own
outcome. The controller routinely holds `checkouts.lock` longer than that during an
integration, and this run shows integrations at 13:42:05 and later plus five separate
controller-side contentions. The deferral mechanism I added protects controller actions,
the harvest, the cleanup retry and startup. It does not protect this.

**Controller side**, `Pipeline\AssistantControl\graph_controller.py` line 1574, inside
`_wait_for_progress`:

```python
if observed.get("host_identity_alive") is False:
    return {**observed, "status": "progress", "progress": "worker_exited"}
```

A provably dead host is returned as progress, so the next cycle re-plans the same wait.
Nothing in that loop turns a host that exited without a terminal worker record into a
settle or into a failure.

### What I want from you

1. Confirm or refute that ordering, from the durable records rather than from my account.
   In particular, is the child's ten second acquisition the actual cause of death, or did
   something else kill it and the lock error is a symptom?
2. Is the controller's `worker_exited`-as-progress the right place to fix, or does the
   correct fix belong where the launch record is still `ready_pending`, meaning the worker
   never completed its handshake into a full worker record?
3. Does the settle path (`settle_worker`, and the `settle-worker` CLI) safely recover a
   worker in this exact state, with the crew's finished patch on disk but no receipt? Say
   whether recovery preserves that patch or discards the work.
4. What is the minimal fail-closed fix for each side. For the child, name the retry bound
   you want, since a child has no later cycle and must retry inside its own process.
5. Is there any way this state can lose or double-apply work, as opposed to merely hanging?

---

## Defect 2: NSC-1165 reached a correct human boundary and the wrapper recorded it as a failure

### What happened

The decompose background job for NSC-1165 launched at 13:42:16 UTC and its ticket landed
`failed` at 13:46:30, with:

```
ValueError: Decomposition result is not one exact regular file:
C:\NSC\GauntletFresh1160-Reviewed-Standalone-Checkouts\.assistant-control\decomposition-runs\assistant-nsc-1165-decompose-c7cb184da82b\decomposition_result.json
```

The decomposition run itself did not fail. Its own result document,
`<records>\decomposition-runs\assistant-nsc-1165-decompose-c7cb184da82b\decomposition_run_result.json`,
records a deliberate stop:

| Field | Value |
|---|---|
| `run_status` | `needs_human` |
| `decision` | `decomposed` |
| `authority` | `review_only_not_applied` |
| `calls_used` / `max_calls` | 2 / 2 |
| `author_corrections_used` | 0 |
| `decomposition_result_path` | `null` |
| `graph_delta_path` | `null` |
| `duration_seconds` | 234.5 |
| `provider_order` | `["claude", "codex"]` |
| `review_independence` | `cross_provider` |
| `independent_approver_provider` | `null` |

```
rejection_reasons: ["call limit ended immediately after a revision;
                    the latest author may not approve its own candidate"]
human_next_step:   "Inspect unresolved_findings and round artifacts. The bounded
                    independent-review circuit reached a human authority boundary;
                    no candidate was approved or applied."
```

Round 1 was `claude-code` / `claude-sonnet-5`, round 2 was `openai-codex` / `gpt-5.6-sol`,
both succeeded, both `review_only_not_applied`, neither a correction round.

The one unresolved finding is substantive and looks correct to me:

```
finding_id: round-02-misstated-edit-mode-proof
category:   candidate_correctness
affected:   NSC-1165, gauntlet-1165-alpha-value, gauntlet-1165-beta-value
problem:    Both proposed completion gates say the committed Edit Mode tests confirm that
            the corresponding type is a public static class. The tests resolve the fully
            qualified type and inspect its public static literal Value field, but they
            never assert Type.IsPublic, Type.IsAbstract, or Type.IsSealed. The child
            acceptance criteria correctly require public static classes, but the completion
            gates overstate what their named test filters prove.
```

### The code site I believe is responsible

`Pipeline\AssistantControl\decomposition.py`, `_verify_review`. It loads the result artifact
at line 159:

```python
run_result, run_bytes   = _load_object(run_path, "Decomposition run result")
result_payload, result_bytes = _load_object(result_path, "Decomposition result")   # line 159
graph_payload, graph_bytes   = _load_object(graph_path, "Graph delta")
```

and only about fifteen lines later checks the run's own status:

```python
expected = { ..., "run_status": "review_ready", "decision": "decomposed", ... }
for field, wanted in expected.items():
    if run_result.get(field) != wanted:
        raise ValueError(f"Decomposition review {field} is ...")
if run_result.get("unresolved_findings") != [] or run_result.get("rejection_reasons") != []:
    raise ValueError("Decomposition review carries unresolved findings or rejections")
```

A `needs_human` run has no result artifact by design, so the load at line 159 raises first
and the honest diagnosis is never reached. The ticket is recorded `failed`, and a failed
decomposition ticket blocks any retry for that task.

### What I want from you

1. Confirm or refute that ordering as the cause of the mislabelling.
2. Is reordering the checks sufficient and fail-closed, or does it weaken any proof that
   currently depends on the artifacts being loaded before the status is trusted?
3. Should a `needs_human` decompose job be terminal-but-not-failed, mirroring how post-crew
   already reports `awaiting_human` and completes successfully? If so, name the exact
   durable status you want, and say what the controller should plan for such a task so it
   neither retries blindly nor wedges.
4. Separately from the wrapper: was the circuit right to stop? It spent both calls and
   stopped immediately after a revision, where independence forbids the author approving
   its own candidate. Is the correct remedy a third call, the bounded author-correction
   round, or a human decision every time?
5. Is the reviewer's finding itself correct, that the completion gates overstate what the
   named Edit Mode test filters prove? If so, it is a provider-output quality matter rather
   than controller code, and I would like that said explicitly so we classify it correctly.

---

## Evidence you can read directly

All read-only. Please do not write into the checkout root.

```
<records>\graph-controller-events.jsonl
<records>\NSC-1163.json
<records>\NSC-1165.background-job.json
<records>\NSC-1165.decomposition.json
<records>\worker-runs\NSC-1163\c957f9501d3572c377f702bfc66f5323e3506010e4b4c7424fd3bf6185e7bf3c\
<records>\decomposition-runs\assistant-nsc-1165-decompose-c7cb184da82b\
<records>\background-jobs\NSC-1165\045fe48bfc7b7752a227e624420143e8ab021945d3956ec9df40e3e1682af00d\
```

where `<records>` is `C:\NSC\GauntletFresh1160-Reviewed-Standalone-Checkouts\.assistant-control`.

Code, in `C:\NSC\GauntletFresh1160-Reviewed-Standalone`:

```
Pipeline\AssistantControl\worker_control.py          (lines 102, 140)
Pipeline\AssistantControl\graph_controller.py        (_wait_for_progress, line 1574)
Pipeline\AssistantControl\decomposition.py           (_verify_review, line 159 onward)
Pipeline\AssistantControl\background_jobs.py         (ticket statuses, launch refusal)
```

## Output I want

For each defect: whether you confirm my diagnosis or refute it and why, the minimal
fail-closed fix with the exact bound or status you want, whether it is controller code,
fixture policy, provider output, Unity infrastructure or task implementation, and a priority.
State plainly which of your conclusions you reproduced from the records and which are
reasoning only. If you believe either defect can lose or duplicate work rather than just
hang or mislabel, say so first and loudly.
