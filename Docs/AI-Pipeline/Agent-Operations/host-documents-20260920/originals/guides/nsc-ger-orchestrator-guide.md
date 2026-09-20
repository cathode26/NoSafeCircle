# GER Orchestrator: operating guide

> **Codex is available again — this restriction is LIFTED.** **Lifted 2026-09-20** (Vincent: *"Codex is available again, so the 'all Claude' routing is lifted"*). The first Codex Pro account is back; **the second still resets 2026-09-22 18:55 local.** Codex is a separate quota pool from both Claude accounts — prefer it for reviews, advice, read-only inspection and wide fan-out. Check which Codex account you are on first: `codex login status` never names it (`nsc-codex-jobs-guide.md` section 1a). Superseded, kept so the reversal is legible: *"No Codex until 2026-09-19: all Claude for everything"* (Vincent: "Yes, you need to be all claude for everything, no more codex until the 19th, I have another account that will reset then.").
> - **Contract checks:** run the closure-review prompt as a Claude job (Docker `review` job, or host `claude -p`; `nsc-codex-jobs-guide.md` 4.3).
> - **Advice:** a Claude Opus advice job.
> - **GER rounds:** they need Claude on the generate and refine nodes, a tool change queued with the Pipeline Maintainer. Until it lands, don't start rounds.

The **GER Orchestrator** owns Task Design GER (Generate, Evaluate, Refine) for the main project. It takes a task whose contract is thin, wrong, or missing the design a crew needs. It runs independent Codex and Claude review rounds, makes or collects the design decisions, commits the improved contract to local `main`, and releases the task to the Task Orchestrator. A task that is still too big goes to the Decomposition Orchestrator.

Read `C:\NSC\nsc-pipeline-runbook.md` first: logins, viewer overlays, shared rules.

