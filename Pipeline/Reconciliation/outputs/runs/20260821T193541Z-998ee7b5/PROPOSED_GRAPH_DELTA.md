# Proposed Persistent-Graph Delta

> This is a proposal generated from an immutable reconciliation snapshot. It does not modify `Tasks/*.yaml`.

- **Reconciliation run:** `20260821T193541Z-998ee7b5`
- **Status:** `bootstrap_seed_proposal`
- **Persistent graph mutated:** `false`

## Summary

No persistent Tasks/*.yaml graph exists yet. This snapshot proposes bootstrap seed records only; human approval and the deterministic Work Graph Seeder are required before any persistent task state is created.

## Proposed Bootstrap Seed Records

| Reconciliation key | Kind | Title | Proposed status | Execution | Exclusive resources | Parent | Depends on |
|---|---|---|---|---|---|---|---|
| player | feature | Player | open | not_applicable |  | no-safe-circle |  |
| player-movement | implementation | Mouse-Directed Player Movement, Shared Pointer Projection, and Movement Restriction | open | single_agent | repo-file:Assets/InputSystem_Actions.inputactions, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | player |  |
| player-health | implementation | Player Health Ownership, Restore, Death Transition, and Feedback | open | single_agent | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | player |  |
| player-mana | implementation | Player Mana Ownership, Restart Reset, and Denied-Cast Feedback | open | single_agent |  | player |  |
| combat | feature | Wizard Combat and Spells | open | not_applicable |  | no-safe-circle |  |
| fireball | implementation | Charged Fireball | open | single_agent | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, repo-file:Assets/InputSystem_Actions.inputactions | combat | player-movement, enemy-health-damage-defeat |
| frost-field | implementation | Frost Field | open | single_agent | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, repo-file:Assets/InputSystem_Actions.inputactions | combat | player-movement, enemy-status-effect-displacement |
| force-wave | implementation | Force Wave | open | single_agent | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, repo-file:Assets/InputSystem_Actions.inputactions | combat | enemy-status-effect-displacement |
| enemies | feature | Enemies | open | not_applicable |  | no-safe-circle |  |
| active-enemy-registry | implementation | Active Enemy Registry | open | single_agent |  | enemies |  |
| enemy-health-damage-defeat | implementation | Enemy Health/Defeat | open | single_agent |  | enemies | active-enemy-registry |
| enemy-status-effect-displacement | implementation | Enemy Status-Effect and Forced Displacement | open | single_agent | logical:enemy-locomotion-behavior-surface | enemies | enemy-pursuit-search-foundation, gameplay-navigation-locomotion |
| enemy-pursuit-search-foundation | implementation | Enemy Detection, Pursuit, and Search/Reacquisition Foundation | open | needs_execution_decomposition | logical:enemy-locomotion-behavior-surface | enemies | gameplay-navigation-locomotion |
| melee-enemy | implementation | Melee Enemy Archetype | open | needs_execution_decomposition | logical:enemy-locomotion-behavior-surface | enemies | enemy-pursuit-search-foundation, enemy-health-damage-defeat, active-enemy-registry |
| ranged-enemy | implementation | Ranged Enemy Archetype | open | needs_execution_decomposition | logical:enemy-locomotion-behavior-surface | enemies | enemy-pursuit-search-foundation, enemy-health-damage-defeat, active-enemy-registry |
| locked-door-enemy-attack | implementation | Locked-Door Enemy Attack Initiation | open | single_agent | logical:enemy-locomotion-behavior-surface | enemies | enemy-pursuit-search-foundation, door-close-lock-break-lifecycle |
| doors | feature | Doors and Interaction | open | not_applicable |  | no-safe-circle |  |
| door-open-interaction | implementation | Cursor-Targeted Door Opening (Click-to-Approach, Arm's-Reach Auto-Timer, Interruption) | open | single_agent | repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | doors | player-movement |
| doorway-crossing-state | implementation | Shared Doorway-Crossing State (Forward-Side Crossing Detection) | open | single_agent | repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | doors |  |
| door-close-lock-break-lifecycle | implementation | Door Close/Lock, Health Restore Request, Durability, and Locked-to-Broken Lifecycle | open | needs_execution_decomposition | repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity, logical:gameplay-walkability-surface | doors | doorway-crossing-state, player-health, gameplay-navigation-locomotion |
| world | feature | World and Unity Foundations | open | not_applicable |  | no-safe-circle |  |
| fixed-isometric-camera | implementation | Fixed Isometric Camera | complete | not_applicable |  | world |  |
| tilemap-navigation-package-configuration | implementation | Tilemap and AI Navigation Package Configuration | open | single_agent | repo-file:Packages/manifest.json | world |  |
| gameplay-navigation-locomotion | implementation | Gameplay Navigation/Locomotion Foundation | open | needs_execution_decomposition | logical:gameplay-walkability-surface, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | world | tilemap-navigation-package-configuration |
| world-visual-foundation | implementation | Tilemap and SpriteRenderer World Visual Foundation | open | needs_execution_decomposition | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | world | tilemap-navigation-package-configuration |
| encounters | feature | Dungeon Encounters | open | not_applicable |  | no-safe-circle |  |
| encounter-admission-cap-enforcement | implementation | Encounter Admission Active-Enemy-Cap Enforcement | open | single_agent |  | encounters | active-enemy-registry |
| five-room-content-authoring | feature | Five-Room Floor Content Authoring | open | not_applicable |  | world | world-visual-foundation |
| dungeon-encounter-content-authoring | feature | Dungeon Encounter Placement and Composition Authoring | open | not_applicable |  | encounters | encounter-admission-cap-enforcement, door-close-lock-break-lifecycle, melee-enemy, ranged-enemy |
| floor-run-restart | feature | Floor Run/Restart | open | not_applicable |  | no-safe-circle |  |
| floor-run-restart-bootstrap | implementation | Floor Run/Restart Bootstrap (Current-Owner Stage) | open | single_agent | logical:floor-run-restart-orchestrator, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | floor-run-restart | player-health, player-mana, player-movement, door-open-interaction |
| floor-run-restart-persistent-closure | implementation | Floor Run/Restart Persistent-Systems Closure | open | needs_execution_decomposition | logical:floor-run-restart-orchestrator, repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | floor-run-restart | floor-run-restart-bootstrap, player-health, player-mana, player-movement, door-open-interaction, doorway-crossing-state, door-close-lock-break-lifecycle, enemy-health-damage-defeat, enemy-pursuit-search-foundation, enemy-status-effect-displacement, active-enemy-registry, encounter-admission-cap-enforcement, fireball, frost-field, force-wave |
| win-loss-conditions | feature | Win/Loss Conditions | open | not_applicable |  | no-safe-circle |  |
| final-escape-victory | implementation | Final Escape / Victory (Game Flow/Victory Capability) | open | needs_execution_decomposition | repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs, unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity | win-loss-conditions | doorway-crossing-state, player-movement, door-open-interaction, fireball, frost-field, force-wave |
| no-safe-circle | feature | No Safe Circle | open | not_applicable |  |  |  |
| delivery-and-build | feature | Delivery and Build | open | not_applicable |  | no-safe-circle |  |
| windows-build-scene-registration | implementation | Windows Build Scene Registration | open | single_agent | repo-file:ProjectSettings/EditorBuildSettings.asset | delivery-and-build |  |

## Proposed Non-Code / Delivery / Pipeline Records

| Type | Title | Status | Evidence / rationale |
|---|---|---|---|
| delivery_requirement | Windows build | confirmed | Directly and repeatedly stated as required delivery scope in the current GDD; represented as an actionable configuration gap via windows-build-scene-registration. |
| pipeline_constraint | No concurrent Unity asset edits | confirmed | Stated identically in both Section 4 and Section 5 as a hard process invariant; applications of this rule are represented per-task via exclusive_resources across all domain workers. |
| pipeline_constraint | Credentials outside source control | confirmed | Directly stated in Section 5 API and Tool Constraints. |
| pipeline_constraint | Minimal-context dispatch | confirmed | Explicitly required by both Section 4 and Section 5 as a mandatory pipeline constraint. |
| pipeline_constraint | Failed-task retry policy | confirmed | Directly stated as a required pipeline constraint in Section 5. |
| pipeline_constraint | Compile-before-validation gate | confirmed | Directly stated in Section 5 API and Tool Constraints. |
| pipeline_constraint | Isolated execution and task handoff requirements | confirmed | Directly stated as required process/handoff structure in Section 4 and reiterated in Section 5 Agent Coordination. |
| pipeline_constraint | Human inspection and final integration authority | confirmed | Explicitly stated as required human-authority process constraints in Sections 4 and 5. |
| pipeline_constraint | Agent scope and canon discipline | confirmed | Stated identically in Section 4 and Section 5 as a required scope-discipline constraint on implementation/planning/reconciliation agents. |
| non_code_requirement | Runtime generative-AI prohibition | confirmed | Directly and explicitly required/excluded scope in the current GDD; a non-code technical constraint on the shipped game rather than a build step or agent-process rule. |
| pipeline_constraint | Development-time generated-art import boundary | confirmed | Directly stated in Section 5 Runtime Implementation and reiterated in the Technical Strategy generative-tools note; a required process/validation constraint on content/asset pipeline work rather than gameplay implementation. |
| pipeline_constraint | Non-canonical prototype scene preservation | confirmed | Directly stated in Section 5 Current Prototype Scene Evidence; confirmed present via Assets/Scenes/DoorPrototype.unity and Assets/Scenes/SampleScene.unity glob results. |
| pipeline_constraint | Current prototype scene-builder exclusive-write lock | confirmed | Directly stated as a required durable process rule in Section 4; per-task applications are represented as matching exclusive_resources entries across domain workers whose implementation writes through the builder/scene. |
| pipeline_constraint | Development Agent Ownership Invariants | confirmed | Directly stated as a required cross-cutting process constraint in Section 4; the specific per-agent ownership boundaries (Wizard Combat, Enemy Pursuit, Door and Interaction, victory coordination, Dungeon Encounter, Unity Validation) are represented as acceptance criteria/dependencies on their respective owning work items across the other domain workers. |
| pipeline_constraint | Planning token budget ceiling | confirmed | Directly stated as a pipeline planning/orchestration constraint in Section 5 Token Budget. |

## Next Action

`human_review_then_seed`
