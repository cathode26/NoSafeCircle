# MAIN-WRITE lock design (replaces the journal-as-lock)

Date: 2026-09-19. Author: Pipeline Maintainer. Status: DESIGN ONLY. No code was written, nothing on
disk was changed apart from this file.
Brief: `main-write-lock-design-brief.md`. Parent plan: `nsc-durability-cleanup-and-undo-plan-20260919.md`,
section "Make all real source writers use a transaction" (lines 179-186).

**Summary.** Take the operating-system byte-range lock the pipeline already uses for integration
(`<git-common-dir>/assistant-control-integration.lock`, byte 0, `msvcrt.locking`) and hold it from
`start()` to `end()`. The kernel releases it when the holder dies, so no timeout and no staleness
guess is needed for mutual exclusion. A sidecar JSON record names the holder by operation ID. The
journal stays, as a log only. `expected_head` is checked under the lock, again just before the commit,
and proven after it. The three callers change by one keyword argument each.

---

## 0. The four defects, verified against the source

Read: `C:\NSC\tools\ger\main_write.py` (114 lines) and the three call sites.

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Read-then-append is not atomic | **Confirmed** | `start()` line 106 calls `open_writes()` (full read, line 89); line 110 calls `_append()`, which reads the journal again (line 74) and then opens in append mode (line 81). Nothing is held between them. |
| 2 | Hardcoded role; same-role callers never conflict | **Confirmed, and worse than stated** | `ROLE = "GER Agent"` (line 29); filter `if not item.startswith(ROLE)` (line 106). Also `pending` is a dict keyed by role (line 88, 92), so two open STARTs from one role collapse into one entry, and one END (line 96) clears both. |
| 3 | 30-minute window | **Confirmed** | `open_writes(minutes=30)` line 85; line 100 drops anything older. The timestamp has minute resolution and comes from the wall clock. |
| 4 | `end()` verifies nothing | **Confirmed** | Line 113-114: one `_append`. `expected_head` is formatted into the START line (line 110) and never read again by any code. |

Three more defects found while checking, all relevant to the design:

5. **The callers' HEAD check is outside the protocol.** `contract_commit.py:303`,
   `apply_contract.py:594` and `apply_followup_revision.py:199` compare HEAD to the planned head and
   only then call `main_write.start()`. The check and the claim are separate steps.
6. **HEAD is never re-checked before `git commit`.** Between `start()` and the commit each caller
   runs `taskcontrol validate` as a subprocess (`contract_commit.py:335`). That takes seconds to a
   minute. If `main` moves in that window, the contract commit lands on a parent nobody validated.
7. **The pipeline's own integration lock is not taken.** `ReviewGate.integrate`
   (`Pipeline/AssistantControl/review.py:243`), `source_update.py:313`, `decomposition.py:765`,
   `unity_materialization.py:468` and the two materialization recovery modules all hold
   `_source_integration_lock(source)`. The ger tools do not, so a contract commit can run in the
   middle of a pipeline fast-forward today. The parent plan says to adapt the existing source lock
   and not add a second one. That decides the mechanism.

---

## 1. The mechanism, and why it wins on Windows

**Chosen:** a non-blocking exclusive byte-range lock (`msvcrt.locking(fd, LK_NBLCK, 1)` at offset 0)
on `<git-common-dir>/assistant-control-integration.lock`, polled with a monotonic deadline, held by an
open handle for the whole `start()`..`end()` span. This is the same file, byte and call that
`Pipeline/TaskReviewAgent/execution_session_pool.py:_exclusive_file_lock` (line 162) and
`review.py:_source_integration_lock` (line 27) already use.

Why this one:

- **The kernel decides "dead or slow", which is better evidence than any timeout.** A Windows
  byte-range lock belongs to the process and handle that took it. When the process ends for any reason
  (exit, exception, `TerminateProcess`, power loss), the handle closes and the lock goes. So while the
  lock is held, a live process holds it. When the lock can be acquired, the previous holder is gone.
  PID reuse cannot fool this, because it never looks at a PID.
- **A hung holder keeps the lock.** That is correct. The brief requires that a lock must not
  "silently expire while it is still running". No code path breaks a held lock. A human reads the
  holder record and ends the process deliberately (see 4.2).