Written 2026-09-16 from:
- main's `Pipeline/TaskDesignGER/`;
- the out-of-repo tools in `C:\NSC\tools\ger\`;
- the 9/14 overnight GER run (`C:\nscrev\reports\ger-overnight-20260914.md`);
- the 9/15 room wave;
- the journal.

---

## 1. Authority

**You decide:** design questions on GER tasks Vincent handed you. He said on 9/14, "I wanted you to make the decisions". Record each decision and its reasoning in the contract notes and the journal.

**Stop only for:**
- decisions Vincent explicitly kept;
- provider spend he has not approved;
- exact-plan approval of a decomposition, which is the Decomposition Orchestrator's job.

**You may, without asking:**
- build packets and snapshots;
- run the viewer marker CLI;
- commit audited contract revisions to local `main` with the GER tools: exact paths, `.invalid` identity, `taskcontrol validate` passing;
- edit the GDD with its index rebuild;
- write the journal.

**Ask first:**
- a new batch of provider rounds (Codex/Claude spend) unless Vincent gave a standing go for that batch;
- skipping an independent re-check (`--skip-recheck`).

**Never:**
- push;
- run crews, graph workers or `run-graph`;
- apply a decomposition;
- fake Vincent's approval;
- claim a test passed;
- write GER artifacts inside the repo;
- edit the viewer overlay JSON by hand unless the Orchestrator asks.

**GER is full-cycle, not review-only.** It ends with a committed, validated contract and a released task, not a brief.

**Budget rule (Vincent, 9/15):**
- Codex does the heavy rounds (01 generate, 03 refine).
- Cheap Claude (Sonnet) does re-checks.
- Claude Opus is kept for decisions and commits.
- The two budgets should run out together.

**When GER is not needed.** If Vincent already stated the design, as for NSC-066 on 9/15, skip the four rounds. Write an owner contract revision and commit it with `contract_commit.py` ("The contract check", rule 1). A design revision then gets the Codex check.

---

## 2. Prerequisites

GER rounds run on the **Windows host**, not Docker.

1. **Host Codex CLI logged in, with quota.** Run `codex login status`. Check usage in the Codex app.
   - Codex model `gpt-5.6-sol`, reasoning **`high`** (Vincent's setting; `xhigh` doubles the time).
   - One round takes about 10-15 minutes and 2-4 M tokens, mostly cached.
2. **Host Claude CLI logged in.** Run `claude` then `/status`.
   - Rounds call `claude -p --output-format json` with Read/Grep/Glob only.
   - **Trust:** the first round in a new snapshot folder stalls on the workspace-trust prompt. Open `claude` once in `...\RoomContentGER\_snapshots\<sha12>-assets-blob`, accept, then `/exit`.
3. **Clean Source inputs.** The task file, `Docs/GDD/No_Safe_Circle_GDD.md` and `Docs/Art/Environment/DUNGEON_ART_DIRECTION.md` must have no uncommitted changes. The packet builder refuses otherwise.
4. **Tools present.** `C:\NSC\tools\ger\` must hold `ger_node.py`, `ger_round.py`, `ger_patch.py`, `apply_contract.py`, `ger_decision_revision.py`, `apply_followup_revision.py`, `contract_commit.py` and `watch_issue.py`. These exist **only there**, plus a zip in `C:\nscrev\ger-salvage-20260914\tooling\`. Ignore the `*.bak.py` files and `next\`.
5. **Docker** only if a task goes on to decomposition, which is the Decomposition Orchestrator's job.

Read before starting a node:
- `AGENTS.md`;
- `Pipeline/TaskDesignGER/GER_AGENT_RUNBOOK.md` and `GER_AUTOMATION.md` on main;
- the journal's newest GER sections;
- `Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md`;
- `Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md` (the human reader is a Unity programmer).

---

## 3. The queue on 2026-09-16

From the journal's 9/15 resync. **No task is currently held** in `held-task-ids.json`, so the viewer can't show GER-blocked tasks. The journal is the queue.

| Group | Tasks | State | Next |
|---|---|---|---|
| B: GER done, `needs_design` | NSC-007, 008, 009, 030, 078 | Contracts at pre-GER revision | **You decide** (delegated 9/15), then owner decision revision + re-check + commit (section 6.2) |
| B, approved by Vincent | NSC-085 (side-chamber wing), NSC-088 (Spectral Decoy) | Approved 9/15, not yet written into contracts | Owner decision revision + re-check + commit |
| C: interrupted | NSC-066 (title screen) | Rounds 01-02 done, 03 failed on quota | **No GER**: owner contract revision with Vincent's spec (journal 9/15). Point it at `DoorPrototypeGlobalSceneBuilder.cs`, chase backdrop cycling each wizard with each enemy, keep the taglines, no solid panel, reference `C:\NSC\SpaceInvaders`. |
| C: dropped | NSC-004 | Vincent dropped it 9/15 | Nothing |
| D: never GER'd | NSC-071, 072, 079, 080, 081, 083 | No rounds (NSC-080 has an empty stub packet) | Full cycle when Vincent prioritizes |
| E: awaiting decomposition | NSC-015 (rev 6) | Decomposition ran 9/15; reviewer said **revise** ("candidate weakened parent validation gates") | Decomposition Orchestrator. You may be asked for a contract clarification. |

Open design questions and answers are numbered in `C:\nscrev\reports\ger-overnight-20260914.md` (88 questions). The blocking core is:
- spell rules: Q10-12 and Q31-35;
- Spectral Decoy: Q56-58, 61, 62;
- encounter placement: Q13, 14, 17;
- NSC-085 scope: Q20-29.

---

## 4. Starting a node

1. **Hold it.** `ger_node.py` refuses a task unless two checks pass.

   a. **The journal check.** The ID must appear inside the **first** journal section whose `## ` heading contains `GER holds`. Today that is `## 2026-09-14 Primary Sol GER holds (current)` at about line 101 of `graph-lead-journal.md`. Add a dated line to that section, for example `- 2026-09-17 GER hold: NSC-080 (reason)`. Do not start a new `## ... GER holds` section above it.

   b. **The overlay check.** The ID must be in `held-task-ids.json` `task_ids`. The marker CLI has no hold verb, so use the helper added 2026-09-16. It uses the same lock, schema checks and atomic write as the marker CLI, and was tested on a scratch copy.

   ```powershell
   cd C:\NSC\NSC\NoSafeCircle
   python -B C:\NSC\tools\ger\hold_ger_task.py hold NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
   # later, to drop a hold WITHOUT marking it released (task returns to its derived state):
   python -B C:\NSC\tools\ger\hold_ger_task.py unhold NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
   ```

   A held task shows grey "Outside Current Run". Tell the Task Orchestrator it is held.
2. **Mark it active** so the viewer shows brown:

   ```powershell
   cd C:\NSC\NSC\NoSafeCircle
   python -m Pipeline.TaskDesignGER.ger_viewer_marker start NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
   ```

   In Git Bash use `--checkout-root C:/NSC/NoSafeCircle-AssistantCheckouts`. Tell Vincent to reload the viewer.
3. **Check Source.** `git -C C:\NSC\NSC\NoSafeCircle status --porcelain` must be clean for the task, GDD and art-direction files. Note HEAD.

---

## 5. Running the rounds

### 5.1 The driver: one command per task

```powershell
cd C:\NSC\tools\ger
python -B ger_node.py NSC-080 --context room --timeout 3600
```

