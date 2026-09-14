# Task Content GER

This is a small preparation tool for fleshing out an existing game task for an
agent crew. Give it an active `NSC-###` task ID and a new output directory
outside the repository. It reads the exact task contract, validates and searches
the current GDD index, adds the approved dungeon art direction and selected
user-supplied visual references, and writes a source-bound `GER_PACKET.md` plus
`SOURCE_IDENTITY.json`. An optional UTF-8 feedback file can carry Vincent's
observations from a gameplay-camera screenshot, such as "the room looks empty."

The command prepares the source-bound packet and an explicit agent handoff. It
does not claim to run Generate → Evaluate → Refine, does not call a provider,
and does not emit fabricated review or status artifacts. A future provider
runner must remain a separate entry point and preserve external round evidence.

When a GER agent is run, v1 requires one evaluator conversation independent of
the generator, followed by one bounded refinement and a fresh re-audit by that
evaluator. The evaluator's material findings are a union of findings, not a
vote; the latest author may not approve its own revision. This is a scaled-down
content loop derived from the project's multi-auditor reconciliation and D1B.2
review rules. It remains review-only and produces no graph delta or apply mode.

The generated brief asks for named props, a focal landmark, two supporting
clusters, their relationship to approved routes and doors, art catalog needs,
the Unity prefab/builder handoff, and a visual review shot. The evaluator checks
the proposal against the GDD, task ownership, art direction, asset availability,
and what a player can actually see. A refiner resolves findings before Vincent
reviews the brief. For tasks other than rooms, it asks for equivalent concrete
deliverables rather than forcing room composition onto unrelated work.

This is **review-only design preparation**. The script does not call a model,
run Unity, alter `Tasks/`, change the graph, or approve proposed details. An
agent performs the creative GER passes using the packet; a separate graph edit
can follow only after Vincent accepts the proposed content. The existing D1B.2
round-robin decomposition flow remains the structural review for actual child
task proposals. Assignment 6 and Assignment 7 GER loops remain implementation
and player-copy loops, respectively.

Typical agent instruction:

> Run Task Content GER for NSC-080, include my gameplay screenshot feedback,
> and return a refined review-only brief. Preserve the approved room geometry
> and do not update the task graph yet.

The CLI entry point is `task_content_ger.py`. Its required arguments are a task
ID and `--output-dir`; use a fresh
`Downloads/NoSafeCircleOutput/RoomContentGER/<RunId>-<TaskId>/` directory. Use
`--feedback-file` for an existing UTF-8 note. Re-prepare after any source
change; the packet records the exact task, GDD, index, art direction, and
reference hashes. A second run refuses to overwrite an earlier review packet.