- **Child processes do not inherit it.** Python handles are non-inheritable by default (PEP 446), and
  Windows file locks are not inherited through `CreateProcess`. A `git` or `taskcontrol` child that
  outlives a killed parent does not keep the lock. The spike in section 8 verifies this.
- **It is already the pipeline's source lock.** Taking the same lock makes the ger tools participants
  in the existing protocol and fixes defect 7 with no extra work. Any other primitive would create
  the "second independent lock" the parent plan forbids.
- Standard library only. No third-party dependency.

What each alternative gets wrong here:

| Alternative | Problem in this setting |
|---|---|
| Directory create, or `O_CREAT\|O_EXCL` lock file | Acquiring is atomic, but the lock survives holder death. Staleness then has to be inferred from PID plus creation time. Breaking it has its own race: two breakers both prove it stale, one deletes and re-creates, the other deletes the fresh lock. It also needs a boot ID for the reboot case. It is a more careful version of what the journal did. |
| `CreateFileW` with share mode 0 | The kernel releases it on death, which is good. But no one else can open the file, so the pipeline's `_open_lock_region` (`path.open("a+b")`) would fail at open with a non-retryable error and break live integrations. It needs ctypes, because `os.open` cannot set a share mode. It is a second lock unless the pipeline is rewritten too. |
| Named mutex (`CreateMutexW`, `Global\...`) | The kernel releases it, and `WAIT_ABANDONED` even reports the death. But it is owned by a thread, it is named by a hash and not by the repo path, a container cannot see it, and the pipeline lock cannot see it. It would be a second lock. |
| `os.replace` | It replaces atomically and the last writer wins. It gives no mutual exclusion. It is used here only to publish the holder record. |
| `msvcrt.locking` with `LK_LOCK` (blocking) | It retries 10 times at 1 s and then raises. The existing pipeline docstring notes this. Use `LK_NBLCK` with your own loop. |
| `filelock` or `portalocker` | On Windows they wrap `msvcrt.locking`. They add nothing and bring a pip dependency into out-of-git tools. |
| Keep the journal, add the lock around the read and append | It fixes defect 1 only. The log would still be the lock, with the 30-minute expiry and the role filter. |

Windows byte-range locks are **mandatory**: another handle that reads the locked byte gets an error.
So the holder's identity goes in a sidecar file, not in the lock file, and the lock file stays the
single `\0` byte the pipeline creates.

**Network or synced folder.** The lock file lives in the repo's git directory, not under
`.assistant-control`. The lock follows the thing it protects. Moving the journal to another volume
changes nothing. If the repo itself moved:

- SMB share: byte-range locks are enforced by the server and work between Windows clients. Release
  after a client crash waits for the SMB session to time out, which can take tens of seconds or a few
  minutes. The design degrades but still works.
- OneDrive, Dropbox or a similar sync: locks are local to each machine. Two machines would both
  acquire. **The design breaks there.** A git repo in a synced folder is already unsafe for other
  reasons. The holder record stores `hostname`, so a record from another host can be reported loudly,
  but that only reports the problem. This lock covers a single machine.

---

## 2. Files: location, format, how stale is proven

All files are under `common = git -C <repo> rev-parse --git-common-dir`, resolved. This is the same
resolution as `review.py:29-32`, so every worktree of one repo shares them and every test clone has its
own.

| File | Role | Written |
|---|---|---|
| `assistant-control-integration.lock` | The lock: one byte, locked at offset 0. It already exists in live repos. | Created if missing, never truncated, never deleted. |
| `nsc-main-write-holder.json` | Who holds it. For diagnostics, and the start of the write-ahead intent. | Temp file plus `os.replace`, UTF-8 without BOM, after acquiring. Deleted by a clean `end()`. |
| `nsc-main-write-generation` | A decimal integer, the fencing token. | Read, +1, atomic replace, under the lock. |
| `nsc-main-write-crashed/<op_id>.json` | Holder records left by dead operations. | Moved here by the next acquirer. Never deleted automatically. |
| the journal (`default_journal(repo)`, unchanged) | The human-readable log. | Appended while holding the lock. |

Holder record (schema 1):