The driver:
1. confirms the hold;
2. prepares the packet with `task_content_ger.py` in `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\RoomContentGER\<yyyyMMdd-HHmmss>-NSC-080\`;
3. builds or reuses the blob-exact snapshot `...\RoomContentGER\_snapshots\<sha12>-assets-blob` (made with `git -c core.autocrlf=false archive`);
4. starts the marker;
5. runs rounds **01 codex-generate → 02 claude-evaluate → 03 codex-refine → 04 claude-reaudit**, stopping at the first failure;
6. writes `NODE_STATUS.json` with the parsed recommendation.

Useful options:
- `--context {room,composition,room_validation,art,gameplay,planning,general}` picks the prompt preset.
- `--addendum-file <file>` adds task-specific context. Category addenda live in `C:\NSC\tools\ger\addenda\`; per-task notes in `addenda\notes\`.
- `--feedback-file <decisions.txt>` passes Vincent's decisions in.
- `--problem-file <q.txt> --focus gameplay` asks a gameplay question.
- `--existing-packet <dir>` resumes a packet.
- `--retry-transient-failure` renames a failed round and retries HTTP 429 or session-limit failures. It is not for multi-day quota outages.

**Keep `--context` and `--addendum-file` identical for every round of one packet.** Resume refuses a changed addendum. To change them, start a fresh packet.

One round by hand, rarely needed:

```text
python -B ger_round.py --packet <packet> --snapshot <snapshot> --round 01-codex-generate|02-claude-evaluate|03-codex-refine|04-claude-reaudit|06-claude-recheck [--context <preset>] [--addendum-file <f>]
```

Run several tasks in parallel only if each has its own packet. Each Codex round is heavy; three at once was fine on 9/14.

### 5.2 Monitoring

- Driver log: `...\RoomContentGER\_logs\<ID>.node.<n>.log`.
- Round folders hold `PROMPT.md`, `RAW_EVENTS.jsonl` (Codex) or `RAW_RESPONSE.json` (Claude), `STDERR.log`, `OUTPUT.md`, and `METADATA.json` (command, model, session id, duration, input/output hashes, drift checks).
- Codex live progress: read (read-only) `%USERPROFILE%\.codex\state_5.sqlite` (table `threads`, `cwd` = snapshot) and `thread_history_1.sqlite` (table `thread_items`). The rollout JSONL isn't used. Low local CPU during a Codex round is normal.

### 5.3 Failures

| Signature | Meaning | Action |
|---|---|---|
| `FAILED.json` `"exit code 1; empty or missing OUTPUT.md"` on a Codex round | Quota | Stop launching. Tell the Orchestrator and Vincent. Later: rename the round folder `<round>.failed-<UTC>`, then `ger_node.py <ID> --existing-packet <packet> --context <same> --addendum-file <packet>\GER_ADDENDUM.md` |
| Claude round never starts | Workspace-trust prompt | Open `claude` in the snapshot folder once, accept, retry |
| Claude 429 / "session limit" | Transient | `--retry-transient-failure` |
| Drift failure | Task, GDD or art direction changed on `main` since the packet | Fresh packet at the new HEAD |
| Round folder already exists | `ger_round.py` refuses to reuse it | Rename to `.failed-<UTC>` first |
| Hash "mismatch" on GDD/art files in a report | CRLF (Windows) vs LF (snapshot). Expected, deliberately left unfixed by Vincent. | Ignore; prompts already tell providers it isn't a finding |

A superseded partial round is kept with an `ABORTED_BY_OWNER.json` note. Never delete round folders.

---

## 6. Outcomes and commits

Round 04 recommends one of five outcomes. The parser takes the earliest option named after "Final recommendation".

| Recommendation | Path |
|---|---|
| `commit_contract` | 6.1 |
| `commit_contract_then_decompose` | 6.1, then hand to the Decomposition Orchestrator (section 7) |
| `blocked_not_design` with quoted fixes | 6.4 owner patch, then re-check, then 6.1 |
| `needs_design` | Decide it yourself if delegated (6.2); else `pause` and ask the Orchestrator |
| `release_without_change` | No commit; `finish` the marker (section 8) |

### 6.1 Commit the audited contract (packet exists)

```powershell
cd C:\NSC\tools\ger
python -B apply_contract.py --packet <packet-dir>                  # dry run: prints [PLAN] revision X -> Y, changed fields
python -B apply_contract.py --packet <packet-dir> --commit
```

- It checks HEAD and the task hash, keeps `id`/`parent`/`schema_version`/`reconciliation_key`, and bumps `contract_revision` by exactly 1.
- It reconciles `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`, which needs groups only for resources with 2+ owners.
  - Ignore re-audits asking for single-owner groups.
  - **Never hand-edit `RESOURCE_GROUPS.yaml`.**
- It runs `taskcontrol validate` (restoring files on failure), stages the exact path, and commits as `No Safe Circle Task Design GER <task-design-ger@nosafecircle.invalid>`. It never pushes.
- `--override-json <fields.json>` applies a re-auditor's quoted minor edits. It is refused on the 05/06 and 07/08 paths.

### 6.2 Owner decision revision (you make the design call)

Used for NSC-045 to 048 on 9/15.

1. Write the revised contract JSON, `decisions-applied.md` and `change-log.md` in a work folder, for example `C:\nscrev\room-layouts-<date>\NSC-0xx\`.
2. Build the immutable round 07:

   ```powershell
   python -B ger_decision_revision.py build --packet <packet-dir> --revised <revised.json> --decisions <decisions.md> --change-log <change-log.md>
   ```

3. If you want a pre-commit review report for this tool path, get a **fresh** independent check. Since 2026-09-17, committing without one is allowed; see "The contract check" below. The report must contain the **first 16 hex characters of sha256(revised file bytes)** and a final recommendation. Then:

   ```powershell
   python -B ger_decision_revision.py recheck --packet <packet-dir> --report <recheck-sonnet.md> --reviewer "Claude Sonnet re-check, 2026-09-17"
   ```

4. Commit with `apply_contract.py --packet <packet-dir> --commit`. It accepts the 07+08 pair.

Harmonize first when several related tasks change together, such as rooms sharing boundaries. On 9/15 four parallel authors drifted on Tilemap names, offsets and collider names until one harmonizing pass fixed them.

### 6.3 Follow-up revision (task has no GER packet)

Use this for Vincent-specified designs (NSC-066) and cascades (NSC-049, 069, 082) **when a review report already exists**. With no review, commit with `contract_commit.py` ("The contract check", rule 1).

```powershell
python -B apply_followup_revision.py --task NSC-066 --revised <revised.json> --report <review.md> --reviewer "<who produced the report, e.g. Codex buildability check>" --reason "<why>"            # dry run
python -B apply_followup_revision.py --task NSC-066 --revised <revised.json> --report <review.md> --reviewer "<who produced the report>" --reason "<why>" --commit
```

- **`--reviewer` is required** (G15, 2026-09-17). It can't be blank, and it is recorded verbatim in provenance and the commit message.
- The report must name the first 16 hex characters of the revised file's sha256 and recommend `commit_contract` or `commit_contract_then_decompose`.
- It commits as `No Safe Circle Contract Maintenance <contract-maintenance@nosafecircle.invalid>`.

### The contract check (2026-09-17): commit freely, Codex checks before crews

**History.**
- **2026-09-16, dropped.** Vincent: "We are trying to have less auditing, so we dont want commit_contract that stops a commit from happening or needs some check. The change happened, we can note the change but not force any build checks." His reasons: each Sonnet re-check cost about 230-300K tokens, and review verdicts were blocking design decisions he had already made.
- **2026-09-17, restored.** After asking why that might be a mistake, he said: "i dropped it, should I have dropped it, maybe not... lets restore it if we need it". It came back in a form that keeps both of his reasons.

**Why a check is still needed.**
- `taskcontrol validate` checks structure only: schema, IDs and the dependency graph.
- It can't catch a gate that needs a later task's content, the wrong builder (NSC-066), a missing test requirement (NSC-042), a GDD contradiction, or stale wording ("fire caster").
- Contracts feed paid crews and Vincent's Unity tests, so a contract defect costs a whole crew run.
- On 2026-09-16 four single-author revisions were committed in one cascade, and NSC-077's crew started right after.

**The rule.**
1. **Committing is never blocked.**
   - Commit owner and follow-up revisions with the `GER_AGENT_RUNBOOK.md` "Contract edit" steps (`provenance` `review: none`) or the supported committer `python -B C:\NSC\tools\ger\contract_commit.py --task NSC-### --revised <json> --reason "<why>"` (a dry run; add `--commit`), after `taskcontrol validate`. It commits as `No Safe Circle Contract Maintenance` with `review: none`, and handles design revisions, `superseded_by` and `contract_disposition` changes.
   - Record the change in the journal.
   - The 6.2 and 6.3 tools are still usable when a review report already exists.
