# Current Task Orchestrator Context

Last context update: 2026-09-01

> **Important:** Every dynamic Git/GitHub/local-checkout fact below is **last session-reported
> state**, not authority. Before any commit, push, PR, merge, claim, checkout mutation, graph
> application, or workflow transition, re-read the current repository, the local checkouts, and
> GitHub.

## First question in the next window

> **First ask which of the three current parallel tracks finished and request its final report.
> Do not ask Vincent to reconstruct the architecture from scratch.**

The architecture is decided. The remaining work is review, integration, proof, and then game
production.

## What architecture we are building now

One human-started **supervised polling Software Architect** that assigns work, plus deterministic
Python that owns all authority.

```text
human starts ONE architect session
        ↓
architect polls TaskGraph state, durable Issue state, active branches/reservations
        ↓
architect reasons about integration/merge surfaces, design seams, decomposition need
        ↓
architect returns START / WAIT / HUMAN_REVIEW per candidate
        ↓
deterministic Python owns claims, leases, checkouts, launches, graph mutation
        ↓
worker receives an EXPLICIT task ID
```

This replaced the older decentralized model in which generic workers selected their own work.

Non-negotiable architect rules (**ADR-045**, currently on the local architect branch, not yet on
production `main`):

- The worker never self-selects. It receives an explicit task ID.
- **Uncertainty about integration conflict means WAIT**, not HUMAN_REVIEW, and not a TaskGraph
  mutation. WAIT is per-candidate and reversible.
- **HUMAN_REVIEW is reserved for real design/canon/task-contract authority ambiguity.** It
  requires a named escalation category plus a non-empty question. Merge/integration uncertainty
  structurally cannot reach a human.
- WAIT and HUMAN_REVIEW may be cached; **START is never cached** and failed invocations are never
  cached.
- The architect's own model is configured at session start; it chooses the *worker's*
  intelligence, not its own.
- **Default worker count remains 1** until the acceptance Gauntlet proves more is safe.
- The architect cannot assign a worker while it is mutating the graph — one internal lane.
- The model proposes; deterministic Git, TaskGraph, evidence, and the human retain authority.

## What is already complete

### Production `main` (last reported)

```text
repository:  cathode26/NoSafeCircle
main:        fa5da9f03343e457af042598bfb83526926123e5
```

That main contains the Stage-2 bulk state observation scaling repair — a single pinned
conformance evaluation context reused across bulk and recursive aggregate evaluation, replacing a
fan-out that reached roughly 34,000 Git subprocesses per planning observation.

### D1C deterministic foundation — reviewed, local, unpushed

```text
Slice 1  c082b66a6d0496ff737b16eedf894d46b2dff072
Slice 2  1219ada824a31a36d0a103450fa552de3aa7d357
Slice 3  67bc67c8340a8351c0ad2fe5299bc59e6183f5fe
```

Slices 1-3 are a **completed** deterministic graph-mutation subsystem. They survived the
architecture pivot because they are useful regardless of who calls them.

### Polling Software Architect v1 — reviewed, local, unpushed

```text
commit  fe051e5f4dc7c3f2a73d185563ce7411df57fa35
branch  orchestrator/polling-architect-v1
```

### Dedicated integration branch

```text
checkout  C:\NSC\NSC\SoftwareArchitectIntegration-v2
branch    orchestrator/software-architect-integration
HEAD      c32ac5fe6de0e5f5d9bf440f4f045846c4a6dcdd
```

Contains the reviewed D1C chain and the reviewed Software Architect commit as ancestors.

### Old private Gauntlet — frozen accepted evidence

```text
accepted private main  2fe8483d805c7071570a06f434c6912c9514dc4f
```

It proved Stage 1-4 primitives, resume priority, human holds, repository binding, and real
two-worker CAS claim contention. Phase A and Phase B are complete accepted evidence.

## What must never be rerun

- **Never rerun old Gauntlet Phase A.**
- **Do not run the retired 10-worker decentralized wave.** It tested a design we no longer
  operate.
- Do not mutate the old private Gauntlet repository; preserve it as frozen historical evidence.
- Do not rebuild the 85-task fixture, the Fibonacci/dice/hybrid synthetic mechanic, or the
  automated review simulator.
- Do not implement old Stage-5 Slices 4-8 as originally designed. Slice 4 shrinks to an audit /
  authorization artifact; Slice 5 is obsolete; Slice 6a becomes defense-in-depth only; Slice 6b is
  replaced by a singleton critical section plus affected-state re-observation; Slice 8 is retired.
- Do not redesign the Software Architect. Do not add a fourth architecture project.
- Do not recommit the D1C slices or the architect commit; verify the existing SHAs first.

## Three tracks in flight at the last session boundary

Each has its own checkout and branch so they do not block each other. Each needs: read its final
report -> independent review -> fix only blockers -> commit locally.

### A. Software Architect Acceptance Gauntlet