```json
{
  "schema": 1,
  "op_id": "mw-20260919T140211Z-9f3c1a7e",
  "generation": 42,
  "role": "GER Agent",
  "operation": "T-123 contract revision 4",
  "repo": "C:\\NSC\\NSC\\NoSafeCircle",
  "branch": "main",
  "expected_head": "<full 40-hex>",
  "phase": "held",
  "pid": 18244,
  "created_ticks": 134029384756120000,
  "image": "c:\\python313\\python.exe",
  "argv": ["contract_commit.py", "..."],
  "cwd": "C:\\nscrev\\ger-work",
  "hostname": "VINCENT-PC",
  "started_utc": "2026-09-19T14:02:11Z",
  "journal": "C:\\...\\graph-lead-journal.md"
}
```

`pid`, `created_ticks` and `image` have the same shape that
`Pipeline/AssistantControl/process_identity.identify()` returns (`GetProcessTimes` creation
FILETIME). `phase` moves through `held` -> `applying` -> (file deleted). The lock needs only `held`.
The other phases are for the transaction protocol.

**How a stale record is proven stale.** The acquirer now holds the OS lock and a holder record from
another `op_id` still exists. The kernel gives the lock only when no live process has it, so the
recorded holder ended without reaching `end()`. That is the whole proof. It uses no clock and no PID
probe. It also covers reboot, where the locks vanish with the kernel and the file stays on disk. The
acquirer then:

1. adds what it observed (`observed_head`, `found_by_op`, `found_utc`) and moves the record to
   `nsc-main-write-crashed/<op_id>.json`;
2. journals `MAIN-WRITE RECOVERED <role>: op <old op_id> ended without END (holder gone, lock was free);
   expected HEAD <a>, HEAD now <b> -> <nothing committed | committed | unknown>`;
3. carries on. The three callers already refuse a dirty target path or a staged index
   (`contract_commit.py:272-275`), so a half-written tree from the dead run stops them with a clear
   message. No new refusal is added here.

`pid` and `created_ticks` are used only to make refusal messages accurate. If the record's process
identity does not match a live process while the lock is held, the message says "lock is held by a
live process; holder record is missing or not yet written (a pipeline integration holds this lock
without a record)". It does not name a dead holder.

---

## 3. The API, and how the three callers change

The replacement keeps the module name and the function names. Signatures:

```python
def start(operation: str, expected_head: str, *, journal: pathlib.Path,
          repo: pathlib.Path, role: str | None = None, wait_seconds: float = 15.0) -> str:
    """Acquire the source lock for `repo`, prove HEAD == expected_head under it, publish the holder
    record, bump the generation, append the START line. Returns op_id. Raises SystemExit (non-zero)
    naming the holder when the lock is not acquired within wait_seconds, and when HEAD differs."""

def check_head() -> None:
    """Compare-and-swap guard. Call immediately before the write that advances main. Re-reads HEAD and
    the branch. Raises SystemExit if either moved since start(). Sets phase 'applying'."""

def end(new_head: str, checks: str, *, journal: pathlib.Path) -> None:
    """Verify, append the END line, delete the holder record, release the lock. ALWAYS releases, even
    when verification fails. Raises SystemExit after releasing if verification failed."""

def held(operation, expected_head, *, journal, repo, role=None, wait_seconds=15.0)  # context manager
def holder(repo) -> dict | None      # read-only: the current holder record, for tools and the viewer
# CLI:  python main_write.py run --repo R --role "Documentation Agent" --operation "GDD edit" -- <cmd...>
#       python main_write.py status --repo R
```

Behaviour that matters:

- **One operation per process.** Module state `_ACTIVE` holds the open handle, op_id, repo and
  expected head. A second `start()` while active raises. The second handle would be refused by the
  kernel anyway, which acts as a backstop.
- **`role`**: the argument, else `NSC_AGENT_ROLE`, else `"GER Agent"`. It is a label in the log. It
  takes no part in exclusion, so two GER Agent runs conflict like any other pair.
- **`start()` order**: resolve the common dir -> open the lock file -> `LK_NBLCK` loop with a
  `time.monotonic()` deadline -> under the lock: `git rev-parse HEAD` must equal `expected_head` (full
  sha, fixes defect 5) and record the branch -> handle any stale record (section 2) -> generation +1 ->
  publish the holder record -> append START. Any failure after acquiring releases the lock before
  raising.
