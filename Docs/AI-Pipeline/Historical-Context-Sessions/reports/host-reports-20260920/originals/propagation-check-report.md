# propagation_check — design, real-case result, timings, limits

Built in the container against a read-only `/workspace` clone. Deliverables:

| file | lines |
|---|---|
| `/out/propagation_check.py` | 702 |
| `/out/tests/test_propagation_check.py` | 499 |
| `/out/README.md` | — |

`/workspace` is byte-identical to how it started: `git status --porcelain=v1
--untracked-files=all` is empty after every run in this session.

---

## 1. Design, and why it is shaped this way

The postmortem fact that drives the whole design: **three of PR #134's four CI
rounds were not symbol removals.** Commit `6e718ece2` removed the string
`"contract_locality_auditor"` from the *value* of `CREW_SESSION_ROLES` in
`Pipeline/ExecutionCrew/session_pool.py`. The tests that broke asserted counts
derived from that tuple — "four roles not idle", "exactly forty leases". No grep
for a removed *name* finds anything there, because no name was removed. The
fourth round was an HTML default moving into script, which fails the same way.

So the tool has two halves with very different weight:

- **Step 4 (test selection) is the product.** It selects every test file that
  imports a changed module, regardless of whether any symbol disappeared. That
  is what covers a value change, and it is what would have caught PR #134.
- **Steps 2 and 3 (symbol diff + grep) are the narrow case.** They catch a
  genuine rename whose stale references live in YAML, Markdown or PowerShell
  where no Python test would ever touch them.

The report prints them in that order but explicitly tells the reader that a
clean step-2 result proves nothing, and that step 4 is the coverage. That
warning is in the tool's own output, not only in the README — a tool that
implies more coverage than it has is worse than none.

### The six steps

1. `git diff --name-only <base>..<head>`, keep `.py`, map path -> dotted module.
2. Parse base and head text of each changed file with `ast`. The source comes
   from `git cat-file --batch`; the file is **never imported**. Collect
   module-level functions, classes, assignment targets (including tuple
   unpacking and annotated assignment) and `__all__` string entries. Report
   names present at base, absent at head.
3. One batched fixed-string `git grep -F` across all tracked files for those
   names. Each hit is tagged `in_changed_file` (so a rename confined to one file
   reads as the rename itself, not as breakage) and `in_workflow` (printed as
   `[CI WORKFLOW]`).
4. One `git grep -E '^[[:space:]]*(from|import)[[:space:]]'` over test-shaped
   paths, then parse each hit in Python. That resolves `import X.Y`,
   `from X.Y import a, b`, the parent-package form `from X import Y as z` that
   this repository uses in `session_pool_smoke_test.py`, indented
   function-local imports (`provider_profiles_test.py` imports inside every test
   method), and relative imports resolved against the importing file's package.
5. Report, or `--json` for the same data. `--limit N` caps printed hits per
   symbol.
6. `--run` executes each selected file with `PYTHONPATH=<clone>` and a scratch
   `TMPDIR`, one line per file: path, exit code, seconds, last meaningful
   output line. Exit `1` if any selected test failed.

### CI marking

A selected test is marked `[CI]` if `.github/workflows` names it. This
repository does that two ways and both are handled: as a path
(`run: python Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py`) and in
dotted form (`"Pipeline.TaskReviewAgent.tests.provider_profiles_test"` in
`assistant-candidate-ci.yml`). Path-matching alone marked
`provider_profiles_test.py` as not-in-CI, which was wrong — it is one of the
four tests that actually failed in PR #134.

### Process spawning

Every `subprocess` call in the tool and in its tests passes
`creationflags=CREATE_NO_WINDOW` — `0x08000000` on Windows, `0` elsewhere.
`DETACHED_PROCESS` appears nowhere.

---

## 2. Real-case verification on `6e718ece2`

Read-only, against `/workspace`:

```
python -B propagation_check.py /workspace 6e718ece2~1..6e718ece2
```

