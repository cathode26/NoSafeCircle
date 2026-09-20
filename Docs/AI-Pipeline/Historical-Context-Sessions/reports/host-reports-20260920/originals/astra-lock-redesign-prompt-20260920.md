Follow-up on the MAIN-WRITE lock. You reviewed Fable's design and returned FIX FIRST. New evidence
has since changed what the design should be built on, and I want you to redesign rather than
re-review — and to challenge Fable's choices directly where you disagree.

This is written to stand alone in case the thread does not carry context.

## Where we are

**The problem.** `C:\NSC\tools\ger\main_write.py` (114 lines) is the protocol every tool uses
before writing to `main` in `C:\NSC\NSC\NoSafeCircle`. Callers: `apply_contract.py`,
`apply_followup_revision.py`, `contract_commit.py`. It appends START/END lines to a shared markdown
journal and treats "no other open START in the last 30 minutes" as permission.

Four defects, all confirmed against the source by me and again by Fable:

1. Read-then-append is not atomic — `open_writes()` reads the whole journal, `_append()` then opens
   and appends; two processes interleave in that gap.
2. `ROLE = "GER Agent"` is a hardcoded module constant, and `start()` filters
   `if not item.startswith(ROLE)`. **Two concurrent callers of this module never conflict** — and
   those callers are the three contract committers.
3. A 30-minute window hides an older un-ENDed START while its writer may still be running.
4. `end()` verifies nothing. `expected_head` is written into the START line and never read again.

Why it matters: contract commits also touch shared registries (`RESOURCE_GROUPS.yaml`,
`WORK_ID_MAP.json`, the validation policy). Two racing revisions can silently drop one task's
policy binding, whose symptom is that task's candidates quietly parking.

## What Fable designed

`C:\nscrev\reports\main-write-lock-design-20260919.md` (491 lines):

- **Mechanism:** hand-rolled `msvcrt.locking` on byte 0 of the existing
  `<git-common-dir>/assistant-control-integration.lock`, held from `start()` to `end()`. Relies on
  the kernel releasing on holder death, so no timeout and no staleness heuristic.
- A sidecar JSON record naming the holder by operation ID; the journal demoted to a log only.
- `expected_head` checked under the lock, again before the commit, and proven after.
- Three callers change by one keyword argument each.
- **Estimate 15.5 h serial.** Explicitly excludes Docker writers, bare `git` run in the canonical
  checkout, multi-command manual sessions and synced folders.
- **Parallel section:** the core (~250 lines, one ordering argument) cannot be split; saving from
  helpers about one hour.

## What you already said about it

FIX FIRST — keep the Windows mechanism, revise the surrounding protocol. Your findings:

- **P0: parent death does not establish that writing stopped.** The design permits a `git` child to
  outlive the holder, and its test 6 treats reacquisition as success while a grandchild is alive.
- **P1:** all three callers read shared registries and stage restoration bytes *before* `start()`,
  so planning still races outside the lock.
- **P1:** "expected HEAD is a first-parent ancestor" is not "the immediate parent equals expected
  HEAD"; commit verification and abort handling are inconsistent.
- **P1:** reboot durability is asserted beyond what atomic replacement actually guarantees.
- **P1:** the acceptance tests need a production-entry-point contract, or an implementation that
  refuses everything could pass.
- You corrected the timing to **18–24 focused hours** for the corrected scope, and agreed the core
  does not parallelise — roughly 55–80 minutes saved, or 25–50 if reviews already overlap.
- You said not to call this a completed transaction foundation for work package 1, because nothing
  rejects stale generations and pipeline integrations do not increment them.

## The new evidence — this is why I am asking again

**1. Mature libraries already implement the primitive.** Neither is installed; both are one
`pip install`:

- `filelock` (py-filelock) — platform-independent, thread-safe via `threading.local`, real OS
  locking; it is the lock that tox, virtualenv and huggingface depend on.
- `portalocker` — cross-platform; since 4.0.0 it works on Windows using built-in `msvcrt` with **no
  `pywin32` dependency**, and it additionally offers Redis-backed distributed locks.