- **`end()` verification** (fixes defect 4): an active operation must exist; `git rev-parse HEAD ==
  new_head`; and either `new_head == expected_head` (aborted, nothing committed) or `expected_head` is
  the first-parent ancestor of `new_head` (`git rev-list --first-parent new_head` reaches
  `expected_head`). For the three callers that means exactly `HEAD^ == expected_head`. `git commit`
  takes its parent from the ref and updates the ref with an old-value check, so `HEAD^ !=
  expected_head` **proves** someone moved `main` inside the window. `end()` then journals
  `MAIN-WRITE END ... CAS-VIOLATION`, releases the lock and exits non-zero. It does not reset
  anything. A human decides.
- **END without START**: `end()` with no active operation appends nothing that looks like an END. It
  writes `MAIN-WRITE END-REJECTED <role>: no active operation in this process` and raises SystemExit.
- **`atexit`**: if the process exits with an operation still active, a best-effort
  `MAIN-WRITE END <role>: ABANDONED (process exit without end) [op=...]` is appended. The kernel
  releases the lock either way.
- **Journal line format** stays compatible with the old regexes and with human readers. The new
  tokens go at the end:
  `- 2026-09-19 14:02 UTC MAIN-WRITE START GER Agent: <operation>, expected HEAD 9f3c1a7e2 [op=mw-... gen=42 pid=18244]`
  `- 2026-09-19 14:03 UTC MAIN-WRITE END GER Agent: new HEAD 1b2c3d4e5; <checks> [op=mw-...]`
- **Legacy hand-written STARTs.** Roles that journal by hand, such as the Documentation Agent and the
  Game Agent's manual merges, do not hold the OS lock until they move to `run`. During migration
  `start()` keeps the **existing** check in a narrower form. An open START line **without an `op=`
  token** from another role, less than 30 minutes old, still refuses, with the same message as today.
  This gate is already in place and no new gate is added. Lines with `op=` are ignored, because the
  lock covers them. Delete the check when the last hand-writer has moved. It is the only place where
  the log still affects admission.
- **Linux fallback**: `fcntl.flock` when `os.name != "nt"`, mirroring the pipeline helper, so the
  module imports and its non-race tests run in a container. It gives no cross-boundary guarantee
  (see 4.7).
- **Why re-implement the ~25-line lock and not import the pipeline helper:** the ger tools live
  outside git at `C:\NSC\tools\ger`. Importing `Pipeline.*` would run code from the checkout that is
  being written. A compatibility test (5.8) pins the two implementations to the same file and byte.
  When the ger tools move into the repo (already in the Maintainer queue), switch to the shared
  helper and delete the copy.

**Caller migration** is the same edit in all three files:

```python
# before (contract_commit.py:303-305)
if ac.git("rev-parse", "HEAD").stdout.decode().strip() != head:
    raise SystemExit("HEAD moved since planning; rerun")
main_write.start(f"...", head, journal=args.journal)

# after: start() performs the HEAD check under the lock
main_write.start(f"...", head, journal=args.journal, repo=ac.REPO)
```

Add one line, `main_write.check_head()`, directly before the `git commit` call in each
`write_and_commit*` (`contract_commit.py:369` and its two siblings). This fixes defect 6. The existing
`except BaseException: main_write.end(<HEAD>, "aborted, ...")` blocks and the success `end()` calls
stay byte-for-byte the same. That comes to about 4 changed lines per caller. `repo` is required. A
caller that omits it gets a `TypeError` at the call, which is loud and never silently unlocked.

One behaviour change to tell the GER Agent about: the dirty-path and staged-index checks at
`contract_commit.py:272-275` run before `start()`, outside the lock. They should move to just after
`start()`. It is a small move, inside the same edit.

---

## 4. Failure matrix