Result:

```
1. CHANGED PYTHON FILES (6)
   Pipeline/ExecutionCrew/role_profiles.py        -> Pipeline.ExecutionCrew.role_profiles
   Pipeline/ExecutionCrew/run_crew.py             -> Pipeline.ExecutionCrew.run_crew
   Pipeline/ExecutionCrew/session_pool.py         -> Pipeline.ExecutionCrew.session_pool
   Pipeline/TaskReviewAgent/openai_pipeline.py    -> Pipeline.TaskReviewAgent.openai_pipeline
   Pipeline/TaskReviewAgent/pipeline_scope.py     -> Pipeline.TaskReviewAgent.pipeline_scope
   Pipeline/TaskReviewAgent/provider_profiles.py  -> Pipeline.TaskReviewAgent.provider_profiles

2+3. REMOVED OR RENAMED MODULE-LEVEL SYMBOLS, WITH STALE REFERENCES (0)
   none - no module-level name present at base is absent at head.
   This does NOT mean nothing broke; see LIMITS below, then step 4.

4. TESTS THAT IMPORT THE CHANGED MODULES (24, of which 12 referenced by .github/workflows)
```

**Steps 2 and 3 correctly find nothing** — exactly as predicted, because
`6e718ece2` removed a string from a tuple value, not a name.

**Would it have selected the four tests that actually failed in PR #134? Yes —
all four, and all four marked `[CI]`:**

| test | selected | `[CI]` | selected because it imports |
|---|---|---|---|
| `Pipeline/TaskReviewAgent/tests/execution_session_pool_smoke_test.py` | yes | yes | `Pipeline.ExecutionCrew.run_crew`, `…session_pool` |
| `Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py` | yes | yes | `Pipeline.ExecutionCrew.run_crew`, `…session_pool` |
| `Pipeline/TaskReviewAgent/tests/provider_profiles_test.py` | yes | yes | `…run_crew`, `…session_pool`, `Pipeline.TaskReviewAgent.provider_profiles` |
| `Pipeline/ExecutionCrew/tests/pooled_run_crew_smoke_test.py` | yes | yes | `Pipeline.ExecutionCrew.run_crew`, `…session_pool` |

The full selection is 24 test files, 12 of them CI-referenced. The other 20
files are genuinely reachable from the six changed modules; the tool does not
claim they would all have failed, only that they import what changed. The
`[CI]` marking is what tells the reader which subset CI would actually have
exercised.

Two selections are worth noting as evidence the parsing is doing real work:

- `provider_profiles_test.py` imports `provider_profiles` only from **inside
  test methods** (indented, `from … import a,b` with no space after the comma).
  A naive line-start import regex misses it.
- `session_pool_smoke_test.py` uses the parent-package form
  `from Pipeline.ExecutionCrew import run_crew as crew_module` alongside the
  dotted form.

---

## 3. Timings

No Safe Circle checkout, Linux container, warm page cache, 252 tracked test
files, 11 workflow files naming ~150 `.py` paths. Steps 1-4, no `--run`:

| range | changed `.py` | tests selected | steps 1-4 |
|---|---|---|---|
| `6e718ece2~1..6e718ece2` (the real case) | 6 | 24 | **1.07 s** |
| `~10..` | 10 | 25 | 1.33 s |
| `~40..` | 24 | 37 | 1.55 s |
| `~100..` | 345 | 176 | 9.20 s |
| `~200..` | 399 | 182 | 9.87 s |

Numbers stable within ~0.2 s across repeated warm passes; a cold-cache first run
costs roughly 3x. A realistic pre-merge range is about a second — inside
Vincent's "if it just takes a minute, then that is fine".

Three optimisations were needed to get there, each measured:

| change | effect on the `~1..` case | effect on `~200..` |
|---|---|---|
| one `git cat-file --batch` instead of one `git show` per file | 5.5 s -> 1.8 s | — |
| all removed symbols in one batched `git grep -F` instead of one grep per symbol | — | symbol grep 1.47 s for 23 symbols, flat |
| step 4: one grep for any import line + parse in Python, instead of one regex alternation per module | 1.8 s -> 1.1 s | **540 s -> 9.9 s** |

The third mattered most. Handing `git grep -E` 1035 alternation patterns (345
modules x 3 forms) took 330 s in the grep alone.

`--run` adds one process spawn per selected file; its cost is the tests' own
cost. The tool's overhead there is negligible.

---

## 4. Limits

Printed by the tool itself, in every report, under `LIMITS`:

- **A value change inside a constant is invisible to steps 2 and 3.** That is
  the PR #134 shape. Step 4 is what covers it. A clean symbol section proves
  nothing on its own.
- Step 3 is a literal text grep: it cannot distinguish a stale reference from an
  unrelated word that matches, and it does not resolve aliases.
- Step 4 matches import statements. A module reached only through `importlib`, a
  plugin registry, a subprocess invocation or a data file is not found.
- Only module-level names are compared. Methods, nested classes and attributes
  are out of scope.
- A multi-line `from X import (` contributes `X` but not submodules named on
  continuation lines. (Single-line forms, including the parent-package form this
  repository uses, are handled.)
- Files added at head are skipped by step 2 — nothing can have been removed from
  a file that did not exist at base.
- Files that do not parse with `ast` at either revision are skipped by step 2
  and listed by path in the report rather than silently dropped.
- `--run` proves what the selected tests prove. It is not the full CI matrix,
  and a green `--run` is not a green CI.

---

## 5. Tests

`python -B tests/test_propagation_check.py` -> **29 tests, all passing**
(0.86 s). Each builds a throwaway git repository under `TMPDIR`; none touches
the real repository.

Required cases, all present:

| case | class |
|---|---|
| removed function with a stale reference in `.github/workflows` | `RemovedFunctionWithWorkflowReference` |
| renamed class | `RenamedClass` |
| **value removed from a tuple**: steps 2+3 find nothing, step 4 still selects the importing test, `--run` catches the failure | `ValueRemovedFromTuple` |
| changed module with no importing tests | `ChangedModuleWithNoImportingTests` |
| non-Python change | `NonPythonChange` |
| `--run` reporting a failing selected test | `RunReportsFailingTest` |

Plus `RenameConfinedToOneFile` (in-file hits marked, not counted as stale),
`ImportFormsAndMapping` (import-form parsing including the repository's
parent-package and indented forms, relative-import resolution, module path
mapping, `__all__` collection, range parsing, and an assertion that
`CREATE_NO_WINDOW` is the allowed flag value), and `BadInput`.

---

## 6. What I could not do

- **I did not run `--run` against the real repository.** The four PR #134 tests
  are `run_crew`/`session_pool` smoke tests and I could not establish offline
  that none of them shells out to Docker or a provider, which I am forbidden to
  start. So the real-case verification is steps 1-4 only, and the `--run` path
  is proven by the synthetic suite (`ValueRemovedFromTuple` and
  `RunReportsFailingTest` both assert real non-zero exit codes and last-line
  capture). What that leaves unmeasured is the wall-clock cost of `--run` on a
  24-test selection in this repository.
- **The `CREATE_NO_WINDOW` flag is exercised, not observed.** On Linux it is
  `0`, so the tests assert the constant and that every spawn passes it; the
  actual suppression of a console window can only be confirmed on Windows.
- **Ordering of the four rounds.** I took the postmortem facts from the prompt
  as given; the commit `6e718ece2` and its contents I verified directly in
  `/workspace`, but I did not independently reconstruct which round each CI
  failure belonged to.
- **No installation step.** The tool is plain files under `/out`; wiring it into
  a pre-merge habit at `C:\nscrev\job-tools\` is the caller's step. It is
  deliberately not added to `.github/workflows`, since it is a local pre-merge
  check, not a CI job.
