# Repo topology for everything not yet in a repo

Decision document, 2026-09-18 late. Pipeline Maintainer. **Design only:** no code written, no
repository created, nothing moved or deleted; every check below was read-only. Follow-up to
`repo-durability-and-reset-design-v2-20260918.md` (v2), not a rewrite of it. Game repo base:
`main` = `255951482`.

## 1. "Should NSC be the way it is or should we break up into 2 repos?"

**Two. But by adding a second repo, not by breaking the first one up.**

| | Answer |
|---|---|
| **The game repo** (`C:\NSC\NSC\NoSafeCircle`) | **Stays exactly as it is.** Game + `Pipeline` + `Tasks` in one repo. Do not split the pipeline out of it, and do not fold the docs or agent state into it |
| **One new working repo, `nsc-fleet`** | Everything the agents *run on*: the 80 docs, `agent-state`, `C:\NSC\tools`, agent definitions, agent memory. About 6 MB of text |
| **Behind those two, two archives nobody works in** | `nsc-reports` and `nsc-control`: fed by the backup job, never part of a reset, never edited through git |
| **`C:\NSC` the folder** | Stays the way it is. Nothing moves. No `.git` appears in it |

So: **2 repos you work in, 2 archives a job feeds = 4** (v2 had 5). Why each alternative loses:

| Alternative | Why not |
|---|---|
| Split the game repo into game + pipeline | Task checkouts are clones that run `Pipeline` from inside themselves, and contracts are bound to policy hashes in the same tree. Two repos means every reset needs a sha pair. v2's strongest result (one reset repo, no tuple) would be thrown away |
| Fold docs, agent-state and tools into the game repo | Every doc edit becomes a write to pushed `main` under main-write START/END (8 agents, constantly); fleet rules and other agents' state land in every task checkout a crew worker reads; `origin`'s visibility is still unanswered (v2 Q1) and the docs hold email addresses |
| A plain `.git` at `C:\NSC` | Fact 4 and fact 6, measured tonight: 788 top-level dirs, **277 with their own `.git`, 511 without**. Those 511 would silently resolve to the fleet repo; a stray `git add -A` stages against it; the 79 registered worktrees would show as embedded repos (a `git add` of one records a gitlink and **no content**: a false-green backup) |
| A new root outside `C:\NSC` | Measured: **272 path references** to `C:\NSC\<name>.md` across agent definitions, memory, agent-state and the docs themselves. Files cannot be junctioned (only directories can), `CLAUDE.md` must sit at the sessions' working directory, and every session is rooted at `C:\NSC`. The 788-directory problem goes away without moving anything (next table) |
| One repo for everything (fleet + reports + records) | Different trees, different growth (6 MB of text vs 133 MB + ~2.4 MB/day packed), different commit model (a change someone meant vs a 15-minute sweep of logs). Mixing them buries the doc history in log sweeps |

**Is an external git dir over `C:\NSC` workable all day? (fact 4.) Yes, for one reason: ambient
git cannot see it.** `git -C C:/NSC rev-parse` keeps failing, which is the safety property worth
keeping. The repo only ever looks at four top-level names, so the 788 directories, the 79
worktrees and whatever the Cleanup Agent moves are invisible to it (git never descends into an
excluded directory). What it costs and how v2 changes:

| Condition | Detail |
|---|---|
| A wrapper, not raw git | `nsc-repo <name> log\|diff\|show\|commit -m … <paths>\|restore-file <path> <sha>`. Flags per call (`--git-dir`, `--work-tree`), **never** `GIT_DIR` in an environment or profile |
| Verb allow-list | Never `clean`, `reset`, `checkout`, `restore`, `stash`, `add -A` (v2's rule, kept). `restore-file` is `git show <sha>:<path>` to a temp file, then atomic replace |
| **Change to v2:** agents may commit | v2 made the job the only committer, so doc history would be nothing but "sweep 21:15". An agent that wants a real message uses `commit`; one that doesn't is still caught by the sweep. **No step is required of anyone.** Wrapper and job share the job's lock file; a lost race is harmless because the sweep picks it up |
| Not workable for | Anything needing branches, review or IDE git. That is why tools that are really pipeline code still port into the game repo (§4) |

## 2. Where each item lives

| Item | Home | Grouped with | Why |
|---|---|---|---|
| `C:\NSC\tools` (3 MB, 192 files, 6 folders) | **`nsc-fleet`**, tracked at its one real path `/tools/` | docs, agent-state | Operator tooling edited alongside the guides that cite it. The committers that write `main` still port into the game repo (§4); the rest stays here for good |
| `C:\NSC\*.md` (80 files) | **`nsc-fleet`**, `/*.md` + v2's small top-level scripts | — | In place. Once tracked, the Cleanup Agent retiring a stale `CLAUDE_*.md` becomes reversible |
| `C:\NSC\agent-state` (19 files, all written today) | **`nsc-fleet`**, `/agent-state/` | — | Rule-20 todo files change with the guides |
| `~\.claude\agents` (14 files, 100 KB) | **`nsc-fleet`**, via `C:\NSC\linked\claude-agents` (a junction; the data stays where Claude Code owns it) | docs | One decided change touches a guide, an agent definition and memory together (that is the `doc-sync` helper's whole job). It should be one commit and one revert, not two repos. **Replaces v2's `nsc-home`** |
| `~\.claude\projects\C--NSC\memory` (108 files, 708 KB) | **`nsc-fleet`**, via `C:\NSC\linked\claude-memory` | same | Same. Checked: of ~100 `projects\*\memory` folders, **only `C--NSC` is non-empty**, so one junction covers it |
| `.assistant-control` (60 MB raw ≈ 12 MB packed) | **`nsc-control`**, own archive, exactly as v2 §2.1–2.2 | nothing | Machine-written, grows ~2.4 MB/day packed, every log kept. Whitelist by exact name stays: the pipeline writes Unity clones in there (`.sync-*`) |
| `C:\nscrev\reports` (133 MB, 3,936 files) | **`nsc-reports`**, own archive, work-tree `C:\nscrev`, in place, **never moved** | the GER working area | Holds 40 deliverables pinned by `Tasks/NSC-098.yaml` and `Tasks/NSC-099.yaml` on `main`. Byte-exact rules in §3 |
| `ger-contract-revisions-20260916` (271 MB) | **Split three ways** (§4): tools → `nsc-fleet`; drafts and decisions (~2.5 MB) → `nsc-reports`; two scratch clones (~268 MB) → no repo | — | — |

**The junctions (fact 1).** Git for Windows treats a junction as an ordinary directory and walks
through it on `add` (it only special-cases true symlinks).

| Question | Answer |
|---|---|
| What does `nsc-fleet` (work-tree `C:\NSC`) do with `C:\NSC\tools`? | Tracks it once, as real files under `tools/` |
| What about `C:\nscrev\ger-tools` → `C:\NSC\tools\ger`? | It is in a different tree. Only a repo rooted at `C:\nscrev` that **names it** would follow it and store a second full copy. **v2's `nsc-reports` whitelist names exactly those six folders. Delete those entries.** With them gone nothing follows or duplicates a junction |
| Are the junctions more than doc convenience? | **Yes, code depends on them:** `new_task_commit.py:32` and `policy_entry_commit.py:24` do `sys.path.insert(0, r"C:\nscrev\ger-tools")`. Treat the six as permanent; they cost nothing |
| Does git store a junction? | **No.** A restored machine has none. `nsc-fleet` carries `tools\JUNCTIONS.json` (nine entries: six existing, three in `linked\`) and a recreate script; the restore drill runs it |
| Hazard worth one line to the Cleanup Agent | Windows PowerShell 5.1 `Remove-Item -Recurse` is known to delete **through** a junction into its target. Never recurse into a reparse point; remove a junction with `cmd /c rmdir`. This applies to the six that exist tonight |

**The worktrees (fact 6).** 138 registered, 79 under `C:\NSC\_worktrees`. No repo proposed here
contains them: the whitelist never enters `_worktrees`. Their commits are not at risk from
topology at all, because a worktree shares canonical's object store, so v2's backup remote already
covers them. Only uncommitted files in them are uncovered, same as any checkout.

## 3. `reports`: byte-for-byte (fact 8)

| Rule | Why |
|---|---|
| Never moved, never re-exported. The repo is laid over it in place | The pins are `sha256` of the files as they sit |
| `core.autocrlf=false` and a `* -text` attributes line in the git dir's `info/attributes`, **set before the first `add`**; no LFS, no filters | Git stores a blob verbatim unless a text conversion is configured. With none, a clone returns identical bytes |
| Restore drill adds one check | From the scratch clone, recompute the 40 `sha256` values and compare with the two contracts. A mismatch is red |
| End state | The pinned files land in the game repo when NSC-098/099 integrate. Until then `nsc-reports` is their only off-machine copy |

## 4. `ger-contract-revisions-20260916`: what is actually in it

Measured tonight. It is not 271 MB of work; it is 2.5 MB of work and two clones.

| Part | Size | Finding | Home |
|---|---|---|---|
| `scratch\` and `followups-20260917\nsc066\scratch\` | ~268 MB | Two full clones of the game repo. Both HEADs (`688bd05d0`, `7698abac0`) are **on `main`**; no stash, no untracked files; real diffs ignoring line endings are 1 file / 21 lines and 2 files / 63 lines | **No repo.** Disposable once the GER Agent confirms those small diffs are applied drafts |
| `new_task_commit.py`, `policy_entry_commit.py`, `verify_filter.py` | 29 KB | Only copies (confirmed: absent from `C:\NSC\tools\ger`). The first two import `apply_contract` and `main_write` **from `ger-tools`**, so they already run against the installed helpers | **`C:\NSC\tools\ger` → `nsc-fleet`**, then into the game repo with `contract_commit.py` (v2 step 7) |
| `main_write.py` | 2.6 KB | **Stale.** Differs from `C:\NSC\tools\ger\main_write.py` (5.5 KB, newer). Shadowed at import time, so harmless today, but it is what "tools in two places" produces within a day | Retire; do not copy out |
| `validate_in_memory.py`, `quiet.py`, `build_supersede_cascade.py`, two `.bak`/`.retired` | small | Helpers and dead files | GER Agent's call; default: first three go with the tools |
| ~50 per-task patch scripts, revision JSON drafts, `COMMIT_MESSAGE.*`, `*_DECISIONS.md` | ~2.5 MB | Provenance of each revision. The finished output is already on `main` | **`nsc-reports`** whitelist entry `/ger-contract-revisions-20260916/`, excluding `scratch/` at any depth. In place; the GER Agent keeps working in it undisturbed |

**How the tools come out without touching live work:** copy (not move) the three into
`C:\NSC\tools\ger`; at the GER Agent's next quiet point it replaces each original with a
three-line shim that runs the installed one, so there is never a second editable copy. That edit
is in the GER Agent's folder and lane, not mine.

**Going forward (proposal for the GER and Documentation Agents):** scratch clones go under
`C:\nscrev\<topic>` like every other agent's, so a working area never again looks like 271 MB.

## 5. The reset boundary: does v2's rule still hold?

**Yes, with one refinement.** "Anything that must roll back *with a task* lives in one repo."

| Item | Rolls back with a task? | Verdict |
|---|---|---|
| Docs, agent-state, agent definitions, memory | No. Fleet-level; reverted on their own (v2 §3.4), now in one repo instead of two | Holds, improved |
| `.assistant-control` | No. Undo reads ledger entries, never a commit of `nsc-control` (v2 §3.1) | Holds |
| Reports, GER drafts | No | Holds |
| **Pinned deliverables in `reports`** | **`main` depends on bytes outside the game repo.** They are never rolled back because they are immutable and addressed by hash | **Refinement: the rule is about *mutable* state.** Immutable pinned inputs may live outside if their hash is verified (§3). Durability was the real gap, not reset |
| Tools that write `main` (`contract_commit`, `new_task_commit`, `policy_entry_commit`, `main_write`, `verify_filter`) | Not rolled back, but version-locked to the contract schema and policy format | **Still belong in the game repo (v2 D3).** Do not record a fleet sha in contract commits to compensate: that is the cross-repo tuple by the back door |
| `jobs`, `session`, `astra`, `art`, the viewer helper | No lock to the repo's schema | **Change to v2 step 7:** port by coupling, not by folder. These stay in `nsc-fleet` permanently. Step 7 shrinks from "72 `.py`, weeks" to the `ger` committers and whatever `Pipeline` imports |

## 6. Sequencing, with the Cleanup Agent moving things underneath

Nothing below moves, renames or deletes a file, so none of it can collide with a cleanup pass.
Everything that needs a push needs Vincent's go.

| When | Step | Conflict with cleanup? |
|---|---|---|
| **Tonight, first** | **v2 steps 1–2, still not done** (checked tonight: no bundle, no zip in OneDrive). Amended zip list: `C:\NSC\*.md`, `agent-state`, `C:\NSC\tools` **by its real path only** (zipping the six junction paths too doubles it), `.claude\agents`, `.claude\projects\C--NSC\memory`, the GER folder minus the two `scratch` clones, **and `reports`** (133 MB; it holds the pinned deliverables). Confirm *synced* | None: read-only |
| Tonight | One message to the Cleanup Agent: add `C:\NSC\tools`, `C:\NSC\agent-state`, `C:\NSC\linked`, `C:\nscrev\backup` to the named guards; the junction rule from §2 | — |
| Tonight | Create three private repos: `nsc-fleet`, `nsc-reports`, `nsc-control` (plus v2's `NoSafeCircle-backup`) | None |
| Tonight | `nsc-reports` first commit: `/reports/` and the GER folder minus clones. gitleaks first; attributes before first add; `ls-remote` verify; pinned-hash check from a scratch clone | None. `reports` is on the never-move list and the GER folder is a named guard |
| Tonight | `nsc-fleet` first commit: `/*.md`, top-level scripts, `/agent-state/`, `/tools/` | None. No cleanup pass touches those names; the 416 proposed moves are invisible to the whitelist |
| **Wait: a two-minute test** | `linked\` junctions for agents and memory. I believe git follows junctions and the code says so, but **the brief forbade creating even a scratch repo, so it is untested here.** Test in a scratch folder under `C:\nscrev`; the restore drill (14 agents, 108 memory files present as files) is the standing proof. **If it fails: v2's `nsc-home`, unchanged** | None |
| Wait: GER quiet point | The three tools copied into `C:\NSC\tools\ger`; shims by the GER Agent | None |
| Wait: the backup job (v2 step 5) | `nsc-control` (needs root enumeration and the generated whitelist), the 15-minute sweep, the `nsc-repo` wrapper, status line | None |
| **Wait: until the cleanup passes settle (review 2026-10-09)** | Anything that moves: retiring junctions, renaming `C:\NSC\tools`, touching `_worktrees`. **Recommendation: never move the docs at all** | This is the only class that can collide |

## 7. What I would not put in a repo

| Not tracked | Reason |
|---|---|
| The two GER `scratch` clones, and any clone or worktree | They are git data. Their commits are covered by v2's hub fetch; tracking the files stores a gitlink or 184 MB of duplicate |
| The six junction paths under `C:\nscrev` | Tracking them stores `C:\NSC\tools` twice with two places to revert |
| `~\.claude` apart from `agents` and the one `memory` folder | `.credentials.json` is in that folder; `sessions`, `history.jsonl`, `telemetry`, `cache`, `file-history` are large, private and rebuildable. Linking two named folders (not whitelisting a tree that holds credentials) makes leaving them out the default. `skills\` (8.3 MB) and `settings.json`: add as a third junction only if Vincent wants them (v2 included them) |
| The 24 `.bundle` files and the `.tar` at the top of `C:\NSC` | v2's answer stands: fetched into the hub as refs, not committed as 200 MB of blobs |
| `.sync-*`, `*.lock`, anything holding a `.git`, Unity `Library`, `__pycache__` | v2 §2.2, unchanged |
| `C:\NSC-History-20260918` | Quarantine with its own manifest and review date; tracking it defeats deleting it |
| The 788 scratch directories | Disposable by definition; unique commits in them are the hub's job |
| The stale `main_write.py` and the `.bak`/`.retired` scripts in the GER folder | Once history exists, `.bak` files are what git is for |

## 8. Changes to v2, in one place

| v2 said | Now | Why |
|---|---|---|
| Five private repos | **Four.** `nsc-ops` + `nsc-home` + the interim-tools part of `nsc-reports` become `nsc-fleet` | Agent definitions, memory and guides change together; the tools now live under `C:\NSC` |
| `nsc-reports` whitelist names six tool folders under `C:\nscrev` | Deleted | They are junctions since tonight; following them duplicates `C:\NSC\tools` |
| The job is the only committer (§2.1) | Agents may commit through the wrapper; the sweep remains the safety net | Doc history worth reading, no added step |
| All six tool folders port into the game repo (step 7, weeks) | Only the tools coupled to the contract schema port; the rest stay in `nsc-fleet` | Coupling, not folder, decides |
| GER working area not mentioned | Split three ways (§4) | Only copies of three tools; 98% of its size is two disposable clones |
| Restore drill: counts and parses | Adds: recompute the 40 pinned `sha256`; recreate the nine junctions | Facts 1 and 8 |
| Reset rule as stated | Holds; applies to mutable state (§5) | Pinned deliverables |
| Unchanged | External git dirs (Q7), whitelist-only, no `+` refspec, `refs/history`, "green means verified", `nsc-control` design, the whole undo half | — |

## 9. Decisions for Vincent (each has a default; "yes to all" works)

| # | Question | Default |
|---|---|---|
| T1 | Two working repos (game as is + `nsc-fleet`) and two archives, replacing v2's five? | **Yes** |
| T2 | Agent definitions and memory join `nsc-fleet` through two junctions in `C:\NSC\linked\`, falling back to v2's `nsc-home` if the two-minute test fails? | **Yes** |
| T3 | Only contract-coupled tools port into the game repo; `jobs`, `session`, `astra`, `art` and the viewer helper stay in `nsc-fleet`? | **Yes**; the Art Director decides for `art` |
| T4 | Go for tonight's zip and bundle (v2 Q5), with `reports` and the GER drafts added? | **Yes — it is still the only thing protecting any of this** |

Handoffs this implies, none sent (design only): Cleanup Agent (guards and junction rule), GER Agent
(confirm the two clones are disposable; shims at its quiet point), Documentation Agent (scratch
clone convention), Release Agent (repo creation and first pushes, on Vincent's go).