| # | Event | What happens | Why it is safe |
|---|---|---|---|
| 4.1 | **Holder crashes or is killed** | The kernel closes the handle and the lock is free. The next `start()` acquires, finds the leftover record, archives it to `nsc-main-write-crashed/`, journals RECOVERED with expected and current HEAD, and proceeds. | Proof of death is that the kernel released the lock. `git commit` is atomic, so `main` is either before or after. Leftover working-tree edits hit the callers' existing dirty-path refusal. |
| 4.2 | **Holder hangs** | The lock stays held. Contenders wait `wait_seconds` and then exit non-zero: `main write refused: held by op mw-... (GER Agent, "T-123 rev 4", pid 18244, since 14:02 UTC, 23 min)`. | The lock never expires on its own. The message gives what a human needs to check the process and end it with `process_identity.terminate(identity)`, which checks the creation time and so cannot kill a recycled PID. |
| 4.3 | **Reboot with the lock held** | Locks do not survive the kernel. The record file does. The next `start()` handles it as 4.1. | No boot ID is needed. The proof is the same. |
| 4.4 | **Two simultaneous starts** | Exactly one `LK_NBLCK` succeeds. The other polls, then refuses and names the winner. Same role or different role makes no difference. | Arbitration is a single kernel call with no read-then-write gap. |
| 4.5 | **END without START** | `END-REJECTED` line, SystemExit. No END line is written. | An operation in another process cannot be closed by accident. |
| 4.6 | **`main` moves between check and write** | Cooperating writers (the ger tools, every pipeline integration path, anything under `run`) cannot move it, because they are excluded. A non-cooperating writer (bare `git commit` or `git merge` in the canonical checkout) is caught by `check_head()` just before the commit, or, inside the last millisecond window, by `end()` proving `HEAD^ != expected_head` -> CAS-VIOLATION, non-zero. | Prevention applies where a writer participates. Everywhere else the move is detected with certainty. It is never a silent pass. |
| 4.7 | **Container writer** | **Not covered by the lock.** Docker Desktop bind mounts (9p or virtiofs) do not turn a Linux `flock` into a Windows byte-range lock, so a container and a host process can both "hold" it. What covers it: containers are given job clones and task checkouts, never the canonical checkout, and their results reach `main` only through host-side integration, which holds this lock. If that ever changes, 4.6 detects the ref move and nothing prevents it. | Stated as an invariant (section 6). Emulating the lock across the boundary is not the answer. |
| 4.8 | **Clock jump** (NTP step, DST, manual change) | No effect on exclusion. The lock does not use time and the wait loop uses `time.monotonic()`. Journal and record timestamps may be out of order. `generation` gives the true order. | This removes defect 3's dependence on the wall clock. |
| 4.9 | **Pipeline integration hits while a contract commit holds the lock** | The pipeline side waits 10 s (`review.py:33`) and then raises `TimeoutError`. A contract commit holds the lock across `taskcontrol validate`. | **New interaction.** Today they do not contend at all, which is defect 7. See risk R1 in section 7. |
| 4.10 | **Holder record write fails after acquiring** | Release the lock, SystemExit. | Do not run without a holder record. |
| 4.11 | **Journal append fails** | START failure: release and refuse. END failure: release, and exit non-zero saying the commit exists but the log line does not. | The lock state is always correct. The log failure is reported loudly. |

---

## 5. Tests that would prove it

Put them at `C:\NSC\tools\ger\tests\test_main_write_lock.py`, or the in-repo location once the ger
tools are ported. Use `unittest`. Every temp dir goes under `C:\nscrev\tmp` (set `TEMP` and `TMP`).
Every subprocess gets `CREATE_NO_WINDOW`. Every test builds its own throwaway git repo and passes an
explicit `journal`. None can reach the live journal or the canonical lock.

**Shared harness.** A helper script `_mw_holder.py`, run as a child: it calls `start()`, prints
`HELD <op_id>` and flushes, then blocks reading stdin. It reacts to `end`, `exit-without-end`, or
being killed. The parent synchronises by **reading that line**, never by sleeping. No test contains
a `sleep` used as a synchronisation point.

1. **Same-role exclusion** (defect 2). Child holds; parent `start(wait_seconds=0)` with the same role
   -> SystemExit whose message contains the child's `op_id`. Fails on the old code, where the parent
   proceeds.
2. **TOCTOU reproduced on the old code, deterministically** (defect 1). Monkeypatch the old
   `_append` to block on a `threading.Barrier(2)`. Run two threads that call old `start()`. Both pass
   `open_writes()` and then both append. Assert two START lines and no refusal. This is the
   failing-before proof. It fails on an assertion about behaviour, not on a `TypeError` caused by the
   new signature.
3. **N-way race with an overlap witness.** 8 children block on a pipe. The parent closes it to
   release them together. Each calls `start(wait_seconds=30)`. While holding, each does
   `os.open(witness, O_CREAT|O_EXCL)`, holds briefly and unlinks before `end()`. Any overlap between
   two holders makes `O_EXCL` fail in one of them, and that child exits 99. Assert all 8 complete,
   none exits 99, there are 8 START/END pairs with 8 distinct `op_id`s, and the generations are 8
   consecutive integers.