Fable proposed hand-rolling exactly what these wrap.

**2. Git already provides compare-and-swap on refs. I verified this on this machine today:**

```
git update-ref refs/heads/master <new> <wrong-old>
fatal: update_ref failed for ref 'refs/heads/master': cannot lock ref 'refs/heads/master':
is at 70e40f209f... but expected 2d7e8acbb0...
```

With the correct old value it succeeds. That is atomic CAS, built in — which appears to make
defect 4 solvable with no bespoke code.

**3. What these do NOT appear to solve**, and I want you to confirm or correct: your P0 (a `git`
child outliving the holder and writing after the kernel released the lock), and the planning done
outside the lock by the three callers. Those look project-specific rather than library-shaped.

### Sources I used — verify them rather than trusting my summary

These are where the library claims above come from. I have not read the source of either library,
only their documentation and a search summary, so treat my characterisation as unverified:

- `filelock` documentation — https://py-filelock.readthedocs.io/
  (claims: platform-independent; `FileLock` uses OS-provided locking while `SoftFileLock` only
  checks for the lock file's existence and is more deadlock-prone; thread-safe via
  `threading.local`.)
- `portalocker` — https://github.com/wolph/portalocker
  (claims: Windows/Linux/BSD/Unix; supports `with`; distributed locking via Redis.)
- `portalocker` package metadata — https://simple-repository.app.cern.ch/project/portalocker
  (claims: requires Python 3.10+; since 4.0.0 `pywin32` is no longer installed automatically on
  Windows and exclusive locks work using built-in `msvcrt`.)
- `portalocker` implementation, for the Windows path specifically —
  https://github.com/wolph/portalocker/blob/develop/portalocker/portalocker.py
- Background on why the two platforms need different APIs, and that POSIX locks are advisory —
  https://dev.to/susumun/cross-platform-file-locking-in-python-fcntl-vs-msvcrt-from-scratch-19c5

Environment facts relevant to the choice, verified by me on this machine:

- Python 3.13.1. **None** of `filelock`, `portalocker`, `fasteners`, `pid` or `flufl.lock` is
  installed. `msvcrt` is available (standard library).
- Windows PowerShell 5.1 only; **PowerShell 7 is absent.**
- The repo in question is on a local NTFS volume, but `C:\NSC` also contains junctions, and a
  OneDrive client is running on this machine — so "never on a synced or network path" is not a
  safe assumption forever.
- If you consider anything beyond these two libraries, name it and say why it beats them here.

## What I want

A redesign, library-first, that challenges Fable where you disagree. Specifically:

1. **Which library, or none?** `filelock`, `portalocker`, something else, or hand-rolled after all —
   and the reason. If a dependency is the wrong call for a tool that guards `main`, say so; supply
   chain and one more thing to install are legitimate counter-arguments. Check what each actually
   does on Windows when the holder dies abruptly, hangs, or the machine reboots holding the lock.
2. **Does `git update-ref` with an old value fully replace the bespoke HEAD checking**, or only
   part of it? Name what it does not cover — I am thinking of the shared-registry files that are
   not refs, and of the window between validating a tree and updating the ref.
3. **The parts no library provides.** How the surviving-child problem (P0) is actually solved —
   process-tree ownership, job objects, a post-write verification, or refusing to inherit handles.
   And how planning is brought inside the lock without making the critical section absurdly long.
4. **The smallest correct design.** I would rather ship a smaller thing that is right than a
   complete one that is subtly wrong. State plainly what it does not protect.
5. **A revised estimate**, against your own corrected scope of 18–24 hours. If using libraries plus
   `git update-ref` genuinely reduces it, say by how much and what remains. If it does not reduce
   it — because the protocol and tests were always the work — say that instead of being agreeable.
   I have already had to correct this number twice and would rather have it right than low.
6. **Does the parallelisation answer change?** If the primitive is now an import, is there more or
   less for helpers to do?

Write to `C:\nscrev\reports\main-write-lock-redesign-astra-20260920.md`.
