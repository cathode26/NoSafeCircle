# One design question (and one already-settled one) from the ExecutionCrew CI-coverage fix — for Vincent

Written by the Release Agent, 2026-09-18. Promised to Pipeline Maintainer on 09-18 ~07:08 UTC ("I'll add the unreachable-code design question... to what I write up for Vincent alongside the auto-discovery question") and not delivered until now — caught as a live gap during the 09-18 handover-pass stranger test. Both questions came up while fixing the CI gap that let `execution_crew_smoke_test.py` sit broken 4 days undetected (`ci/add-executioncrew-coverage` @ `047e5488f`, still queued for merge as of this writing).

**Update, same day, before this was even read:** question 2 below turned out to be already settled — Pipeline Maintainer had forgotten committing the fix. Left the section in with its correction rather than deleting it, since "we asked this and then found out it was already done" is itself worth recording.

## 1. Explicit CI test lists vs. auto-discovery

**The problem, Pipeline Maintainer's framing (09-18 07:04 UTC):** `assistant-candidate-ci.yml`'s "Run focused orchestration checks" step runs a hand-written list of test module names. A suite is covered only if someone remembers to add it to that list — which is exactly how `execution_crew_smoke_test.py` went unnoticed for 4 days after `6e718ece2` broke it. The fix just landed (`ci/add-executioncrew-coverage`) adds 5 more names to that same kind of list — it closes today's gap but doesn't change the failure mode; the next new test file can still silently go uncovered.

**Two options:**
- **Keep explicit lists, add a trip-wire.** Something greps `Pipeline/*/tests/*_test.py` (or per-package) and fails CI when a file exists that no workflow's list references. Keeps today's control (a human/agent decides what runs and when) but stops silent drift.
- **Move to auto-discovery.** Glob-based test collection (`Pipeline/*/tests/*_test.py`) instead of hand enumeration. A new suite is covered the moment it exists, no PR needed to add it to a list. Risk: an experimental/WIP test file could start running in CI before anyone means it to, and CI runtime grows with every new file whether or not it's meant to gate merges.

Pipeline Maintainer's own words: "If you would rather keep an explicit list for control, that is a reasonable call, but then something has to fail when a suite exists and is unlisted, or it will drift again." Neither of us picked one — this needs your call. Low cost either way (a few lines), the choice is about failure mode, not effort.

## 2. ~~Unreachable `contract_locality_auditor` code in `run_crew.py`~~ — SETTLED, no decision needed

**What was there:** `6e718ece2` (2026-09-14) removed `contract_locality_auditor` from `CREW_PROFILE_ROLES["full"]` — the last profile that carried it — but didn't remove the code that runs it. The audit block at `run_crew.py:2701` was guarded by `if "contract_locality_auditor" in required_roles:`, and no profile contains that role anymore, so the block, its prompt, its schema, and its role class were unreachable on main. Both Pipeline Maintainer and Game Agent independently flagged this while fixing the drift it left behind in test assertions, and both of us treated it as an open design call ("reinstate non-blocking, or delete").

**It's already decided and done.** Pipeline Maintainer's own commit `55f61230c` (2026-09-17, "ExecutionCrew: drop the unreachable contract locality auditor branch," 41 lines deleted) already removed it — they'd forgotten writing it. It's one of 3 commits on branch `fix/retired-auditor-test-debt` @ `ca13f7511` in `C:\nscrev\ci-134-fix`, which also fixes `execution_crew_smoke_test.py` itself (the 4-days-broken suite from the auto-discovery question above). I verified independently 2026-09-18: the branch merges cleanly onto current local main (`git merge-tree`, zero conflicts) and `execution_crew_smoke_test.py` passes at that tip. Queued for the Game Agent to merge on your go, same as the ExecutionCrew CI-coverage fix already waiting.