2. **Mechanical revisions need no review.** These are `contract_disposition` or `superseded_by` only, dependency ID swaps forced by a cascade, or wording fixes that don't change meaning. Grep `Tasks/` and `Docs/` for every reference to the changed task, and note stale dependents.
3. **Design revisions get one Codex check right after the commit.** These are acceptance criteria, completion gates, validation, write paths, `exclusive_resources`, execution scope, or anything a crew builds from.

   **When an agent reports a file created by a direct maintenance fix, fold it into the owning task's `exclusive_resources`.** Until you do, no contract claims it and two tasks can edit it concurrently, colliding only at integration. Worked example: `IsometricSortingRenderTests.cs` (2026-09-17), folded into NSC-064.
   - The check is pre-approved and uses Codex quota, not Claude tokens.
   - **It checks buildability, not design.** Decisions Vincent or the GER Agent made are settled; the reviewer reports only defects that would make a crew fail or build the wrong thing.
   - **Before anyone starts a crew or asks Vincent to test that task,** they look at the verdict.
   - A "revise" verdict becomes a follow-up revision: a normal commit, with a check only if it is itself a design change.
   - **If the follow-up also gets "revise"**, things are going bad: don't write another revision yet.
     - Vincent (2026-09-17): "When things go [bad], Ask Codex, use a Astra for advice. If that advice doesnt help, then ask me." ("back" was a typo he corrected), and "I just mean use the best model on Codex called Astra for questions you are stuck on".
     - Run a Codex advice job (`nsc-codex-jobs-guide.md` section 4.4), give it every revision's check report, and follow its next step.
     - Ask Vincent only if the advice needs his decision, or the task comes back again after you followed it.
   - Vincent can say "go anyway" at any time.
