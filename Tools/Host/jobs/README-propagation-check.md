# propagation_check.py

A pre-merge check that answers the question nobody has time to answer by hand:
**if I merge this range, what else in the repository still points at what I
changed, and which tests would CI have run?**

Standard library only. It never imports the repository under test, never
writes to it, and never starts a provider, Docker or Unity.

```
python -B propagation_check.py <clone> <base>..<head> [--run] [--json] [--limit N]
```

Example:

```
python -B propagation_check.py C:\NSC\NSC\NoSafeCircle origin/main..HEAD
```

## What it does

1. **Changed modules.** `git diff --name-only <base>..<head>`, keep the `.py`
   files, map each to its dotted module
   (`Pipeline/ExecutionCrew/session_pool.py` -> `Pipeline.ExecutionCrew.session_pool`).
2. **Removed or renamed symbols.** Parse the base and head text of each changed
   file with `ast` (read via `git cat-file`, never imported), collect
   module-level functions, classes, assignment targets and `__all__` entries,
   and report names present at base and absent at head.
3. **Stale references.** One fixed-string `git grep` across *all* tracked files
   — Python, PowerShell, Markdown, YAML and `.github/workflows` — for those
   names. Hits inside the changed files themselves are marked, so a rename
   confined to one file does not read as breakage. Workflow hits are marked
   `[CI WORKFLOW]`.
4. **Tests that import the changed modules.** One `git grep` for import
   statements in test-shaped paths, parsed in Python so that
   `import X.Y`, `from X.Y import a`, `from X import Y as z`, indented
   function-local imports and relative imports all resolve. Tests named by
   `.github/workflows` are marked `[CI]` — this repository names them both as
   paths (`python Pipeline/.../foo_test.py`) and in dotted `python -m unittest`
   form, and both are recognised.
5. **Output.** Removed symbols with their stale references first, then the exact
   commands to run the selected tests. `--json` emits the same as data.
   `--limit N` caps printed hits per symbol (default 10).
6. **`--run`.** Runs each selected test file with `PYTHONPATH=<clone>` and a
   scratch `TMPDIR`, printing path, exit code, elapsed seconds and the last
   meaningful output line. Every spawn uses `creationflags=CREATE_NO_WINDOW`
   (`0x08000000` on Windows, `0` elsewhere), so no console window flashes.
   `DETACHED_PROCESS` is not used anywhere.

Exit codes: `0` fine, `1` a selected test failed under `--run`, `2` bad input.

## Step 4 is the one that earns its keep

Release PR #134 took four rounds of CI fixes. Three of them removed no symbol at
all. Commit `6e718ece2` dropped the string `"contract_locality_auditor"` from the
**value** of the `CREW_SESSION_ROLES` tuple; the tests that broke asserted counts
derived from it ("four roles not idle", "exactly forty leases"). The fourth was
an HTML default moving into a script. A grep for a removed *name* finds nothing
in any of those cases.

So the ordering of trust is deliberate:

- **Step 4 covers value changes**, because it selects every test importing the
  changed module whether or not any name disappeared.
- **Steps 2 and 3 cover the genuine rename**, which step 4 would only catch if a
  test happened to exercise the renamed path.

A clean step-2 result means nothing on its own, and the report says so in its
own output rather than only here.

## Limits, stated in the report itself

- A change to the value of a constant removes no name; steps 2 and 3 see nothing.
- Step 3 is a literal text grep. It cannot distinguish a stale reference from an
  unrelated word that matches, and it does not resolve aliases.
- Step 4 matches import statements textually. A module reached only via
  `importlib`, a plugin registry, a subprocess or a data file is not found.
- Only module-level names are compared. Methods, nested classes and attributes
  are out of scope.
- Multi-line parenthesised `from X import (` bodies contribute `X` but not the
  individual submodules named on continuation lines.
- `--run` proves what the selected tests prove. It is not the full CI matrix.

## Cost

Measured on the No Safe Circle checkout (Linux container, warm page cache,
252 tracked test files, ~150 `.py` paths named across 11 workflow files):

| range | changed `.py` | tests selected | steps 1-4 |
|---|---|---|---|
| 1 commit (`6e718ece2~1..6e718ece2`) | 6 | 24 | **1.1 s** |
| 10 commits | 10 | 25 | 1.3 s |
| 40 commits | 24 | 37 | 1.6 s |
| 200 commits | 399 | 182 | 9.9 s |

A realistic pre-merge range costs about a second, which is inside Vincent's
"if it just takes a minute, then that is fine".

`--run` costs whatever the selected tests cost; the tool adds only one process
spawn per file. On a 24-test selection that is the dominant term by far, so run
it deliberately rather than by habit — the default no-`--run` report is what
belongs in front of every merge.

Three implementation choices keep steps 1-4 fast:

- blobs are read with a single `git cat-file --batch`, not one `git show` per
  file (this alone took the one-commit case from 5.5 s to 1.8 s);
- all removed symbols go into one batched `git grep -F`, so cost is a pass over
  the tree rather than a pass per symbol;
- step 4 greps once for *any* import line and does the matching in Python.
  Handing git one regex alternation per changed module took 330 s on a
  345-module range; the current form takes about 9 s.

## Tests

```
python -B tests/test_propagation_check.py
```

29 tests. Each builds a throwaway git repository under `TMPDIR` and covers: a
removed function still referenced from `.github/workflows`; a renamed class; a
rename confined to one file; a value removed from a tuple (steps 2 and 3
correctly find nothing, step 4 still selects the importing test and `--run`
catches the failure); a changed module with no importing tests; a non-Python
change; `--run` reporting a failing selected test; plus import-form, relative
import, module-mapping and range-parsing units.
