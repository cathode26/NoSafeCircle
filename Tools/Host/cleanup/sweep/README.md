# Only-copy sweep scripts

**Working tools, not finished ones.** They are here because they were the only
copies in existence, in session scratchpad directories that are temporary and
sit on a ~30-day auto-delete. The method they encode took several wrong attempts
to get right, and re-deriving it would cost more than keeping them.

They are deliberately **not** wired into `run_tool_tests.py` or CI: they have no
tests, and they carry hardcoded host paths (`importsweep.py` opens with
`REPO = r"C:\NSC\NSC\NoSafeCircle"`). Treat them as a recorded method rather than
a supported entry point, and read before running.

| script | what it does |
|---|---|
| `sweep_nscrev.py` | walks `C:\nscrev` and reports files that exist nowhere else |
| `importsweep.py` | the same question against a named import folder |
| `sweep_codexjobs.py` | narrower pass over `C:\nscrev\codex-jobs` |

## The method, which is the part worth keeping

A file is an "only copy" when its content appears neither in the repository's
object store nor under `C:\NSC\tools`. Three things make that harder than it
sounds, each learned by getting it wrong:

1. **Normalise CRLF to LF before hashing.** Git stores LF; the Windows checkouts
   are CRLF. Skipping this reported **97,714 false positives** against 5,595 real
   ones — a 94% error rate that looked like a catastrophe until the cause was
   found.
2. **Compare against the whole object store, not `HEAD`.** `git cat-file
   --batch-all-objects --batch-check` answers "has this content ever been
   committed"; a `HEAD`-only comparison calls every historical file unique.
3. **Hash in process.** Spawning `git hash-object` per file is one subprocess per
   file over ~100k files. The blob hash is
   `sha1(b"blob " + len + b"\x00" + data)` and computing it directly turns hours
   into minutes.

## Scope, which is where this went wrong twice

**A sweep that covers `C:\NSC\tools` and skips `C:\nscrev` undercounts.** It did,
three separate times: 3 callers found against 5 real, 3 only-copy GER files
against 8, and an undercount of junction-dependent lines. Any run must cover
`C:\nscrev` and the GER working folders, and **must state which roots it
searched** so the next reader can tell what was not looked at.

## Status

The sweep is **unfinished**. Two folders under `C:\nscrev` were completed and
both yielded tooling nobody had listed. The remainder is unswept, and cleanup
walks all of it. `C:\nscrev\codex-jobs` alone is 5.1 GB across 607k files, 98% of
which is 71 git job clones rather than job records.
