# Current Task Orchestrator Context

Last context update: 2026-09-02

> **Important:** Dynamic Git/GitHub/local-checkout facts below are last-verified or
> last-session-reported state, not standing authority. Before any mutation, re-read current Git,
> TaskGraph, GitHub Issue/workflow, remote refs, and relevant local checkout state.

## Context-maintenance rule: preserve durable warnings

`CURRENT_CONTEXT.md` has two different kinds of information and they must not be treated the same:

1. **Dynamic continuation state** — current branches, SHAs, open work, checkouts, Issues, task state.
   This should be refreshed or replaced when it becomes stale.
2. **Durable operating memory** — hazards already encountered, command/runner safety rules, recovery
   rules, handoff style, review discipline, and explicit things not to repeat. These rules exist
   because real failures already happened. **Do not delete or aggressively compress them merely
   because the dynamic context changed.**

When refreshing this file, preserve durable warnings unless a newer repository standard explicitly
supersedes them. If one is superseded, replace it with the newer rule and point to the authoritative
document; do not silently remove the warning.

The detailed operating guidance below is intentionally somewhat repetitive with repository rulebooks.
That repetition is useful here: this file is the bootstrap context a new ChatGPT window reads before
it knows which other documents matter.

## First action in the next window

Do **not** ask Vincent to reconstruct the Software Architect architecture.

1. Re-read live `main`.
2. Re-read the NSC-042 task branch/check-out and its managed Issue/workflow state.
3. Determine whether the revised **narrow DoorPrototype builder-output integration** was already
   run after this context was written.
4. If not, continue that exact bounded slice; then finish NSC-042 from an exact clean post-builder
   commit.

Primary handoff:

`Docs/AI-Pipeline/Historical-Context-Sessions/2026-09-02-software-architect-live-production-and-nsc-042.md`

Earlier architecture rationale:

`Docs/AI-Pipeline/Historical-Context-Sessions/2026-09-01-software-architect-integration.md`

## Current objective

The Software Architect infrastructure is in production and has already been exercised on real game
work. Stop building speculative infrastructure.

The immediate goal is to finish NSC-042 and make one narrow workflow correction proven necessary by
that real task:

```text
AI candidate changes DoorPrototypeSceneBuilder.cs
        ↓
run DoorPrototypeSceneBuilder.Build()
        ↓
capture intended builder-owned generated outputs
        ↓
automated validation
        ↓
commit/push exact clean task state
        ↓
Vincent validates that exact commit
        ↓
PASS → delivery/integration
```

Intended builder-owned output boundary selected at the end of the session:

```text
Assets/NoSafeCircle/DoorPrototype/**
Assets/Scenes/DoorPrototype.unity
```

Unity/editor side effects outside that boundary — especially `ProjectSettings/**` — are not
automatically part of the task commit unless they were already part of the verified AI candidate.

## Live GitHub state verified immediately before this documentation repair

```text
repository: cathode26/NoSafeCircle
main:       a7b8e2faee69f7c70acf0ea57922ed6bd3b061c0
main tip:   docs: refresh 2026-09-02 orchestration context

NSC-042 remote:
  branch: nsc-042-seamless-scalable-wall-tiling-for-long-isometric-walls
  HEAD:   2a4861235e8ba363d4b85e8d0a77a807db5aec26

broad experimental branch:
  pipeline/pre-handoff-unity-generation-hygiene-20260902-004901
  last recorded HEAD: 473cf101502108b0844f7151f25c8255f30d8d45
```

This documentation repair itself advances `main`, so the SHA above is intentionally the observed
pre-repair authority point, not a promise about the current tip after this file is committed.

Local checkout cleanliness is **not** verified here. The last session reported that the NSC-042
builder had run and left builder-generated files plus two unrelated ProjectSettings side effects
dirty. Re-read before restore/stage/commit.

## Production architecture that is already done

Do not reopen these as architecture projects:

- Software Architect Acceptance Gauntlet v1.
- Execution Routing v1.
- Decomposition Authorization Binder v1.
- Real `PollingOrchestrator` acceptance adapter for ordinary cycles.
- Windows GitHub UTF-8 Issue-read boundary.
- Windows-host Game Task Agent controller boundary.
- Canonical mutation API precedence.
- Two-strike runner/proof escalation rule.
- Vincent human-action notification.
- TaskGraph review-work materialization.

Key production milestones are recorded in the 2026-09-02 handoff.

The Software Architect model advises; deterministic Python owns task eligibility, claims, Issue
workflow, checkouts, routing, and mutation. Workers receive explicit task IDs.

