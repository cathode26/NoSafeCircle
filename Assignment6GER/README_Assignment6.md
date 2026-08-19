# Assignment 6 — Build a GER Pipeline for Your Capstone

**Student:** Vincent Liguori  
**Game:** No Safe Circle  
**Assignment:** Assignment 6 — Build a GER Pipeline for Your Capstone

## Overview

For Assignment 6, I built a GER pipeline that generates, evaluates, refines, and, if necessary, escalates Unity implementation work for **No Safe Circle**.

Rather than creating new agents from scratch, I reused systems from earlier assignments:

- **Assignment 5** selects what feature should be built next.
- The **Assignment 5 implementation agent** acts as both the **Generator** and the **Refiner**.
- The **Assignment 3 validation infrastructure** acts as the **Evaluator**.
- Assignment 6 adds the **GER orchestration**, a game-specific evaluator contract, runtime-feedback handling, and a **Circuit Breaker**.

This made Assignment 6 a continuation of the earlier agent work instead of a separate demo.

## What Content Does the Pipeline Generate?

The pipeline generates **Unity implementation code for missing No Safe Circle features**.

Assignment 5 had already analyzed the current game against the GDD and produced a list of candidate goals. Instead of regenerating that expensive analysis, I added a lightweight reselection step that reused the saved Assignment 5 artifact and excluded the already-completed Mana goal.

The next selected goal was:

> **Fixed Isometric Camera and Projection Setup**

The goal was to replace the disposable perspective test camera with the fixed orthographic isometric presentation required by the GDD.

## GDD Rule Enforced by the Evaluator

The Assignment 6 Evaluator enforces a specific No Safe Circle GDD rule rather than performing only generic code validation.

For this run, the camera implementation had to satisfy these requirements:

1. The gameplay Main Camera uses **orthographic projection**.
2. The game maintains a **consistent isometric viewing orientation**.
3. The player cannot freely rotate the world view.
4. The implementation stays inside the selected camera/projection task instead of expanding into unrelated systems such as Tilemaps, spells, enemies, or sprite sorting.

A script compiling successfully was not enough to pass.

## GER Architecture

```text
Assignment 5 Goal Selection
        ↓
next_goal_selection.json
        ↓
Assignment 5 Implementation Agent
        ↓
GENERATOR
        ↓
Assignment 3 Validation Infrastructure
        ↓
EVALUATOR
      /       \
   PASS       FAIL
    ↓           ↓
Unity Test   Assignment 5 Implementation Agent
                ↓
             REFINER
                ↓
             EVALUATOR
                ↓
        repeated failures
                ↓
         CIRCUIT BREAKER
                ↓
           Human Review
```

The Circuit Breaker allows a maximum of **three refinement attempts**. If the system cannot self-correct within that limit, the task is escalated for human review.

## What Happened During the Run

### Implementation Pass 1 — Generator

The Assignment 5 implementation agent generated the first camera implementation.

It modified:

