# Demo scripts: running NSC-042, and talking about the tool while it runs

Two spoken scripts. Script 1 is the walkthrough you narrate while you press the buttons.
Script 2 is the filler talk for the minutes the run needs; it is cut into segments so you
can stop whenever the viewer changes and go back to Script 1.

Timing you can expect: pressing Start to a visible task is about two to three minutes
(login check, preflight, container images, scheduler). The architect decision and worker
launch add a minute. The crew itself, implementer plus validator, is usually five to ten
minutes for a task this size. So plan on eight to fifteen minutes of talk in total.

---

## Script 1: "Doing 42"

### Before you press anything

"This is the project checkout, the actual repo, not a copy. The viewer on the left is
watching it. It says LOCAL REHEARSAL and 'no active run', and the first button says
Start run, because nothing is running yet. That's the whole control surface: start, stop,
and a reset that only unlocks after a stop."

"The task I'm going to run is NSC-042: Seamless Scalable Wall Tiling for Long Isometric
Walls. It's a real contract from the game's task graph. It has four acceptance criteria and
three completion gates, and one of those gates is a human runtime observation, which is
exactly why this task is special in the pipeline: it can never be accepted by a machine."

### Press Start run

"I press Start. The page says Starting. Behind that, the launcher is checking that the
Claude login inside Docker is still valid, running the pipeline's own preflight, building
the run's container images, and starting the scheduler. The scheduler is the process that
hosts the Software Architect."

(If it takes a while: switch to Script 2, segment A.)

### The run appears

"There it is. The run id is a timestamp. The architect line went green: the scheduler is
alive, and it shows the age of its last journal event. NSC-042 shows as Task Unstarted,
the purple state, meaning it is admitted to the run but nobody has claimed it."

"Now the Software Architect gets its turn. It's a Claude session that sees every eligible
task and decides what can safely run in parallel. With one task there's not much to decide,
but it still has to say yes, and it still checks dependencies and the files the task will
touch. When it says start, the scheduler launches a worker."

### Task Working

"Task Working. One worker now owns NSC-042 under a lease. Watch the stage text on the node:
first it prepares an isolated checkout of the project, then it validates the execution
scope. That scope is the list of files the task is allowed to change. For 042 that's the
DoorPrototype scene builder, its test file, the wall tile asset and the scene. Anything
outside that list would be rejected later no matter how good the code was."

"Then it runs the execution crew. That's two Claude roles inside Docker, an implementer
and a validator, working from the task contract, with no network access to anything but
the model. The host never trusts their claims; it diffs the checkout itself and hashes
every artifact."

(This is the long wait: Script 2, segments B and C.)

### Local Review Ready

"And it lands here: Local Review Ready. Every other task in this pipeline would now be
committed onto this branch automatically. 042 is held. It's the one task that is always
human-reviewed, so the pipeline stops, keeps the candidate patch and the crew's own
validation report, and waits for me."

"In the production mode of the same tool, this exact moment is a GitHub Issue with a
checklist, and the run continues only when I post a PASS with the tested commit hash on
it. Nothing else can move it. That's deliberate: the model writes the code, the machine
proves what it touched, and the human owns the judgement."

### If you want to close the loop on camera

"I can stop the run cleanly from the same button, and the reset button deletes the run
state without touching the repo. The checkout stays clean; the only thing that changes
the branch is an accepted candidate."

---

## Script 2: "About the tool" (while it runs)

### Segment A: what it is (about 90 seconds)

"While that starts, here's what this tool is. It's an autonomous software pipeline for a
Unity game called No Safe Circle. The unit of work is a task contract: a YAML file with
an id, acceptance criteria that cite the design document, completion gates that say what
proves it done, a dependency list, and the exclusive files or scenes it needs. The task
graph is a few hundred of those."

"The pipeline runs that graph. A Software Architect agent picks what to run in parallel.
Each task gets its own worker, and each worker is a deterministic host program with an AI
supervisor inside it. The host owns every fact: which commit, which files, which lease.
The model only chooses the next bounded action from a menu the host offers. If the model
picks something the state doesn't allow, the host refuses."

### Segment B: why it's built this way (about two minutes)

"The design rule underneath everything is: no claim without evidence. A task is only done
when there's a delivery record committed in the repo that names the exact commit, the
exact tree hash, and the validation artifacts, and the graph tooling can re-derive that
state from the files alone. If a record is missing or ambiguous, the task is not done,
whatever any agent said."

"That's why everything is hash-bound. The task contract has a hash. The run has an
immutable manifest. Each crew gets its own frozen copy of that manifest, so a worker that
was admitted earlier keeps its view of the world even if a sibling task advanced the source
underneath it. Workers hold leases, not just claims. Source changes go through one
serialized queue. When two things could race, the code is written to fail closed and leave
a durable reason."

"Decomposition is part of it too. Some contracts are too big for one agent, so a
decomposition worker writes a plan for children, another model session reviews it, and
the host validates it deterministically before children are admitted. Today one of those
plans was rejected because its coverage table pointed at a child it hadn't defined. That's
the system working: a bad plan never became tasks."

### Segment C: local versus production (about 90 seconds)

"There are two modes. Production runs against GitHub: each task has a coordination Issue
with a state machine in it, candidates are pushed as exact task branches, an integration
gate merges main, validates, and pushes the synchronized commit, and human handoffs happen
on the Issue. Local rehearsal is the same pipeline with GitHub fenced off: it commits
accepted candidates into a local source, integrates them serially, and wakes the architect,
and it deliberately never pushes. It exists so the whole machine can be exercised, and
broken, without touching the real repository."

"To test the machine itself there's a gauntlet: eight synthetic tasks that create disjoint
files, plus this one real task, 042, that's kept as the human-reviewed control. Runs of that
gauntlet are how the pipeline's own bugs get found. Several were fixed today: a scope check
that rejected valid work because of a generated Unity meta file, a race between a source
read and a decomposition apply, and a stop that didn't reach the agents."

### Segment D: what I'm looking at (use while the crew runs, about a minute)

"The viewer is reading the run's journal, not asking the agents. The stage text on the node
comes from durable events the worker wrote. The token and cost panel is built from
persisted provider usage, per call, per role; if the price table for a model isn't known it
says so rather than guessing. The architect line is a real process check. If this window
says something is happening, the artifacts on disk say the same thing."

### Segment E: the operator loop (if you still have time)

"The part I've been working on most recently is the operator loop: one checkout, one
viewer on one port, a start/stop toggle, a poke button that wakes the scheduler, and a
reset that only unlocks after a stop and never touches the repo. Stop is cooperative now:
the scheduler stops admitting, every worker sees the request at its next turn and records
why it stopped, and a crew that's mid-flight is terminated so the drain takes seconds, not
a full model call. Force stop exists for anything that ignores that."

---

## Cue card (keep this next to you)

| Viewer shows | Say | Script |
| --- | --- | --- |
| no active run, Start run | intro, press Start | 1 / before |
| Starting… | login, preflight, images, scheduler | 1 + 2A |
| run id, architect green, 042 purple | admission, architect decides | 1 / appears |
| Task Working, checkout / scope | isolation, allowed files | 1 / working |
| Task Working, execution crew | implementer + validator in Docker | 2B, 2C, 2D |
| Local Review Ready | held for human; production = GitHub Issue | 1 / review |
| anything odd | Stop run, then talk 2E | 1 / close |