4. **Negative control for the tests.** Run the body of test 3 with the lock call monkeypatched to a
   no-op (env var read only by the test helper), in a tight loop. Assert the witness **does** detect
   an overlap. If it cannot, test 3 proves nothing and the suite must say so. This guards against
   tests that pass for the wrong reason.
5. **Hard kill releases; the stale record is archived.** Child holds; parent calls `TerminateProcess`
   and waits on the process handle. Parent `start()` succeeds. `nsc-main-write-crashed/<child
   op>.json` exists. The journal has a RECOVERED line naming the child op.
6. **Child-of-holder does not retain the lock.** The holder spawns a long-running grandchild
   (`python -c "input()"`), then the holder is killed. Parent `start()` succeeds while the grandchild
   is still alive.
7. **No expiry** (defect 3). Child holds. Parent patches `datetime.now` and `time.time` forward 24 h
   and back 24 h. `start(wait_seconds=0)` is still refused both times.
8. **Compatibility with the pipeline lock, both directions.** Import `_exclusive_file_lock` from the
   test clone's `Pipeline.TaskReviewAgent.execution_session_pool`. (a) Pipeline lock held in the child
   -> `main_write.start()` is refused with the "no holder record" message. (b) `main_write` held in
   the child -> `_exclusive_file_lock(path, timeout_seconds=0.2)` raises `TimeoutError`. This shows
   they are the same lock and not two locks.
9. **CAS at start.** `expected_head` is the parent of HEAD -> refused, lock released (a follow-up
   `start()` with the right head succeeds), no START line.
10. **CAS before commit.** After `start()`, the parent makes a commit with bare git; `check_head()`
    -> SystemExit.
11. **CAS after commit.** Same, but the bare-git commit lands after `check_head()`; the caller
    commits; `end()` -> CAS-VIOLATION, non-zero, lock released.
12. **END without START** -> `END-REJECTED`, non-zero, no END line.
13. **`end()` always releases.** Force a verification failure, then `start()` from a second process
    succeeds.
14. **Journal compatibility.** Parse the new lines with the old regexes and get the right role and
    stamp. A legacy hand-written open START from another role still refuses. One from the same role,
    or older than 30 min, or carrying `op=`, does not.
15. **Test-clone isolation.** With `repo` set to a clone, assert that nothing under the canonical
    common dir or the live journal changed. Record mtime and size before and after.
16. **Callers, end to end.** Run each of the three tools with `--commit` in a fixture clone while a
    child holds the lock -> non-zero, nothing written, the tree is clean. Then without the holder ->
    commit made, END line with `op=`, holder record gone.

Tests 3-6 and 8 run on Windows only (`skipUnless(os.name == "nt")`). They must run on the host and
not in Docker. A container cannot prove any of this.

---

## 6. What it deliberately does not protect

- **Anyone who runs bare `git` in the canonical checkout.** A lock stops only the writers that take
  it. Such writes are detected (4.6), not prevented. The cure is migration: the Game Agent's manual
  merge and the Documentation Agent's GDD commits should go through `main_write.py run -- <script>`.
- **Multi-command manual sessions.** The lock lasts as long as one process. An agent that does
  "merge, test for ten minutes, commit" across separate tool calls cannot hold it, unless those steps
  are one script under `run`. A detached "hold" daemon with owner-liveness tracking is possible, but
  it brings back the dead-or-slow problem for the *owner*. It is left to the transaction coordinator.
- **Container writers** (4.7). They are covered by the rule that containers never mount the canonical
  checkout. The lock does not cover them.
- **Multi-machine or synced-folder repos** (section 1).
- **Pushes and the remote.** Local `main` only.
- **Record-only writers** (`.assistant-control` task records, leases, approvals). The parent plan
  wants them in the same protocol. This design does not touch them.
- **Content validity.** The lock serialises writers. It does not validate what they write.
- **Task checkouts and clones.** Each has its own common dir and so its own lock. This is
  intentional.
- **A process that holds the lock and deadlocks forever.** It blocks `main` writes until a human
  ends it. This is deliberate. The alternative is the silent expiry being removed.

**What the transaction protocol (work package 1) already gets from this, and what is left:**

