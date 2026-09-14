# Task Design GER

This is a small preparation tool for fleshing out an existing game task for an
agent crew. Give it an active `NSC-###` task ID and a new output directory
outside the repository. It reads the exact task contract, validates and searches
the current GDD index, adds art direction and references for visual tasks, and
writes a source-bound `GER_PACKET.md` plus
`SOURCE_IDENTITY.json`. An optional UTF-8 feedback file can carry Vincent's
observations from a gameplay-camera screenshot, such as "the room looks empty."

The command prepares the source-bound packet and an explicit agent handoff. It
does not claim to run Generate → Evaluate → Refine, does not call a provider,
and does not emit fabricated review or status artifacts. A future provider
runner must remain a separate entry point and preserve external round evidence.

Task Design GER supports two compact modes. Visual mode (the default for room
and art tasks) includes the relevant room references and a bounded upstream prop
catalog snapshot when present. Gameplay mode is selected automatically when
`--problem-file` is supplied, or explicitly with `--focus gameplay`; use
`--focus visual` when a task needs both a gameplay question and room dressing.
The UTF-8 problem is included in the packet and hashed in `SOURCE_IDENTITY.json`.
`--feedback-file` remains supported for earlier visual workflows.

The packet tells the independent agent to generate at least three gameplay
alternatives, compare projectile survival, melee escape, cover/LOS, distance
based target persistence/search, control readability, resource costs, route
tradeoffs and owner/task IDs, then perform bounded refinement and a fresh
re-audit. A current-GDD option must be separated from proposals requiring
design approval. Cover that blocks a projectile does not make an enemy forget
the wizard: Chapel pew/column occlusion is canon, while target loss remains
distance-based with last-known-position search. The preparer does not run these
agent/model passes or invent a final status.

When a GER agent is run, v1 requires one evaluator conversation independent of
the generator, followed by one bounded refinement and a fresh re-audit in a new evaluator
conversation. The evaluator's material findings are a union of findings, not a
vote; the latest author may not approve its own revision. This is a scaled-down
design loop derived from the project's multi-auditor reconciliation and D1B.2
review rules. The packet itself produces no graph delta or apply mode; the runbook's GER
owner turns the audited result into contract edits and any needed decomposition.

For comparison only, a GER agent may consult
[Diablo II Decoy](https://classic.battle.net/diablo2exp/skills/amazon-passive.shtml),
[Ultima Online Hiding](https://uo.com/wiki/ultima-online-wiki/skills/hiding/),
[Stealth](https://uo.com/wiki/ultima-online-wiki/skills/stealth/), or
[Provocation](https://uo.com/wiki/ultima-online-wiki/skills/bardic-skills/).
These sources are comparison patterns only; they do not establish NSC mechanics,
and neither they nor R01–R17 authorize copying rules, assets, or layouts.

For either mode, the first pass inventories gaps in the existing spec and asks
Vincent only for decisions that block a buildable contract; values left to
playtesting remain hypotheses. Visual briefs ask for named props, a focal
landmark, two supporting clusters, their relationship to approved routes and
doors, art catalog needs,
the Unity prefab/builder handoff, and a visual review shot. The evaluator checks
the proposal against the GDD, task ownership, art direction, asset availability,
and what a player can actually see. A refiner resolves findings before Vincent
reviews the brief. For tasks other than rooms, it asks for equivalent concrete
deliverables rather than forcing room composition onto unrelated work.

This is **review-only design preparation**. The script does not call a model,
run Unity, alter `Tasks/`, change the graph, or approve proposed details. The
GER owner performs the creative GER passes using the packet, then commits the
audited task-contract edit and applies any needed decomposition as described in
the runbook; only genuine game-design decisions and exact-plan authorizations go
to Vincent. The existing D1B.2
round-robin decomposition flow remains the structural review for actual child
task proposals. Assignment 6 and Assignment 7 GER loops remain implementation
and player-copy loops, respectively.

When approved design expands a dispatchable task beyond a safe crew-sized unit,
Vincent and Primary Sol identify and pause that exact task. Graph Sol stops work
on it, marks it unavailable, and continues other eligible work. Preserve any
checkout, candidate, and evidence; if no worker started, block new starts.
Approve the GDD or subordinate design and revised task scope first; then run
D1B.2 to review needed child contracts and their ownership, resources,
dependencies, and integration handoffs. An organizational parent such as
NSC-006 may need a reviewed new child rather than a forced split. GER may
recommend these boundaries but never edits the graph or makes children
available.

Typical agent instruction:

> Run Task Design GER for NSC-080, include my gameplay screenshot feedback,
> and return a refined review-only brief. Preserve the approved room geometry
> and do not update the task graph yet.

For a gameplay question, anchor the packet to an active task such as NSC-006
(Wizard Combat and Spells), supply `--problem-file` with the question, and use
`--focus gameplay`. Spectral Decoy is currently a GDD stretch goal, so a GER
proposal about its behavior must identify the GDD and graph decisions needed
before an agent crew implements it.

The CLI entry point is `task_content_ger.py`. Its required arguments are a task
ID and `--output-dir`; use a fresh
`Downloads/NoSafeCircleOutput/RoomContentGER/<RunId>-<TaskId>/` directory. Use
`--feedback-file` for an existing UTF-8 note or `--problem-file` for a gameplay
question. Re-prepare after any source
change; the packet records the exact task, GDD, index, art direction, and
reference hashes. A second run refuses to overwrite an earlier review packet.

For the manual mixed-provider review sequence, immutable evidence, verdict,
hold, decomposition, and explicit release procedure, see
[GER_AGENT_RUNBOOK.md](GER_AGENT_RUNBOOK.md).