- `Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
- `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs`

The implementation changed the camera to orthographic and added tests.

### Evaluation Pass 1 — Static Pass

The Evaluator found that the implementation satisfied all four static acceptance criteria:

- orthographic projection,
- fixed isometric presentation,
- no free camera rotation,
- correct scope.

However, the checked-in Unity scene was still stale, so I rebuilt the Door Prototype scene in Unity and tested the result manually.

### Unity Runtime Test 1 — Failure

The camera was orthographic, but the game was not usable:

- the camera faced the wrong direction;
- the camera did not follow the player;
- the static evaluator had interpreted “fixed camera” too narrowly.

I recorded this as:

`Assignment6GER/outputs/runtime_feedback000.json`

The pipeline was updated so human Unity runtime failures could re-enter the GER loop as evaluation feedback.

### Implementation Pass 2 — Refiner

The Assignment 5 implementation agent was reused as the Refiner.

It created:

- `Assets/NoSafeCircle/DoorPrototype/Scripts/IsometricCameraFollow.cs`

and modified the scene builder and camera tests.

The camera could now translate with the player while preserving a fixed isometric orientation.

### Evaluation Pass 2 — Static Pass

The Evaluator again passed the implementation statically.

I rebuilt and tested the scene in Unity again.

### Unity Runtime Test 2 — Failure

The camera still did not frame the game correctly. The player-follow behavior existed, but the viewing side and framing were wrong and the starting door was no longer properly visible.

I recorded this separately as:

`Assignment6GER/outputs/runtime_feedback001.json`

Runtime feedback files are preserved as an append-only history:

```text
runtime_feedback000.json
runtime_feedback001.json
runtime_feedback002.json
...
```

### Implementation Pass 3 — Refiner Made No Progress

The Refiner reported `implemented`, but it made **no observed changes under `Assets/`**.

This exposed a weakness in the original Assignment 5 implementation contract: Assignment 5 expected an `implemented` result to always include modified files and would crash otherwise.

For Assignment 6, I changed that behavior. A no-op refinement is now treated as a **failed repair attempt**, not a pipeline error.

The GER progress guard detected the no-op and forced the loop to continue instead of accepting a false success.

### Implementation Pass 4 — Final Refinement

The final allowed refinement modified the scene builder and its tests again. The Evaluator verified the current camera implementation and the additional regression safeguards.

The implementation now used:

- orthographic projection,
- a consistent isometric orientation,
- camera translation/follow without free rotation,
- stable camera-to-player offset behavior,
- tests for camera framing and fixed rotation,
- a regression check for invalid/null follow targets.

The Evaluator returned PASS.

At this point, all **three allowed refinements** had been used. If the feature had failed again, the Circuit Breaker would have escalated the task to human review.

## Final Unity Validation

After the final GER pass, I rebuilt the Door Prototype scene in Unity and tested the result manually.

The camera now behaves as intended: it uses a **Diablo / Ultima Online-style orthographic isometric presentation**, follows the player appropriately, and does not allow free camera rotation.

I then ran the relevant Unity automated tests:

- the full `DoorPrototypeSceneBuilderTests` EditMode suite;
- the existing `DoorInteractionPlayModeTests` PlayMode suite.

**All tests passed.**

## Did the Pipeline Catch Something I Would Have Missed?

Yes.

The most useful result of this assignment was discovering that a static evaluator can prove that code satisfies a written requirement while the actual game can still be broken.

The first camera implementation passed static evaluation because it was orthographic and used a fixed isometric rotation. In Unity, however, it faced the wrong direction and did not follow the player.

The second implementation also passed static evaluation but still framed gameplay incorrectly.

Human Play Mode testing exposed those failures. The failures were converted into structured runtime feedback and fed back into GER so the Refiner could continue working on the same selected goal.

The pipeline also caught a different failure during Pass 3: the Refiner made no code changes even though unresolved runtime feedback existed. A GER progress guard rejected that no-op repair and counted it toward the Circuit Breaker instead of allowing the pipeline to fail silently.

## Important Output Artifacts

The Assignment 6 run preserves the complete history of the experiment under:

`Assignment6GER/outputs/`

Important artifacts include:

```text
ger_contract.json

implementation_pass_1.json
implementation_pass_2.json
implementation_pass_3.json
implementation_pass_4.json

evaluation_pass_1.json
evaluation_pass_2.json
evaluation_pass_3.json
evaluation_pass_4.json

runtime_feedback000.json
runtime_feedback001.json

final_result.json
final_result_pass_*.json

evaluator_agent_log_pass_*.json
```

This history makes it possible to reconstruct what each agent did, what failed, what feedback was provided, and how the implementation changed.

## Final Result

The GER pipeline successfully demonstrated all four required behaviors:

- **Generator:** produced Unity implementation code for the selected No Safe Circle feature.
- **Evaluator:** checked the implementation against a specific rule from the No Safe Circle GDD.
- **Refiner:** repeatedly used evaluator and Unity runtime feedback to repair the implementation.
- **Circuit Breaker:** bounded the loop to three refinement attempts and would have escalated to human review if the final attempt failed.

The selected camera feature ultimately passed both the GER Evaluator and real Unity validation.