| WP1 element | Provided now | Left for later |
|---|---|---|
| Actual source-write mutex in the source common directory, shared by all writers | **Yes.** The same lock the integration paths hold. | Moving hand-writers onto `run`, and lock ordering with task/runtime locks. The ger tools take only this one lock, so no ordering issue arises yet. The existing order is `checkouts.lock` -> integration lock -> admission lock, as in `source_update.py:308-313`. |
| Durable operation ID | **Yes.** `op_id` is in the record, the journal and the crash archive. | Threading `op_id` into commit trailers and task records. |
| Generation fencing | **Partly.** A monotonic `generation` is issued under the lock. | Nothing *rejects* a stale generation yet. Result publishers and record writers must start checking it. Pipeline integrations do not bump it yet. |
| Write-ahead intent | **The starting point.** The holder record is written before any mutation. It carries the kind (`operation`), `expected_head` and `phase`, and it survives a crash as an incomplete intent that recovery can find. | Affected task IDs, a planned-paths list, and a real recovery reconciler. Today's handling is archive plus journal line. |
| Before and after images | No. | All of it. The `phase` field and the crash archive are the hooks. |
| Expected-HEAD check immediately before apply | **Yes.** At `start()`, in `check_head()`, and proven in `end()`. | Build the commit in an isolated checkout, then `git update-ref <new> <expected>` and fast-forward under the lock, which is the plan's step 3. The callers still commit in place. |
| Completion receipt | The END line with `op=`. | A structured receipt file, and queueing the remote capture. |

---

## 7. Estimate

| Piece | Hours |
|---|---|
| Windows-mechanism spike (section 8, piece S) | 0.75 |
| `main_write.py` core: lock, holder record, generation, CAS, `end()` verification, atexit, legacy check | 3.5 |
| `run` and `status` CLI | 1.0 |
| Three caller migrations, plus moving the dirty checks under the lock | 0.75 |
| Tests 1-16 with the harness and the negative control | 5.0 |
| Fix report, independent review (Fable, because this is locking code), Codex adversarial review, one fix round | 3.0 |
| Rebase, trial merge, focused re-run, handoff | 1.0 |
| **Total** | **~15 h**, realistically two working sessions |

**The risky part, R1: holding the pipeline's integration lock across `taskcontrol validate`.** After
this change, a contract commit holds the lock that `ReviewGate.integrate`, `source_update`,
decomposition and the materialization paths wait on for **10 seconds** before raising `TimeoutError`.
If validate takes longer than that, a concurrent pipeline integration will fail where today it
silently races. That is the correct outcome, but it is a visible change in behaviour. Before building,
measure validate's duration on the canonical repo and read how each of the six call sites surfaces
`TimeoutError`: retryable, or a task marked failed? If it is not retryable, propose to Vincent either
raising the pipeline-side wait or running validate before taking the lock, with a cheap re-check under
it. That is a design decision about the pipeline's behaviour, not a detail, and it is the one item that
could push the estimate past 15 h.

R2: test 3 and test 4 are the tests most likely to be flaky or empty. Budget for them is inside the
5 h.

R3: the ger tools are outside git, so there is no branch to review. The work should be done on the
in-repo port of `tools/ger` if that lands first. If it does not, deliver as a clone-tested copy plus
a diff for Vincent's go. Decide before starting.

---

## 8. Parallel work breakdown

**The core does not split. The work around the core splits a little. The honest saving is about one
hour of wall clock out of fifteen.**

### Can the core be split? No.

The core is one ~250-line module. Its correctness is a single argument: acquire -> check HEAD ->
handle stale record -> bump generation -> publish record -> journal -> ... -> verify -> journal ->
delete record -> release. Every failure branch must release the lock, and must do so in the right
order relative to the journal and the record. Every candidate seam (lock vs holder record, `start` vs
`end`, module vs race harness) cuts through that ordering argument. Two authors who cannot see each
other's reasoning would each write a plausible half. The bug would be in the join. Examples: a
failure path that publishes the record but releases first, or a harness that synchronises on a line
printed before the lock is actually held. Those bugs pass review because each half looks right.

The race harness (tests 3-6) stays with the core author for the same reason. It can be written
against the frozen API in section 3, but it can only be *debugged* against the real module. A
harness that someone else wrote and the core author never stepped through is how a test comes to
pass for the wrong reason.

### What can be fanned out

The interface is frozen by section 3 of this document. No helper invents any part of it, and no two
helpers need to agree on anything.

