# Handoff: audit the graph's evidence debt

From: GER Agent. To: Viewer Agent. Date: 2026-09-18 (Vincent asked for this directly: "Can we do an audit, the viewer agent was asked to be an auditor and fix everything").

## The problem, in one paragraph

Work is merged on `main` and the game plays, but the task graph does not know it. `taskcontrol states` across 95 tasks reports **16 conformant, 51 not_delivered, 24 aggregate, 2 needs_testing, 1 needs_replan, 1 superseded**. A large but unknown share of those 51 is **evidence debt**: the implementation is on main and the delivery record was never written. That debt, not design or art, is what is actually blocking work. Three times on 2026-09-17 it stopped something Vincent asked for:

- he asked for a room task, and all five rooms were blocked behind NSC-069, whose code was already on main with no record;
- the stretched wizard he found himself cannot be fixed by its own task, because NSC-075's five dependencies (NSC-062, NSC-068, NSC-070, NSC-073, NSC-074) are all `not_delivered` although the wizard work is merged and visibly in the game;
- two spells are parked behind NSC-013 in the same way.

## What the audit must produce

One report that splits the 51 `not_delivered` tasks into three buckets, with evidence per task:

1. **Evidence debt** - every implementation file the contract claims exists at `HEAD`, and there is no delivery record (or a record that is `prepared` rather than approved). These are recoverable with an evidence pass, no new code.
2. **Partially built** - some claimed files exist and some do not. Name which are missing; these need work, not just a record.
3. **Not built** - none of the claimed implementation files exist. Nothing to recover.

For each task also report:
- its `depends_on`, and how many of those dependencies are themselves conformant, so a **ready queue** falls out: evidence-debt tasks whose dependencies are already conformant can be recovered immediately;
- whether an assistant-control record exists and its `status` and `approval` fields;
- whether the contract has a validation policy entry (missing entries park candidates - NSC-007 had none at all today).

Rank the evidence-debt bucket by how many other tasks each one unblocks. That ranking is the working queue.

## Where to look

- Contracts: `C:\NSC\NSC\NoSafeCircle\Tasks\NSC-###.yaml` (JSON). `exclusive_resources` lists claims as `repo-file:<path>`, `unity-scene:<path>` and `logical:<name>`; only the first two are file existence checks, and `logical:` claims are not files.
- Derived state: `python -B Pipeline/TaskGraph/taskcontrol.py states` from the repo root for all tasks, `... state NSC-###` for one, which also prints the findings, for example `no_committed_evidence`.
- Records: `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\NSC-###.json`, plus `worker-runs\NSC-###\` and `.scope-state\NSC-###.scope.json`.
- Validation policy: `Pipeline\TaskReviewAgent\authoritative_validation_policy.json`.
- Read repository files with `git show main:<path>` from a clone rather than opening the canonical checkout.

## Rules

- **Read-only.** Do not write delivery records, do not edit contracts, do not merge, do not run Unity. The audit produces a list; the Game Agent produces evidence and the GER Agent owns contracts.
- Prove file existence against `HEAD` with git, not against a working tree that may have churn.
- Where a contract claims a file that no task has built yet, say so plainly rather than inferring intent.
- If a task's state looks wrong for a reason the buckets do not cover, give it its own line rather than forcing a bucket.

## One caution, learned expensively today

Two agents, including me, concluded a test fixture "did not exist" by searching the file tree for a file named after it. It is a **partial class** declared in two differently named files. That cost three contract revisions. **To prove a symbol absent, grep file contents for its declaration, never the tree for a filename.** The same trap applies to any claim in this audit of the form "X is not there".

## Deliverable

`C:\nscrev\reports\viewer-agent\evidence-debt-audit-20260918.md`, with the three buckets, the ready queue, and a one-line summary of counts. Tell me when it lands and I will take the contract-side items; the Game Agent takes the evidence passes.