## Strategic rules

```text
NO NEW PIPELINE FEATURE unless actual integration/game development proves it is needed.
```

- TaskGraph is structural/task authority.
- Managed GitHub Issues are durable operational/workflow authority.
- Git claims are short-lived race protection.
- START is never cached.
- Integration uncertainty fails closed as WAIT.
- HUMAN_REVIEW is only for real design/canon/task-authority ambiguity.
- Default live worker count remains conservative until real use justifies more.
- Scenario J remains deliberately pending; do not create a concurrency project just to make it
  green.

## NSC-042 specific context

`Tasks/NSC-042.yaml` is the active, concrete, single-agent task:
**Seamless Scalable Wall Tiling for Long Isometric Walls**.

The task implementation commit exists remotely at `2a486123...`. Human/runtime rebuilding exposed
that the generated Unity state is part of the deliverable. Delivery correctly stopped when the
validated checkout was dirty rather than falsely claiming the earlier commit was what Vincent
tested.

A larger reviewed branch at `473cf101...` implements generalized pre-handoff generation/hygiene,
but it grew to 11 files and is intentionally held. Do not merge it automatically.

The chosen next production change is the smaller builder-output capture rule above.

## Operational hazards already encountered

Do not rediscover these by trial and error.

- Historical context is never live authority. Before mutation, re-read Git, GitHub, TaskGraph,
  managed Issue/workflow, claim/lease state, relevant branch/ref state, and the actual checkout.
- Paste-ready operator commands target **Windows PowerShell 5.1** unless explicitly stated
  otherwise. Docker Compose uses the project convention `-p nosafecircle` where the established
  workflow requires it. Pipe prompt text through stdin; do not use Bash `< prompt.md` syntax in
  PowerShell.
- The convention is what matters; **do not freeze one provider CLI invocation forever**. Reuse the
  repository-approved provider service/runtime and current model configuration rather than copying
  a historical invocation literally.
- Prefer repository/container provider execution over unnecessary host provider CLIs. The
  orchestration controller itself is different: it must run on the Windows host because it owns
  host Git, authenticated GitHub, Docker, claims, Issues, checkouts, and workflow state.
- GitHub CLI machine output is UTF-8 regardless of the Windows locale. Machine data must be decoded
  and parsed as machine data, not mixed with human diagnostic streams.
- Host Git is final changed-file authority for the real Windows checkout when Linux bind mounts show
  CRLF/stat projection noise. Do not "fix" unrelated files because a container reports mass line
  ending differences.
- Never use a global `safe.directory` workaround. Fix the specific checkout/ownership boundary.
- Do not `git add .` or `git add -A` for bounded reviewed work. Stage exact reviewed paths and prove
  the staged path set.
- Do not reset, clean, restore broad directories, delete claims, move refs, or repair durable state
  by guesswork merely to make a checkout look clean.
- Unity can dirty generated assets, scenes, and unrelated editor settings. Capture only the exact
  authorized/generated boundary and distinguish intended output from editor side effects.
- Close Unity when deterministic validation/staging requires a stable workspace.
- Substantial provider jobs use the canonical `.claude-jobs` / `.codex-jobs` writable roots and
  print/preserve their job directory so output can be recovered.
- Reuse canonical mutation APIs before inventing wrappers or alternate write paths.
- After **two failed runner/proof attempts**, stop incremental wrapper guessing. Preserve state and
  use a bounded read-only engineering diagnosis before another assistant-authored mutation attempt.
- A timeout, transport error, missing final marker, or wrapper exception does **not** prove that a
  durable mutation did not occur. Read back authority before retrying.
- Keep deterministic setup/preflight separate from expensive provider execution where the command
  standards require it. A successful setup phase is not permission to blindly replay the provider
  phase after an uncertain failure.
- Native process exit code is authority. Ordinary stderr from Git/Docker/gh/Python is not itself a
  proof of failure, and combined diagnostic output must not be parsed as filenames, SHAs, JSON, or
  exact machine state.

Repository rulebooks that remain authoritative:

```text
Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md
Docs/AI-Pipeline/OPERATOR_COMMAND_TEMPLATE.md
Docs/AI-Pipeline/AGENT_PROMPT_AND_RUNNER_CONSTRUCTION_RULES.md
Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md
```

## Preferred ChatGPT operator handoff style

Substantial work reaches Vincent as a **downloadable artifact plus one guarded command**, never as
a giant inline prompt that must be reassembled by hand. This is part of the safety model: it
prevents long-prompt corruption, pins exactly what was run, removes most PowerShell quoting/parser
mistakes, and makes handoff and recovery straightforward. Use it by default.

