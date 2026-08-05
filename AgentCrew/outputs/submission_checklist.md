# Submission Checklist — Sealed Door Prototype (Assignment 3)

## Crew Code
- [x] `AgentCrew/orchestrator.py` runs four independent Claude Code invocations with file-artifact handoffs.
- [x] Pipeline runs and produces output without crashing (see `AgentCrew/outputs/crew_run_log.json`).

## Three or More Coordinated Agents
- [x] Feature Planning Agent
- [x] Door and Interaction Agent
- [x] Unity Validation Agent
- [x] Submission Packaging Agent (this agent)

## Game Connection
- [x] Feature is the Sealed Door Prototype — the core "hold still to be safe" mechanic from the No Safe Circle GDD.
- [x] Implementation lives under `Assets/NoSafeCircle/DoorPrototype/`, inside the actual Unity project.

## Role Clarity
- [x] Each agent has an explicit, documented input and output (see `README.md` table and `run_report.md`).
- [x] No agent is removable without breaking the pipeline (explained in `run_report.md`).

## Mermaid Diagram
- [x] `Docs/architecture.mmd` shows all four agents, artifacts, the pass/fail gate, the repair loop, and the human verification step.

## README
- [x] `README.md` names the game, explains crew output, game connection, agent roles/inputs/outputs, pipeline command, output locations, scene-builder and Play Mode instructions, human verification steps, known limitations, and AI usage statement.

## Successful Unity Compilation *(human step — pending)*
- [ ] Open project in Unity `6000.1.8f1`, confirm scripts compile with zero console errors.

## Successful Play Mode Tests *(human step — pending)*
- [ ] Run `NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests` in the Test Runner; confirm all five tests pass.

## Playable Prototype *(human step — pending)*
- [ ] Run **No Safe Circle â†’ Build Door Prototype Scene**.
- [ ] Play the scene: confirm prompt visibility, progress fill, release/movement/damage cancellation, and post-completion doorway passability.

## GitHub Repository *(human step — pending)*
- [ ] Review the working tree (`git status`) and commit/push the reviewed result.

## Final Submission Review *(human step — pending)*
- [ ] Confirm `validation_report.json` status is `pass`.
- [ ] Confirm all checklist items above are checked.
- [ ] Confirm no out-of-scope systems were introduced (see `implementation_summary.md` Â§ Excluded Systems Confirmation).

