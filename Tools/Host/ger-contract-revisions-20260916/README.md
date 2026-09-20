# GER contract-revision tools — preserved 2026-09-20

Source: `C:\nscrev\ger-contract-revisions-20260916` (the GER Agent's live working directory).

These are preserved because **they existed in exactly one place on the machine** and nowhere in
this repository under any name. Verified 2026-09-20 against `main` at `416bb3605`. Preservation is
the point: once they are here, deleting the source folder is reversible, which is what makes the
cleanup safe to run.

The folder they came from is 271 MB, but almost all of that is `followups-20260917` (206 MB) and
`scratch` (62 MB). The irreplaceable part is the ~40 KB of Python here.

A secret scan over every file found nothing. `origin` is public; that check was not optional.

## Known defect — read before restoring any of this

**`main_write.py` in this folder is STALE and actively breaks the two contract committers.**

The real, maintained module is `Tools/Host/ger/main_write.py` (114 lines). This copy is an older
58-line version that hardcodes the journal path and whose functions take no `journal=` argument:

| | `Tools/Host/ger/main_write.py` | this stale copy |
|---|---|---|
| `default_journal(repo)` | present | **missing** |
| `start(...)` | `start(operation, expected_head, *, journal)` | `start(operation, expected_head)` |
| journal path | passed in by the caller | hardcoded `C:\NSC\...` |

`new_task_commit.py:194` and `policy_entry_commit.py:80` both call
`main_write.default_journal(ac.REPO)` and then pass `journal=` — that is, they are written against
the **maintained** module. But Python puts a script's own directory first on `sys.path`, so running
either of them from this folder loads the stale copy and fails with:

```
AttributeError: module 'main_write' has no attribute 'default_journal'
```

Measured 2026-09-20: importing `main_write` from that folder resolves to the stale file,
`hasattr(main_write, "default_journal")` is `False`, and `start` has no `journal` parameter.

**The fix is a deletion, not a merge** — remove the stale `main_write.py` from the working
directory so `Tools/Host/ger/main_write.py` is the one that loads. It is kept here only so the
history is legible and the diagnosis can be re-checked. **Do not restore it onto `sys.path`.**

The only file that genuinely needs the old no-`journal` API is
`runbook_contract_commit.retired-20260917.py`, which is retired and should not be run.

## Contents

| file | lines | status |
|---|---|---|
| `new_task_commit.py` | 253 | live — creates a new task contract; **blocked by the defect above** |
| `policy_entry_commit.py` | 119 | live — commits a validation-policy entry; **blocked by the defect above** |
| `verify_filter.py` | 170 | live |
| `build_supersede_cascade.py` | 141 | live |
| `validate_in_memory.py` | 52 | helper — imports `persistent_work_graph`, `work_graph_validate` |
| `quiet.py` | 24 | helper |
| `main_write.py` | 58 | **STALE — see above** |
| `runbook_contract_commit.retired-20260917.py` | 249 | retired 2026-09-17 |
| `runbook_contract_commit.before-policy.bak.py` | 149 | backup |

`new_task_commit.py`, `policy_entry_commit.py` and `validate_in_memory.py` also import
`apply_contract`, which is **not** preserved here because it is not an only-copy — the maintained
version is `Tools/Host/ger/apply_contract.py`.

## Owner

The GER Agent owns these tools and the decision about what to do with them. This commit only stops
them being unrecoverable; it does not adopt, fix or deploy them.
