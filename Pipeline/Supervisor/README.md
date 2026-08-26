# Supervisor MVP — GitHub Ticket Orchestration

This directory contains the smallest operational slice needed to coordinate several human-directed ChatGPT task orchestrators against No Safe Circle.

It does **not** implement autonomous dispatch, dependency readiness, leases, race-free distributed locking, automatic merge, or GitHub Projects automation.

## Authority split

- `Tasks/*.yaml` and committed TaskGraph evidence remain authoritative for task definition and current conformance.
- GitHub Issues provide shared operational visibility between concurrent human-directed orchestrators.
- A GitHub Issue being closed does **not** prove TaskGraph conformance.

## Canonical task checkout path

All task checkouts must follow:

```text
Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md
```

The shared operator checkout is:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

A claimed task checkout is named by the exact hyphenated TaskGraph ID directly under the crew root:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Do not use `NoSafeCircle-NSC044` as the normal checkout directory name.

## MVP issue state

For an Issue whose title begins with an exact `NSC-###` ID:

- **open + unassigned**: available/released;
- **open + assigned**: claimed / being worked;
- **closed**: orchestration is finished.

The MVP intentionally does not solve the simultaneous-claim race. The human operator may correct a duplicate claim manually.

## Local helper

`task_checkout.py` deliberately does not require a GitHub token or GitHub CLI. ChatGPT uses the connected GitHub integration to create/search/assign/comment/close Issues. The local helper owns deterministic local-machine work.

Use the canonical checkout path explicitly:

```text
python Pipeline/Supervisor/task_checkout.py show NSC-044
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

### Checkout behavior

`checkout`:

1. requires a clean source repository;
2. fetches current `origin/main`;
3. reads the selected task contract from committed `origin/main`;
4. requires `active` + `implementation` + `single_agent` + `concrete`;
5. clones from the GitHub remote, never the local checkout;
6. verifies the clone landed on the exact captured `origin/main` commit;
7. creates a descriptive `nsc-###-<title>` branch;
8. runs `taskcontrol validate`;
9. requires a clean new checkout;
10. writes `claim.json`, `issue-body.md`, and `claim-comment.md` beneath:

```text
%USERPROFILE%\Downloads\NoSafeCircleOutput\TicketOrchestration\<TASK-ID>\<timestamp>\
```

The generated `claim-comment.md` intentionally contains a required planned-approach section. The ChatGPT orchestrator should fill that section and post it to the claimed GitHub Issue before implementation begins.

### Closeout behavior

`draft-closeout` writes a Markdown report outside the repository. It pre-populates task identity, branch/HEAD, comparison base, commits, changed files, and diff stat, but requires the orchestrator to explain:

- outcome;
- what changed;
- how the task was accomplished;
- implementation/design choices it made;
- missing or underspecified information encountered;
- additions beyond the original task and why;
- validation performed and results;
- remaining follow-ups/risks;
- final TaskGraph state observed after delivery/merge.

Every required section must be filled before the report is posted to the GitHub Issue and the Issue is closed.

## Required GitHub behavior

The ChatGPT orchestrator, using the connected GitHub integration, owns the operational Issue actions:

1. search for an exact Issue matching the task ID;
2. if an open Issue is already assigned, do not select that task;
3. create the Issue if none exists, using task details from the committed TaskGraph;
4. assign it to the human GitHub account to mark it claimed;
5. post the filled Claim / Planned Approach comment;
6. perform the normal task delivery workflow;
7. post the filled Closeout Report;
8. close the Issue only after the orchestration is truly finished;
9. if work is abandoned, unassign the still-open Issue and add a release reason instead of closing it as completed.

See `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md` for the multi-window operator protocol.