```text
checkout  C:\NSC\NSC\SoftwareArchitectGauntlet
branch    test/software-architect-gauntlet-v1
state     UNCOMMITTED at the checkpoint
```

Twelve files under `Gauntlet/SoftwareArchitectAcceptance/`. After an audit correction round:

- the active manifest was reduced to **13 scenarios** (A-J); **K/L/M are future specs**, preserved
  in `LIVE_PROOF_CHECKLIST.md` §7, and are **not** active acceptance scenarios;
- `adapter_kind` was **removed from the package entirely**;
- arbitrary injected adapters are **harness-only** and have no code path to a real PASS;
- **real acceptance is verifier-owned**: `run_acceptance()` takes no adapter parameter and
  constructs `RealPollingArchitectAdapter` internally.

Last independent review found **three verifier/fixture-authenticity blockers**:

1. per-step event evidence — a later/final observation could satisfy an earlier scenario step, so
   decision-only behavior could manufacture a real PASS;
2. grounded live evidence — the live verifier checks event shape, not a complete grounded run
   against the actual source repository and scenario state;
3. forgeable fixture-cleanup ownership — ownership handles can be forged, permitting deletion of
   foreign temp directories.

A final bounded correction was prepared/running at the session boundary.

> **Ask for the latest final-safety-correction report before treating the new Gauntlet as approved
> or committing it.** The counts above describe the last *completed* baseline, not the corrected
> package.

### B. Execution Routing v1

```text
checkout  C:\NSC\NSC\ExecutionRouting
branch    orchestrator/execution-routing-v1   (based on integration HEAD c32ac5f...)
```

The architect recommends `fast | standard | deep` and may prefer `openai | claude |
no_preference`. **Deterministic Python owns the actual provider, model, reasoning effort,
supervisor model/effort, and turn budget.** Model names are operational configuration, never
TaskGraph or canon authority. Automatic `fast -> standard -> deep` escalation is forbidden in v1.

Implementation was prepared/running; inspect the latest report.

### C. Decomposition Authorization Binder v1

```text
checkout  C:\NSC\NSC\DecompositionAuthorization
branch    orchestrator/decomposition-authorization-v1   (based on c32ac5f...)
```

A pure validation slice — no Issue write, no model call, no D1C call, no scheduler mutation. It
binds the exact D1B.2 reviewed candidate, exact task contract bytes, exact `GraphDeltaPlan` plan
ID, exact canonical plan SHA, and the human authorizer. Anything mismatched returns a typed
non-authorized result. **D1B.1 cannot authorize in v1.**

Implementation was prepared/running; inspect the latest report.

## Exact integration that comes after the three tracks

```text
1. merge Routing + Authorization into orchestrator/software-architect-integration
2. persist validated decomposition authorization in durable managed-Issue authority
3. wire Software Architect → D1B.2 → independently authorized plan
       → apply_graph_delta(expected_head=freshly_reobserved_head)
4. reconcile the legitimate pre-D1C Issue contract hash after an exact authorized D1C apply
5. wire RealPollingArchitectAdapter.observe_cycle, then run the verifier-owned acceptance mode
   (real acceptance accepts no injected adapter)
6. one small local proof, then one small live/private proof at max_workers=1
7. stop building pipeline infrastructure and make the game
```

## Strategic rule

```text
NO NEW PIPELINE FEATURE unless actual integration/game development proves it is needed.
```

## Working method for future agents

**Continue using this workflow unless a concrete reason requires deviation.** It is what produced
the reviewed D1C chain, the Software Architect commit, and the corrected Gauntlet.

```text
bounded implementation
→ deterministic/host validation
→ independent adversarial review
→ targeted correction
→ revalidation
→ guarded commit
→ integration
→ move on
```

Multi-track shape:

```text
ChatGPT / human architect
  defines boundaries + authority
        ↓
Claude/Codex implementation lane(s)
        ↓
independent reviewer
        ↓
ChatGPT synthesizes findings and decides the next operation
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
   `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`; keep local foundation
   commits unpushed until the integration/release point is chosen.
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
    UTF-8 prompts piped via stdin, never Bash `<` in PowerShell; Compose project `nosafecircle`; no
    global `safe.directory` workaround; exact-path staging and bounded destructive operations only.
12. **Keep architecture work subordinate to shipping the game.** Parallelize independent work to
    save calendar time. Once a subsystem is reviewed and sufficient, move on. Do not create another
    infrastructure phase for hypothetical future problems.

Do **not**: rebuild the design because a new idea appeared; ask Vincent to restate architecture
already captured here; rerun expensive accepted proof work without new evidence; or treat a
reviewer nit as a new architecture project.

### Preferred ChatGPT operator handoff style

Substantial work reaches Vincent as a **downloadable artifact plus one guarded command**, never as
a giant inline prompt that must be reassembled by hand. This is part of the safety model: it prevents
long-prompt corruption, pins exactly what was run, removes most PowerShell quoting/parser
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
`< prompt.md` syntax in PowerShell. Documentation example only, not a command to run:

```powershell
$ExpectedHash = "<sha256>";
$PromptFile = Get-ChildItem -LiteralPath "$env:USERPROFILE\Downloads" -Filter "<prompt>*.md" -File |
  Where-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -eq $ExpectedHash } |
  Sort-Object LastWriteTimeUtc -Descending |
  Select-Object -First 1;
