# Assignment 6 — GER Pipeline

**Game:** No Safe Circle

This Assignment 6 implementation reuses working systems from earlier
assignments instead of creating duplicate agents.

## Reused components

- **Assignment 5 Implementation Agent** = Generator and Refiner
- **Assignment 3 validation infrastructure** = Evaluator
- **Assignment 6** = GER orchestration, GDD rule contract, runtime-feedback
  handoff, and Circuit Breaker

The selected goal comes from:

`GoalOrientedAgent/outputs/next_goal_selection.json`

For the current run, Assignment 5 selected:

**Fixed Isometric Camera and Projection Setup**

## Normal GER run

```powershell
docker compose run --rm claude python3 Assignment6GER/ger_pipeline.py
```

The implementation agent writes the selected feature under `Assets/`.
The Evaluator checks the result against the specific No Safe Circle GDD rule.
If static evaluation fails, the same implementation agent is re-invoked as the
Refiner.

## Human Unity runtime feedback

A static PASS is not the end of integration. The No Safe Circle GDD explicitly
keeps the developer responsible for inspecting scenes/prefabs, Play Mode
testing, game feel, and final integration.

If Unity testing exposes a real failure after static PASS, record it in a JSON
file and resume the GER loop at **Refiner**, rather than starting over at
Generator.

For the current camera failure, this patch includes:

`Assignment6GER/outputs/runtime_feedback.json`

It records that:

- the rebuilt orthographic camera faces the wrong direction; and
- keeping the camera at a single world-space position makes gameplay unusable
  as the player moves.

Resume with:

```powershell
docker compose run --rm claude python3 Assignment6GER/ger_pipeline.py --runtime-feedback Assignment6GER/outputs/runtime_feedback.json
```

The resume path:

1. preserves the original implementation/evaluation pass artifacts;
2. archives the previous `final_result.json`;
3. counts the runtime failure as a refinement-triggering evaluation failure;
4. invokes Assignment 5's implementation agent as **Refiner**;
5. sends the refined implementation through the Assignment 3-based
   **Evaluator** again;
6. still respects the configured Circuit Breaker maximum.

After another static PASS, test the refined result in Unity again. If it still
fails, update `runtime_feedback.json` with the new observed problem and resume
again. Repeated failed repairs eventually exhaust the Circuit Breaker and
produce `human_review_required`.

## Camera rule after runtime discovery

The canonical GDD requirements remain:

- orthographic isometric presentation;
- a consistent isometric viewing angle; and
- no free camera rotation.

The runtime feedback does **not** rewrite those GDD requirements. It records an
integration failure discovered by the human developer and clarifies that camera
translation/follow needed to keep gameplay visible remains within the selected
camera task.

## Important outputs

- `ger_contract.json`
- `implementation_pass_N.json`
- `evaluation_pass_N.json`
- `runtime_feedback.json`
- `final_result_before_runtime_feedback.json`
- `final_result.json`

The final README for submission should describe both the initial static PASS
and the later Unity runtime failure/refinement, because that demonstrates why
evaluation must include real game integration rather than syntax/static checks
alone.
