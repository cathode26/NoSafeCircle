# NSC-077 review checklist (Game Agent)

Items to check when the Codex implementation (`C:\nscrev\nsc077-codex`, branch `codex/nsc077-moving-enemy-art-20260917`) comes back, and to hand to the fresh Claude reviewer.

1. **VAL-003 component check.** Requested by the GER Orchestrator on 2026-09-17.
   - `EnemyArtIntegrationTests` must assert that the required gameplay components are **present**, not that they are the **exact** component set.
   - For MeleeEnemy that means one each of NavMeshAgent, EnemyTargetKnowledge, EnemyPursuitMovement and EnemyHealth, with the NavMeshAgent settings unchanged.
   - Why: NSC-008 Frost Field and NSC-009 Force Wave will make `DoorPrototypeGlobalSceneBuilder.BuildChaseEnemy` add exactly one EnemyStatusEffectMovement to every MeleeEnemy. An exact-set assertion would break when the first spell lands.
   - The LanternWraith gets no status-effect component; it has no NavMeshAgent.
   - If the Codex test asserts an exact set, fix it before merging.
2. **Facing uses the NSC-075 mapping** (screen up = Z - X), and it is checked in-game, not only in tests.
3. **Import settings:** Texture2D shape and a cookie-defaults reset for the enemy sprites. Only `.png.meta` files change under `Art/Enemies/Source`.
   - Rev 4 (AC-003): 64 PPU, Point filter, no mipmaps. VAL-001 has an importer check for 64 PPU. Ground-line pivots are unchanged.
4. **Out-of-bounds files untouched:** DoorPrototypeSceneBuilder.cs, WizardAnimationController.cs, `.asmdef` files, ProjectSettings.
5. **The EnemyFireballCaster.cs to EnemyLanternWispCaster.cs rename keeps the GUID** (`.meta` moved with it), and the gameplay numbers are unchanged.
6. **Contract retro-check gate.** From the documentation agent, 2026-09-17.
   - NSC-077 rev 3 (`d9af025a5`) was committed without the independent re-check. The GER Agent is running a Codex retro-check on it.
   - BEFORE asking Vincent to Unity-test the NSC-077 candidate, get that verdict. If it is "revise", a follow-up contract revision may change what the candidate must build, so compare the candidate against the revised contract first.
   - NSC-055 rev 3 and NSC-015 rev 7 are in the same situation.
   - Rev 4 (`25fdc505d`) is getting its own Codex buildability check. Report: `C:\nscrev\codex-jobs\codex-contract-check-NSC-077-rev4-20260917.report.md`. The GER messages if it says "revise". Read the verdict before the candidate goes to Vincent.
7. **Rev 4 Visual transform.** The GER Orchestrator committed it on 2026-09-17 after Vincent's pixel-density decision B.
   - The enemy Visual is created with world size (1,1), so its scale is a uniform 1.
   - The Visual's world rotation always equals the camera's, Euler (30,-45,0). NavMeshAgent rotates the MeleeEnemy root, so EnemyAnimationController restores the Visual's rotation every frame after movement.
   - NavMeshAgent settings stay unchanged. Don't "fix" the lean by disabling agent rotation.
   - VAL-003 needs a scene check for uniform scale and camera-facing rotation.
   - VAL-004 needs a Play Mode check that the rotation holds after the root rotates.
   - VAL-008: Vincent's in-game check covers size and lean. Idle is 128 px = 2x2 units; a walk frame is 176 px = 2.75 units.
   - Ground contact and sorting still follow NSC-039.
   - AC-007 and INT-002: Vincent picked the "grumpy face" wisp look, but the teal orb stand-in stays until that art's production pass. No new wisp art belongs in this candidate.
9. **Rev 5 camera constant.** `db0532ab4` came from the GER's rev 4 contract check, which said "revise".
   - EnemyAnimationController holds its own runtime constant (30, -45, 0), the same way WizardAnimationController holds its mapping. Runtime code must never reference the Editor-only `DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles`.
   - `DoorPrototypeGlobalSceneBuilder.IsometricCameraEulerAngles` stays an independent literal field. Codex's rev 4 pass had made it a property that forwards to the runtime constant, which turns the equality test into a tautology. That must be undone.
   - An EnemyArtIntegrationTests Edit Mode assertion checks that the runtime constant equals the builder field.
   - The VAL-004 Play Mode checks compare against the literal (30, -45, 0), not against the controller's constant.
   - The rev 5 contract check report is `C:\nscrev\codex-jobs\codex-contract-check-NSC-077-rev5-20260917.report.md`. That is the verdict to read before Vincent's test.
10. **SUPERSEDED by rev 9 (`643016721`).**
    - After Build 2, every generated file is byte-identical to Build 1 except the scene. The scene is excluded.
    - Commit the scene saved by Build 2. VAL-003 (EnemyArtIntegrationTests) proves its content.
    - Base must be at or after `74207b22f`. The whole DoorPrototypeSceneBuilderTests fixture must pass. Record the exact base commit.
    - The snapshot tool in `evidence-tools\` is optional extra evidence.
    - History (rev 7 text, kept below): **VAL-007 scene idempotency, agreed with the GER on 2026-09-17.**
    - After the second build, every generated file must be byte-identical except `Assets/Scenes/DoorPrototype.unity`.
    - The scene may change only in local fileIDs and references to them. It must keep the same object count per class and per script GUID, and the same sorted serialized sizes.
    - Evidence: `C:\nscrev\reports\nsc077\unity\scene-shape-compare-3233ac923.txt`, produced by `scene_shape_compare.py`. Redo it on the final candidate and put it in the delivery evidence.
    - Rev 6 adds a no-missing-scripts assertion to the VAL-003 saved-scene test.
    - Rebase once, onto rev 7, when the GER sends the commit.
8. **The candidate started on rev 3.** The first Codex pass (`cc4ff8899`, `139e37795`) was built against rev 3, which had 128 PPU and a non-uniform Visual. Check that the rev 4 follow-up replaced every 128 PPU value and non-uniform scale, including in the tests.
