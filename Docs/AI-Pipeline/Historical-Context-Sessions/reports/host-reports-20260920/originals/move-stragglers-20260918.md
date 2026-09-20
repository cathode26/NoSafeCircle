# Move-to-history stragglers - findings (2026-09-18)

## 1. Which C:\nsc* directories are still at the source

**As of the final check in this session, none.** Only the three permanently-excluded
paths remain directly under `C:\`: `C:\NSC`, `C:\nscrev`, `C:\NSC-History-20260918`.

The one known straggler, `C:\nscmin_work`, was present and stuck at the start of this
investigation but disappeared from the source partway through it (see section 3) -
by the time I finished, `C:\NSC-History-20260918\nscmin_work` held its full contents.
I did not move or delete it; something else completed that move while I was reading
the same tree read-only. Nothing in this session's tool history performed a move or
delete of any `C:\nsc*` directory.

## 2. Why `nscmin_work` was stuck (evidence gathered before it resolved itself)

Two independent, compounding causes, both consistent with what I could observe:

**a) `MOVE-TO-HISTORY.ps1`'s own "destination exists" guard skipped it on every run.**
Before this session, `C:\NSC-History-20260918\nscmin_work` already existed and already
contained three folders - `evidence-a`, `evidence-a-2`, `evidence-a-3` - that do not
belong to `nscmin_work`'s known structure (`killer` / `missing` / `negative` / `victim`).
It also already contained a byte-for-byte-identical copy of the `killer` subfolder
(confirmed with `robocopy /L /E` list-mode: 19,791/19,791 files match, same total
bytes). `MOVE-TO-HISTORY.ps1` checks `Test-Path -LiteralPath $r.Dest` per top-level
candidate and skips with no manifest entry the instant anything sits there - which is
exactly the state I found. `MANIFEST.json` (44 entries) has zero entries for
`nscmin_work`, consistent with a silent skip rather than a Move-Item failure being
recorded. I could not determine from the current state alone who put `killer` and the
`evidence-a*` folders there or when; recommend asking Vincent, since `evidence-a*`
looks unrelated to this game-repro workdir and is worth a second look before it is
mistaken for real `nscmin_work` content later.

**b) The underlying paths are long enough that `Move-Item` is a real risk even without
the destination-exists issue.** Measured directly from `C:\nscmin_work`, the deepest
path found was 226 characters, e.g.:
`C:\nscmin_work\negative\Library\PackageCache\com.unity.collections@84e8eb3fc12e\Unity.Collections.LowLevel.ILSupport\source~\Unity.Collections.LowLevel.ILSupport.CodeGen\Unity.Collections.LowLevel.ILSupport.CodeGen.asmdef.meta`
Swapping the `C:\nscmin_work\` prefix (15 chars) for the destination's
`C:\NSC-History-20260918\nscmin_work\` prefix (37 chars) adds 22 characters, projecting
that one path to 247 - still under the classic 260-char `MAX_PATH`, but a plain
recursive enumeration of the tree only returned 46,725 items against an expected
~79,000+ (four Unity `Library\PackageCache` trees), which means a meaningful number of
deeper items were silently dropped by the same MAX_PATH limitation before they could
even be measured. The true deepest paths are almost certainly longer than 226 and some
land past 260 once the longer destination prefix is added. `Move-Item` runs on the
classic .NET Framework path APIs (Windows PowerShell 5.1), which do not reliably honor
the `LongPathsEnabled=1` registry policy already set on this machine for `Directory`
operations, so it is the right suspect even though I couldn't pin an exact failing
path this session.

**Ruled out:** no lock or in-use-process cause. `Get-Acl` and a `\\?\`-prefixed
read-only file open both worked without contention while the folder still existed;
robocopy went on to move the whole tree (confirmed gone from source, fully present at
destination) without anyone stopping a process first, so nothing had it open
exclusively. No permissions issue was found either (no ACCESS_DENIED in the checks
run).

## 3. Timeline note (why section 1 says "none" despite the task's premise)

- First check: `C:\nscmin_work` present, containing `killer`, `missing`, `negative`,
  `victim`. Destination `C:\NSC-History-20260918\nscmin_work` present, containing
  `evidence-a`, `evidence-a-2`, `evidence-a-3`, and a complete duplicate of `killer`.
- A few minutes later, mid-investigation (read-only checks only, no move/delete
  issued by me): `C:\nscmin_work` gone; destination now holds all seven folders,
  timestamps on the freshly-added ones clustering around 8:19 PM.
- Most likely explanation: someone else (plausibly Vincent, directly) ran a manual
  robocopy-style move against this exact target concurrently with this session. This
  is not a finding I can attribute to any action of mine - I did not run any command in
  this session with `/MOVE`, `Move-Item -Destination`, or `-Apply` prior to that point.

## 4. Deliverable

`C:\NSC-History-20260918\MOVE-STRAGGLERS.ps1` - dry-run by default (`-Apply` to act),
uses `robocopy /MOVE /E` (long-path safe) instead of `Move-Item`, appends to the same
`MANIFEST.json` MOVE-TO-HISTORY.ps1 writes, and refuses to run at all if `C:\NSC`,
`C:\nscrev`, or `C:\NSC-History-20260918` itself is ever in its candidate set. Per
target it also refuses a destination that already exists and refuses a cross-volume
move, both checked once at scan time and again immediately before each move. Ran it
dry-run just now: it correctly reports "Nothing to move. No stragglers at the source."
given the current, fully-resolved state. Nothing was moved or deleted by this script or
by me.

## 5. Open item for Vincent

Please take a look at `C:\NSC-History-20260918\nscmin_work\evidence-a`,
`evidence-a-2`, `evidence-a-3` - they don't match `nscmin_work`'s known
`killer`/`missing`/`negative`/`victim` structure and I can't tell from the filesystem
alone whether they're something you put there intentionally or stray content that
landed in the wrong place.