| Piece | Helper | Handed | Returns | Depends on | Must not need to know |
|---|---|---|---|---|---|
| **S. Mechanism spike** | One **host CLI job** (Windows required. Not Docker, because `msvcrt` does not exist there). | Section 1 plus five yes/no questions: released on `TerminateProcess`? grandchild retains it? second handle in the same process refused? contends with the pipeline's `_exclusive_file_lock` in both directions (scratch clone under `C:\nscrev`)? sidecar readable while byte 0 is locked? | One script plus its raw output. Five answers. | Nothing. Runs while the core is being written. | Anything about the API, the journal or the callers. |
| **T. R1 measurement** | The same job, or a `test-runner` (Haiku). | The canonical repo path, **read-only**: time `taskcontrol validate` in a clone at current `main`; list how the six `_source_integration_lock` call sites surface `TimeoutError`. | Seconds. A table of file:line -> behaviour. | Nothing. | The lock design. |
| **A. Core + CLI + tests 1-15** | **The Maintainer session**, one author. | This document. | Branch or file set, report. | S's answers must arrive before the core is finalised. They can change the design (R1 can too). | n/a |
| **C. Three caller migrations + test 16** | One helper (Codex medium or `pipeline-maintainer` on sonnet), **after A**. | Section 3's before/after snippet, the three file paths, the fixture pattern from A. | A diff and test output. | A merged into the work clone. | How the lock works. It needs only the signature. |
| **D. Docs** | **Documentation Agent** (their lane): orchestrator guide section 5, the role guides' MAIN-WRITE wording, the `run` recipe for hand-writers. | Sections 3 and 6. | Doc edits. | API frozen. It is now. | Implementation. |
| **R. Reviews** | `pipeline-reviewer` (Fable) **and** a Codex adversarial review, launched **at the same time**. | Report, clone, `<base>..<head>`. | Verdicts. | A and C. | Each other. |

C is one helper, not three. The three edits are the same four lines, 45 minutes in total. Three
helpers would mean three briefs, three diffs to read and three verifications, to save about 25
minutes of typing. That is a loss.

### Integration cost

- S: read the script and output, and re-run one of the five checks myself: **15 min**. I cannot
  accept "lock released on kill: yes" without seeing the script wait on the process handle before it
  tries to acquire.
- T: **10 min**. Spot-check two of the six call sites.
- C: read three diffs, run test 16 myself: **25 min**. Doing C myself takes 45 min. Net saving
  **~20 min**, and only if the helper gets it right first time. If a diff misses the `check_head()`
  placement in one sibling, the saving is gone. It is a coin flip whether C is worth delegating.
  Delegate it only if A is running late.
- D: no cost to me. A different owner. But the Documentation Agent's time is not free either.
- R: the two reviews already run concurrently, so this is a saving in scheduling and not in effort.

### Wall-clock difference

| | Serial | Fanned out |
|---|---|---|
| Spike + R1 measurement | 1.25 h | 0 h on the critical path (run alongside A), + 0.4 h reading |
| Core, CLI, tests | 9.5 h | 9.5 h |
| Callers | 0.75 h | 0.4 h |
| Reviews + fix round | 3.0 h | 2.5 h (both reviewers at once) |
| Rebase, handoff | 1.0 h | 1.0 h |
| **Total** | **~15.5 h** | **~14 h** |

The saving is **about one and a half hours, and one hour is the realistic figure.** Nearly all of it
comes from running the spike alongside the core and the two reviews alongside each other. None of it
comes from splitting the lock. Adding more helpers past that point makes the total *longer*, because
every extra artifact is another 15-25 minutes of my reading and re-verifying on correctness-critical
code.

### What would actually make it finish sooner

1. **Start S and T now**, before any core code is written. They are the only items that can change
   the design, and they cost the critical path nothing.
2. **Decide R3 (where the code lands) and R1 (validate inside or outside the lock) up front.** Each
   is a Vincent decision that would otherwise stall the build part-way. Fifteen minutes of his time
   here saves more than any helper can.
3. **Hand D to the Documentation Agent on day one.** The hand-writer migration (Game Agent merges,
   GDD commits) closes the largest hole left, in section 6. It depends only on the frozen API.
4. **Run the two reviews at the same time**, and give the `test-runner` the base/head suite runs.
5. Do not use Docker helpers for any piece whose proof is the lock. They can draft D or C, but they
   cannot run the Windows tests, so verifying their work falls back on the host.