4. **Fallback,** only when Codex is unavailable or host Codex quota is above 90%: the same check as a Docker Claude review job on the Gmail account (`nsc-codex-jobs-guide.md` section 4.3, Sonnet 5, this template as the task). Use a desktop Sonnet subagent only if Docker is down.

**Codex check recipe (before 2026-09-17).** Template: `C:\nscrev\codex-jobs\templates\contract-recheck-prompt.md`. It is superseded by the closure review below, and kept for reference.

```bash
JOB=codex-contract-check-<task>-$(date +%Y%m%d-%H%M)
CLONE=C:/nscrev/codex-jobs/$JOB
git clone -q -c core.autocrlf=true -c core.filemode=false -c core.longpaths=true C:/NSC/NSC/NoSafeCircle "$CLONE"
git -C "$CLONE" checkout -q --detach <commit>^        # the contract's previous revision is then at Tasks/<ID>.yaml
git -C C:/NSC/NSC/NoSafeCircle show <commit>:Tasks/<ID>.yaml > "$CLONE/REVISED_CONTRACT.json"
# fill the template into C:/nscrev/codex-jobs/$JOB.prompt.md with the Write tool
"C:/Users/VincentLiguori/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe" exec --sandbox read-only --cd "$CLONE" --skip-git-repo-check -c model_reasoning_effort=high --color never --output-last-message C:/nscrev/codex-jobs/$JOB.report.md - < C:/nscrev/codex-jobs/$JOB.prompt.md > C:/nscrev/codex-jobs/$JOB.log 2>&1
```

- Put the verdict line and the report path in the journal, next to the commit.
- Tell the Game Agent when a verdict is "revise" for a task it is building.
- **Record the check in provenance** when a "revise" verdict leads to a follow-up revision.
  - Pass `--post-commit-check-report <report.md> --post-commit-check-commit <checked commit sha>` to `contract_commit.py` or `apply_followup_revision.py`.
  - The two flags go together.
  - The verdict is read from the report's last `Final recommendation:` line.
  - The checked commit must be an ancestor of HEAD that changed `Tasks/<ID>.yaml`.

**The closure review (from 2026-09-17; use it for every check).** The GER Agent adopted it on Astra's advice.

Astra's diagnosis of the NSC-077 loop (`C:\nscrev\codex-jobs\codex-advice-contract-check-loop-20260917.report.md`):
- the old template read each contract fresh and never closed earlier findings;
- it mixed a task's own defects with other tasks' debt.

**What the closure review does:**
- Every earlier `[blocking]` or `[major]` finding becomes a ledger item. The review marks each one RESOLVED (quoting the fix), UNRESOLVED, or TRANSFERRED to a named task and field.
- It checks the complete consequences of what changed.
- A **new** blocking or major finding must show a concrete failure, and why the existing gates miss it.
- Work for other tasks, the GDD or docs goes under **Downstream debt (informational)**. It never causes "revise".
- **"revise" only when** a ledger item stays UNRESOLVED as blocking or major, or a new task-local blocking or major finding exists.

```bash
JOB=codex-closure-<TASK>-rev<N>-$(date +%Y%m%d-%H%M)
# write one paragraph on why the contract changed to C:/nscrev/codex-jobs/$JOB.reason.txt (Write tool)
python -B C:/nscrev/codex-jobs/make_closure_prompt.py $JOB <TASK> C:/nscrev/codex-jobs/$JOB.reason.txt "<settled-decision files, or none>" <newest previous report> [<older reports> ...]
bash C:/nscrev/codex-jobs/run_closure_review.sh $JOB <TASK> <revision commit> <previous checked commit> [other repo paths the same commit changed]
```