if ($null -eq $PromptFile) { throw "Exact prompt not found." };
Set-Location "<exact checkout>";
$Prompt = Get-Content -LiteralPath $PromptFile.FullName -Raw -Encoding UTF8;
$Prompt | docker compose -p nosafecircle ...
```

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

## Known documentation drift

- `Docs/AI-Pipeline/CURRENT_STATE.md` on `main` was last updated 2026-08-26 and predates the
  architecture pivot. Treat it as historical until it is updated by an authorized task.
- ADR-045 and `Docs/AI-Pipeline/Software-Architect-Orchestrator/` exist only on the local
  architect branch, not on production `main`.
- `Docs/AI-Pipeline/Stage5-Decomposition-Design/` (merged at `514c8842...`) describes the
  pre-pivot Stage-5 plan. Slices 1-3 remain accurate; Slices 4-8 are superseded per the table
  above.
- Documentation PR #110 was a valid checkpoint but is draft/unmerged and stale as current
  context. Do not merge or update it. This branch supersedes it after human review.

## Outstanding documentation merge

- **`cathode26/NoSafeCircle#108` — "Docs: add agent prompt and runner construction rules" is still
  OPEN, draft, and unmerged.** Last independently observed 2026-09-01: branch
  `docs/agent-prompt-runner-rules`, head `24e81073e41303a93e9f4d8a374ff805e10b4854`, mergeable,
  exactly one file. That file is the companion rulebook
  `Docs/AI-Pipeline/AGENT_PROMPT_AND_RUNNER_CONSTRUCTION_RULES.md` — the "command no-no's"
  document — covering how to build agent prompts, PowerShell runners, native argv, machine-data
  verifiers, long-running provider jobs, write boundaries, and recovery paths, consolidating the
  concrete failures recorded in command-governance Issue #103. **Do not rebuild it, and do not
  assume it already landed on `main`.** It is not uncommitted local work: the branch is already
  committed and pushed. What remains is review/revalidation against *current* `main` and the
  merge. Its original "wait for the parallel Stage-5 design" hold is obsolete because that design
  work finished. Next action: after the current historical-context PR is handled, re-read the
  current PR head, current `main`, and the one-file diff; independently review it against
  `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`; then merge. Do not merge stale draft PR #110
  as a substitute.

Do not confuse the two command-documentation PRs:

```text
PR #100  MERGED      operator command reliability standards/template + smoke enforcement
PR #108  OPEN DRAFT  agent prompt and runner construction rules companion document
```

The base operator command standards and template are already on `main` via merged PR #100. PR
#108 is only the remaining companion prompt/runner-construction rulebook.

## Operational hazards already encountered

Do not rediscover these:

- Paste-ready operator commands target Windows PowerShell 5.1; Docker Compose uses `-p
  nosafecircle`; pipe prompts into containers rather than using Bash `<`.
- Host Git is the final changed-file authority for a Windows bind-mounted checkout. Container
  CRLF churn is noise — `git diff --ignore-cr-at-eol --stat` separates it from real changes.
- Stage exact paths. Never `git add .` / `git add -A` for bounded work.
- Automation commits use an `.invalid` identity.
- Never use global `safe.directory` as a generic ownership workaround.
- Parser-preflight generated `.ps1` runners and execute them through a bounded child
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`.
- `py_compile`/AST checks miss call-signature mismatches; preflight critical external calls with
  `inspect.signature(...).bind(...)`.
- Resumable workflows must preserve the original external output/package root.
- A failed runner does not mean its prior durable mutation failed; observe current state first.
- Windows PowerShell 5.1 can promote ordinary native stderr to a terminating error.
- `gh` JSON must be decoded as UTF-8.
- Opening Unity can dirty tracked `ProjectSettings` files.

## Canonical local layout

```text
shared/main checkout   C:\NSC\NSC\NoSafeCircle
task checkout root     C:\NSC\NSC
canonical task path    C:\NSC\NSC\<TASK-ID>
external output root   %USERPROFILE%\Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>
```

Historical paths under `C:\UnityProjects\...` may legitimately remain in old evidence and
transcripts; do not rewrite them.

## Read next

For the full rationale of the current architecture:

```text
2026-09-01-software-architect-integration.md
```

For how the Gauntlet earned that pivot, in order:

```text
2026-08-31-live-gauntlet-evidence-checkpoint.md
2026-08-31-pr9-exact-head-ci-recovered.md
2026-08-31-nsc601-live-lifecycle-accepted.md
```

For older Stage-4 history:

```text
2026-08-30-stage4-repository-binding.md
```

Raw transcripts are advisory archaeology only; see `raw/MANIFEST.md`.
