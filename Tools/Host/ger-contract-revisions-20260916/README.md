# GER contract-revision tools — preserved 2026-09-20

Source: `C:\nscrev\ger-contract-revisions-20260916` (the GER Agent's live working directory).

These are preserved because **they existed in exactly one place on the machine** and nowhere in
this repository under any name. Verified 2026-09-20 against `main` at `416bb3605`.

## What this does NOT establish — corrected 2026-09-20

**The first version of this file said preserving these files makes deleting the source folder
reversible, and called this Python "the irreplaceable part". Both claims were too strong.**
Audit `Tools-Cleanup-Audit/20260920-143913` found further authored source and evidence in the
same folder with no blob in `HEAD`. Five of them are now preserved here —
`followups-20260917/build_followups.py`, `build_decoy_obligations.py`, `encounters/polish_rev4.py`,
`briefs/encounters-030.md`, `cascade-015-017/decisions-applied.md` — but **that list came from an
audit, not from an inventory, so it is not known to be complete.**

Also: `scratch/` inside that folder **is itself a git repository**. Its branches and uncommitted
content have not been certified, and a directory being named `scratch` is not evidence that it is
disposable.

**So: this commit makes these specific files recoverable. It does not make the folder safe to
delete.** That needs a bounded inventory of the exact removal target, with a disposition for every
file — retained, reproducible, still-live, or unresolved — and no live consumer. Do not infer that
anything called scratch, output or log is discardable, and do not import everything into git to
avoid deciding.

A secret scan over every file found nothing, and gitleaks 8.30.1 scanned all three commits with
zero findings. `origin` is public; that check was not optional.

## Correction — the first version of this file claimed a defect that does not exist

**The first commit of this README asserted that `new_task_commit.py` and `policy_entry_commit.py`
were broken. They are not. Both work.** The GER Agent disproved it within the hour and the
correction is recorded here rather than quietly edited away, because the wrong version was
committed and someone may have read it.

What I claimed: that the stale 58-line `main_write.py` in this set shadows the maintained module
on `sys.path`, so both committers fail at `main_write.default_journal()`.

Why it was wrong: **I measured a bare `import main_write`, which is not the code path either
script takes.** Both explicitly prepend the maintained helpers *after* interpreter startup has
placed the script directory, so the good copy wins:

```
new_task_commit.py:31-32   sys.path.insert(0, <own dir>)
                           sys.path.insert(0, r"C:\nscrev\ger-tools")   # "installed G15b helpers win"
policy_entry_commit.py:24  sys.path.insert(0, r"C:\nscrev\ger-tools")
```

Replicating that real setup, `main_write` resolves to `C:\nscrev\ger-tools\main_write.py` with
`default_journal` present and `start(operation, expected_head, *, journal)`. Measured 2026-09-20.

`C:\nscrev\ger-tools` is a **directory junction to `C:\NSC\tools\ger`**, so the committers are
already using the maintained module — and that is why the two copies are byte-identical
(`8f2da4f9…`). There is no version skew to fix.

The lesson worth keeping: *testing the module in isolation is not testing the path the program
takes.* A bare import exercised none of the setup that makes these scripts correct.

## The real risk, which the GER Agent identified

Both committers **hardcode the absolute path `C:\nscrev\ger-tools`** — a junction, at depth 2,
inside the tree a cleanup pass walks. If that junction is ever removed, both break hard, and the
maintained copy at `C:\NSC\tools\ger` will not rescue them: nothing else puts it on `sys.path`
(`PYTHONPATH` is unset and no `.pth` adds it).

That is a genuine fragility and it is being fixed by repointing both at `C:\NSC\tools\ger` with a
fallback. It is also a correction to my own tool-verification report of the same morning, which
said "only 4 lines in 3 live tools are genuinely junction-dependent" — that count was scoped to
`C:\NSC\tools` and missed these. **Second time in two sessions that a sweep of `C:\NSC\tools`
which skipped `C:\nscrev` produced an undercount.**

The stale `main_write.py` is still worth removing from the working directory — it is a real trap
for anyone who does a bare import — but that is tidying, not a fix for a live failure.

## Contents

| file | lines | status |
|---|---|---|
| `new_task_commit.py` | 253 | live — creates a new task contract; **works** |
| `policy_entry_commit.py` | 119 | live — commits a validation-policy entry; **works** |
| `verify_filter.py` | 170 | live |
| `build_supersede_cascade.py` | 141 | live |
| `validate_in_memory.py` | 52 | helper — imports `persistent_work_graph`, `work_graph_validate` |
| `quiet.py` | 24 | helper |
| `main_write.py` | 58 | stale copy; harmless to these scripts, a trap for a bare import |
| `runbook_contract_commit.retired-20260917.py` | 249 | retired 2026-09-17; the only file wanting the old no-`journal` API |
| `runbook_contract_commit.before-policy.bak.py` | 149 | backup |

`new_task_commit.py`, `policy_entry_commit.py` and `validate_in_memory.py` also import
`apply_contract`, which is **not** preserved here because it is not an only-copy — the maintained
version is `Tools/Host/ger/apply_contract.py`.

## Owner

The GER Agent owns these tools and the decision about what happens to them. This commit only stops
them being unrecoverable; it does not adopt, fix or deploy them.