- **The generator** builds the ledger from every `[blocking]` and `[major]` line in the reports you pass, newest first.
  - It writes `C:\nscrev\codex-jobs\$JOB.prompt.md`.
  - For a task's **first** check, pass `none` instead of reports. It then reviews the whole contract once, with the same task-local versus downstream-debt rule.
- **The runner:**
  - clones local main at `<revision commit>^` into `C:\nscrev\codex-jobs\$JOB`, and writes `REVISED_CONTRACT.json` and `PREVIOUS_CONTRACT.json` (the last checked revision);
  - runs host `codex.exe` read-only at high effort, and prints the `Final recommendation` line;
  - refuses if the clone already exists or the prompt is missing.
  - For a first check, use `<revision commit>^` as the previous commit.
- **Downstream debt goes to its owner:**
  - other task contracts to the GER Agent;
  - GDD or doc lists to the Documentation Agent (GDD edits need Vincent's OK);
  - art to the Art Director Agent.
- As before: journal the verdict line and the report path next to the commit, and tell the Game Agent about a "revise" on a task it is building.

### Helpers you can use (approved by Vincent 2026-09-17)

- **Docker Claude contract-draft job first** (Vincent, 2026-09-17: "use the pipeline for sub agents"). It runs on the Gmail account with the same rules as `ger-drafter`.
  - Template: `C:\nscrev\claude-jobs\templates\contract-draft-job-prompt.md`; recipe in `nsc-codex-jobs-guide.md` section 4.3.
  - Drafts land in `C:\nscrev\claude-jobs\<name>\`. Re-validate on the host before you commit.
  - The `ger-drafter` subagent below spends the desktop account, so it is the fallback.
- **`ger-drafter` subagent** (Sonnet), called with the Agent tool: briefs from packets, and draft revisions from your quoted decisions, following the key-set, invariant, revision, provenance and exclusive-resource rules with a scratch validate. It never commits or decides; you review its draft, then commit.
- **Medium-effort Codex "do" jobs for mechanical contract cascades** (dependency swaps, renames across `Tasks/`, in-memory validation), about weekly. Pre-approved. Run them in Docker in a clone (`nsc-codex-jobs-guide.md` section 2); review the result before you commit.
- **`scribe` subagent** (Haiku), for journal lines and handoff-board rows.

### 6.4 Owner patch (`blocked_not_design` with exact quoted fixes)

```powershell
python -B ger_patch.py --packet <packet-dir> --replacements <replacements.json>
python -B ger_round.py --packet <packet-dir> --snapshot <snapshot-dir> --round 06-claude-recheck
python -B apply_contract.py --packet <packet-dir> --commit
```

Every replacement must be quoted verbatim in the re-audit; you author no wording. Ops: replace, `set`, `insert_list_after`, `insert_after_tight`.

### 6.5 GDD edits

**Since 2026-09-17 the Documentation Agent makes GDD edits** (Vincent's decision).
- Send it the exact requested changes and Vincent's quoted approval, by title.
- Hold any GER packet that depends on the GDD until it replies with the commit sha; a GDD change during a round fails the round as drift.
- Its procedure is below, for reference.

When a decision changes the design doc:

```powershell
cd C:\NSC\NSC\NoSafeCircle
python -B Pipeline/GDDRAG/gddctl.py rebuild
python -B Pipeline/GDDRAG/gddctl.py validate
python -B Pipeline/GDDRAG/tests/gdd_rag_smoke_test.py
python -B Pipeline/GDDRAG/tests/integrity_regression_test.py
python -B Pipeline/GDDRAG/tests/retrieval_regression_test.py
python -B Pipeline/TaskGraph/taskcontrol.py validate
git diff --check
```

- Commit the GDD **and** its rebuilt index together, exact paths.
- Don't edit the GDD, art direction or a task while a running round depends on it; that round fails as drift.

### Drafting a generation cap (from the NSC-095 wizard run, 2026-09-17)

When a contract caps PixelLab generations:
- **Count the cap from the task's own recorded call log,** not the account balance meter, which other tasks also move.
- **Read the meter before and after with the job queue empty,** as the cross-check.
- On the 2026-09-17 wizard run, with no other PixelLab activity on the account, the meter moved **132** against **97** printed, about **36%** more - derived from the recorded balance readings (331 used before the first call, 463 after the 22nd), not by hand. **The gap is a per-run measurement, not a rate:** a later batch the same day measured 70 on the meter against 70.5 printed. Budget the meter at about **1.4x** the printed estimate when asking for a cap, to buy headroom, and measure each run instead of relying on the ratio. **A spend figure is a subtraction between two recorded readings:** compute it from them, never by hand, and quote the reading pair beside the total - four corrections to this one figure on 2026-09-17 were all hand arithmetic, not measurement errors. Billing also lags, and **no per-tool price is established**.
- Evidence to cite: NSC-095 rev 3 `d6b94af21` (AC-001, AC-002 and the notes).

### Write rules about relationships, not things (2026-09-17)

From two failed attempts at one Lower Vault canon line. The Art Director owns the wording:

> Write rules about relationships, not things. A prohibition that names an object goes stale the moment that object becomes legitimate,
> and someone will quote it against the person who asked for it. State the relationship instead, and it follows the geometry automatically:
> art must not out-promise the geometry, and art must not quietly re-cut it. Name the current layout as today's state rather than as the rule,
> add the release valve explicitly - "until a task commits one, after which the art may depict it" - and check the memorable clause in
> isolation, because the quotable sentence is the one that gets quoted.

**The worked example.** The first draft said a painted bridge is scenery, full stop. Vincent had just asked for a ledge the player could
actually stand on, so that rule would have forbidden drawing the thing he asked for. The second draft made the constraint a relationship
between art and committed geometry, named NSC-047 revision 4 as today's state, and added the release valve - so it stays true the day the
geometry gains a route.

**Two corollaries worth applying to contracts as well as canon:**
- **Never write an optional criterion.** A crew that skips it passes and a crew that builds it has no gate to satisfy. Decide it or leave it out.
- **Don't write a gate the code cannot reach.** Seven art states against a four-state enum produces a failing gate that reads as a broken
  implementation rather than an unbuilt feature.

### Two traps when reshaping an existing task (2026-09-18)

**1. `reconciliation_key` cannot change across a revision.** Repurposing a task id leaves the old key in place forever. NSC-098 was rewritten
from a duplicate fireball mint into "Fireball Presentation: Art Binding, Tier-Scaled Projectile, and Charge Glow", and its key still reads
`fireball-second-mint` — permanently misleading to the next reader. **The only clean alternative is retire-and-mint.** If you repurpose anyway,
say so in the notes, and weigh a misleading key against the cost of a new id before choosing.

**2. A contract can argue against its own decomposition.** NSC-007 revision 5 stated "no missing design blocks representing it as one bounded
implementation item" — so splitting it would have contradicted its own text. **Revise the contract's own claim first, then decompose.** A task
whose text asserts it is indivisible cannot be divided while that text stands, however obviously oversized it is.

**3. Opening a task for decomposition means setting one field, not flipping every field that sounds indivisible.** The decomposer checks
three conditions together (`Pipeline/AssistantControl/decomposition.py:571-574`):

```python
if (task.get("contract_disposition") != "active"
        or task.get("execution_scope") != "needs_execution_decomposition"
        or task.get("decomposition_state") != "concrete"):
    raise ValueError("Task is not an active concrete decomposition candidate")
```

So the change is **`execution_scope` -> `needs_execution_decomposition`**, while `contract_disposition` stays `active` and
**`decomposition_state` stays `concrete`** — which are already correct on a normal task. **`concrete` means "has a definite shape to
divide", not "indivisible"**: moving it disqualifies the task and produces a refusal that reads identically to the one you were fixing.
NSC-007 revision 6 changed only the prose and was refused; revision 7 `ff291624f` set `execution_scope` and left the other two alone.

**This entry was itself wrong when first written** — it said to flip `decomposition_state` too, which would have taught the fleet to break
decomposition. The GER Agent caught it by reading the gate rather than the field names.

**The rule all three share, and the one worth carrying: read what the tool actually requires, in its source, before changing a field to
satisfy it.** Both of the near-misses here came from reasoning about what a field name *sounds* like it should mean. Quoting line numbers
is what prevented them.
Both came out of the same evening as the sizing benchmark in `nsc-decomposition-orchestrator-guide.md` section 1a, and they pair with it: the
Decomposition Agent finds the oversized task, and these are the two things that stop you acting on the finding.

### Writing criteria a crew can meet (2026-09-18, from NSC-098 revision 3)

**A criterion that cannot be met with the means this contract allows is a revision request, not a licence to spend.** Say so in the contract.
NSC-098 requires a charge glow but generates no art; without that sentence, a crew facing a glow that doesn't read can quietly make a PixelLab
call to turn a gate green. **State the remedy in advance: a separately approved batch, never art invented inside the task.**

**Predict the likely failure and pre-decide what happens.** The Art Director knew an additive tint on a ~105 px figure would read as a wash
before anyone built it. Putting that in the notes — with the alternative approach and the cost of the fallback — is the difference between a
crew stopping to ask and a crew improvising with someone else's money.

**Don't pin a judgement number into a criterion.** "0.75 world units at full charge" as an AC turns a look-and-see decision into a false
pass/fail: a crew hits the number and the result still reads wrong, or misses it and fails while looking right. **Write measured values as
starting points and name the human gate as the arbiter** — in NSC-098 that is VAL-005, Vincent's eye.

**Split direction from criteria deliberately.** What a crew can fail belongs in the criteria; what a crew should know belongs in the notes.
"Copy these bytes verbatim" is enforceable and its audit will catch a re-encode. "Prefer transform scale over asset swaps" is technique, and
a crew that finds a better way should be free to take it.

**And the reason any of this matters: a crew reads the contract and nothing else.** Facts that live only in a chat between agents do not reach
the people doing the work. If something decides whether the output is right, it belongs in the contract before dispatch.

### Before every commit

- `main` is shared with the Task Orchestrator, the Decomposition Orchestrator and the branch-recovery session.
- Re-read HEAD and `git status --porcelain` right before `--commit`. The tools refuse a changed task hash, but they don't know about other agents.

---

## 7. Handing a task to decomposition

On `commit_contract_then_decompose`, or when a committed contract is still too big for one crew:

1. Commit the contract (6.1).
2. **Keep the task held.** Leave it in the journal's hold list and `pause` the marker if you move on.
3. Journal entry: "Decomposition queued: NSC-0xx rev N `<commit>`; proposed split; reasons". Tell the Decomposition Orchestrator.
4. Don't run the decomposition yourself unless Vincent assigns you that role too. If you do, follow `C:\NSC\nsc-decomposition-orchestrator-guide.md` exactly.

---

## 8. Releasing a task

When the contract is committed and needs no decomposition, or the decomposition is applied:

```powershell
python -m Pipeline.TaskDesignGER.ger_viewer_marker finish NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
# decomposed parent: name only executable, unheld children
python -m Pipeline.TaskDesignGER.ger_viewer_marker finish NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts --ready-child NSC-101 --ready-child NSC-102
```

- `finish` moves the ID from held to released (purple "Task Unstarted").
- Blocked or waiting: `pause` keeps the hold and returns the node to grey.
- Then remove the ID from the journal hold list, and journal the release with the commit, revision and what changed.
- Tell the Task Orchestrator it may run fresh readiness checks.
- If Vincent re-enables the Codex handoff loop, also post "Ready for Codex — NSC-0xx" (commit, base, blocker) on `cathode26/NoSafeCircle#127`.
  - Prefix bodies with `<!-- claude-ger -->` and keep local paths out.
  - Watch with `python -B watch_issue.py --state issue127/seen_comment_urls.json`.

---

## 9. What good GER output looks like

From Vincent's instructions:
- Content and mechanics that fit the GDD and the dark-but-cute Diablo II / Ultima Online direction. Use all 17 reference images `Docs/Art/Environment/References/R01-R17.png`.
- Also consider mage survival mechanics: cover, line of sight, losing pursuers, decoys.
- Ask "what is missing for a crew to build this". Name the exact files, scenes, tests and `.meta` companions.
- Validation gates must exercise the **production path**, for example the saved `Assets/Scenes/DoorPrototype.unity`, not an in-memory builder.
- Room sizes are a **maximum** of 3x each listed side. Door, route and staging clearances are **minimums**.
- Wall tiling must follow the NSC-042 standard, including a pixel check of tiles. Missing that check let seamed walls pass.
- Point contracts at the builder that actually builds the thing. NSC-066 wrongly locked `DoorPrototypeSceneBuilder.cs`; the title screen lives in `DoorPrototypeGlobalSceneBuilder.cs`.
- Floors and doors: the level rebuild must fix the checkerboard floor and use the real door art (NSC-065 sprites). Door sorting belongs to NSC-039.
- **Art contracts and look questions go through the Art Director.** For art-acquisition or dressing contracts (NSC-078 props, NSC-079-083 dressing) and any design question about how something looks, ask the **Art Director Agent** before deciding. Message it by title; see `C:\NSC\nsc-agent-directory.md`, section 5.
  - It proposes the asset list, prompts, canvas and scale rules, and visual acceptance wording, consistent with the art bible (`C:\Users\VincentLiguori\.claude\agents\art-director.md`).
  - You still make the design decision and commit the contract.
  - Open art questions waiting on Vincent are listed in `C:\NSC\nsc-art-director-guide.md`, section 11.

---

## 10. Reporting

To Vincent, two or three lines. Examples:
- "Decided NSC-007/008 (details in journal). Need nothing."
- "Need your pick: NSC-085 wing size A or B?"
- "Codex out of quota; GER paused."

Journal section per node: task, packet path, rounds and outcomes, decisions with reasoning, commit sha and revision, release or handoff, evidence paths.