```text
ChatGPT defines bounded work
        ↓
ChatGPT creates a downloadable prompt/script artifact
        ↓
ChatGPT computes and displays the exact SHA-256
        ↓
Vincent downloads it (normally to Downloads)
        ↓
ChatGPT gives ONE paste-ready guarded PowerShell command
        ↓
the command locates the exact artifact by filename pattern AND hash
        ↓
the command verifies checkout / branch / HEAD / working-tree state
        ↓
the provider or runner executes
        ↓
Vincent returns the complete final report / [DONE] / [RECOVERY] block
```

**Prompt artifacts.** For a large provider task, create a `.md` prompt file, give it a descriptive
download link, and publish its exact SHA-256 directly under that link. The command finds the file
by filename pattern *and* hash, reads it with `Get-Content -LiteralPath ... -Raw -Encoding UTF8`,
and pipes it through stdin to the existing Docker provider service using `docker compose -p
nosafecircle` with the project-approved Claude/Codex service and model settings. Never use Bash
`< prompt.md` syntax in PowerShell.

The convention is what matters; do not freeze one provider CLI invocation forever.

**Runner artifacts.** When orchestration logic is too complex for a safe one-liner, ship a
downloadable `.ps1` or `.py` runner with its SHA-256 and a *short* wrapper that finds the exact
file by hash, preflights it, runs it, treats the native exit code as authority, and tells Vincent
not to rerun blindly on failure. Preflight means
`[System.Management.Automation.Language.Parser]::ParseFile(...)` for PowerShell and
`python -m py_compile` for Python where useful. Keep substantial deterministic setup and the
expensive provider invocation in separate phases where the command standards require it.

**Guards.** A paste-ready command normally fences expected checkout, expected branch, expected
HEAD/parent, clean or exactly-expected dirty working tree, empty index when required, the exact
prompt/runner hash, and the exact allowed path boundary where practical. Re-read current authority
for those values; never copy them out of historical context.

**Style Vincent expects:** one clear next action; a downloadable file instead of an inline wall of
prompt; the exact SHA-256 immediately under the download; one PowerShell 5.1-safe paste-ready
command; a clear `[READY]` / `[DONE]` / `[RECOVERY]` ending; explicit instruction about what output
to send back; and an explicit "do not rerun blindly" warning whenever durable mutation might have
occurred. Small harmless read-only commands need no artifact — do not create files for trivial
commands.

**When a downloaded runner fails,** distinguish runner/verifier bugs from product defects. If no
durable mutation occurred, fix the runner and continue. If mutation may have occurred, re-read
durable authority before any retry, and write a continuation/recovery runner instead of replaying
work that already succeeded.

## Working method for future agents

**Continue using this workflow unless a concrete reason requires deviation.**

```text
bounded implementation
→ deterministic/host validation
→ independent adversarial review
→ targeted correction
→ revalidation
→ guarded exact-path commit
→ deliberate integration
→ move on
```

1. **Re-read deterministic authority before mutating.** Branch, HEAD, origin `main`, working
   tree/index, relevant TaskGraph state, relevant Issue/PR/claim state. Historical context — this
   file included — never substitutes for that read.

2. **Define ONE bounded slice.** Explicit objective, invariants, exact allowed file boundary,
   explicit no-go files/actions, expected tests. Do not mix unrelated fixes.

3. **Use an isolated branch/checkout** for substantial work — preferably a fresh standalone clone
   when ownership/EOL/history risk exists. Never casually mutate the canonical live Gauntlet or a
   production checkout. Parallel lanes only when their boundaries are genuinely disjoint.

4. **Delegate implementation to one strong coding agent.** File-based, hash-pinned prompts; large
   prompts piped through stdin; Docker Compose with `-p nosafecircle`; no unnecessary host provider
   CLIs. The implementer does **not** stage, commit, push, merge, or mutate live authority unless
   the reviewed task explicitly grants that boundary.

5. **Validate the surviving patch independently of the implementer's claims.** Inspect the actual
   Git diff/status, prove the exact changed-file boundary, run focused deterministic tests, and run
   host-side validation when Docker/Windows behavior differs. Host Git is final authority for
   Windows bind-mount CRLF projection noise.

6. **Have a different model review high-risk work.** The implementer never grades its own patch.
   Prefer another provider/model family; use read-only review containers; ask for concrete
   blocker/important findings, not speculative redesign.

7. **If review finds a real defect, keep the good patch.** Issue one bounded correction prompt for
   the exact findings. Do not restart the implementation unless the architecture is actually wrong.
   Re-run only the tests/review the changed boundary needs.

8. **Commit only after review and validation pass.** Stage exact paths; never `git add .` /
   `git add -A`; use guarded/fenced commands; use the automation identity
   `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>` where that workflow
   applies; keep local foundation commits unpushed until the integration/release point is chosen.

9. **Integrate deliberately.** Re-check parent/HEAD before merge/cherry-pick, preserve exact
   reviewed commit identities, and run integration-specific validation after combining
   independently reviewed slices. Do not amend an already-reviewed foundation commit to add a new
   concern — add a small separate integration commit.

10. **Fail closed operationally.** A runner that failed *before* mutation is a runner bug, not a
    repository failure. If a runner may have crossed a durable boundary, do **not** rerun blindly —
    re-read durable authority first. Preserve worker identity, lease identity, continuation/output
    roots, and tested commit identity when resuming. Never delete claims or reset/clean/repair
    durable state by guesswork.

11. **Use the project's command standards.** Windows PowerShell 5.1-safe; native exit code is
    authority; separate deterministic setup/preflight from the expensive provider call; file-based
    UTF-8 prompts piped via stdin, never Bash `<` in PowerShell; Compose project `nosafecircle`;
    no global `safe.directory` workaround; exact-path staging and bounded destructive operations
    only.

12. **Keep architecture work subordinate to shipping the game.** Parallelize independent work to
    save calendar time. Once a subsystem is reviewed and sufficient, move on. Do not create another
    infrastructure phase for hypothetical future problems.

Do **not**: rebuild the design because a new idea appeared; ask Vincent to restate architecture
already captured here; rerun expensive accepted proof work without new evidence; or treat a
reviewer nit as a new architecture project.

## Documentation merge status

This section is retained because the old `## Outstanding documentation merge` warning was useful,
but its old live status is no longer true.

- PR #108, **Docs: add agent prompt and runner construction rules**, was merged on 2026-09-01.
  Its merge commit was `f80e077fbdd79180c020667710d4b35edacc61e5`.
- PR #110, **Docs: checkpoint live Gauntlet context**, was closed without merge and is superseded.
  Do not revive or merge it by inertia.
- The base operator command standards/template and the companion prompt/runner construction rules
  are therefore already on production `main`; future agents should read and use them rather than
  treating them as an outstanding documentation task.

## Known documentation drift

Do not assume every document with `CURRENT` in its name is actually current.

- `Docs/AI-Pipeline/CURRENT_STATE.md` is stale relative to production. As observed during this
  repair, it still names an older merged baseline (`fabb221c...`) and describes the Software
  Architect polling work as uncommitted/under-review/not-live. Treat those status statements as
  historical until that file is updated by an authorized documentation task.
- The immutable `2026-09-01-software-architect-integration.md` handoff correctly records what was
  true at that session boundary, including local/not-yet-main statements. Do not reinterpret those
  historical statements as current authority. Current `DECISIONS.md` and the
  `Software-Architect-Orchestrator/` documentation on `main` contain later integrated architecture
  material.
- Historical SHAs, checkout paths, PR states, Issue states, worker counts, and branch cleanliness in
  any handoff are evidence of the recorded session only. Re-read live authority before mutation.
- A documentation file being newer by commit date does not automatically make every embedded
  dynamic fact authoritative; read the content and compare it with Git/TaskGraph/GitHub.

## Exact next action

> Verify current `main`, TaskGraph, NSC-042 branch/checkout, and managed Issue state. If the narrow
> builder-output integration is still pending, implement/review it from current `main` with the
> exact output boundary above. Then create/push the clean post-builder NSC-042 commit and validate
> that exact commit before delivery.

## Do not repeat

- Do not ask which of A/B/C finished; all three were integrated earlier in this session history.
- Do not rerun old Gauntlet Phase A, the retired 10-worker wave, or old Stage-5 Slices 4-8.
- Do not redo accepted A/B/C reviews.
- Do not redo the resolved UTF-8, host-controller, CRLF-validation, or real-adapter investigations
  without new evidence.
- Do not merge the broad `473cf101...` branch by default.
- Do not use the superseded `Generated/ArchitecturalTiles/**`-only builder boundary.
- Do not reconstruct or redesign the Software Architect because a new window lacks context; read
  the recorded architecture first.
- Do not rerun expensive accepted proof work merely to regain confidence after a context switch.
- Do not silently delete durable warnings from this file during the next dynamic-state refresh.
