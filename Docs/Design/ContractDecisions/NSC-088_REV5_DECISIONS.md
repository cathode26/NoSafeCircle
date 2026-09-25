# NSC-088 revision 5 (GER Orchestrator decisions, 2026-09-17)

Input: Codex contract check of revision 4, C:/nscrev/codex-jobs/codex-contract-check-NSC-088-rev4-20260917.report.md ("revise": 1 blocking, 6 major, 1 minor). Every finding is accepted.

Spell design stays as decided in revision 4. The two ordered decomposition children also stay:
1. enemy target redirect in EnemyTargetKnowledge;
2. the Wizard Combat spell.

Align with the settled spell conventions in C:/nscrev/ger-contract-revisions-20260916/spells/REV4_DECISIONS.md (SP4-1 to SP4-3) and NSC-009 revision 6 (HUD non-overlap).

## F1. Builder facade lock (blocking)
- Add repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs to exclusive_resources.
  - It is the Build facade that materializes Assets/Scenes/DoorPrototype.unity; GDD line 632 requires the paired builder and scene lock.
  - Keep the explicit rule that this task does not edit that file.
- decomposition_reason: the Wizard Combat child claims the facade together with the scene. The enemy-redirect child claims neither.

## F2. A route that closes mid-travel
- AC-007 and a VAL-001 or VAL-002 case: cast along a complete route through an open doorway, then seal or lock that doorway before the phantom crosses.
- Assert:
  - the phantom stops at its last reachable position;
  - it stays visible, stationary and the redirected enemies' CurrentTarget until its lifetime ends;
  - it never passes the blocker, disappears early, or picks a new destination.

## F3. Fresh discovery across loaded scenes
AC-005 already requires cast-time FindObjectsByType<EnemyTargetKnowledge>(FindObjectsSortMode.None). Add a VAL-002 case:
1. After SpectralDecoy initializes, create and enable an eligible pursuing enemy in a second loaded temporary scene.
2. Cast.
3. Verify that enemy is redirected.

## F4. Return invariants (enemy-redirect child, VAL-002/VAL-003)
Add one focused assertion for each case:
1. **Leash exceeded while redirected:** the enemy keeps the wizard as its retained target and searches its start position. A later phantom expiry does not overwrite that search.
2. **Expiry inside LoseTargetDistance with no line of sight:** pursuit resumes without a line-of-sight check.
3. **Wizard unavailable at expiry (destroyed or null):** no exception. The enemy keeps whatever retained knowledge AC-004 defines and enters SearchingLastKnownPosition at the saved switch position.
4. **Mismatched decoy Transform:** EndSpectralDecoyRedirect with a Transform that is not this enemy's current decoy target changes nothing.

## F5. Optional references are proven optional (SP4-3)
Add a VAL-004 case: with SpectralDecoy left unassigned on both TitleScreenController and WizardGameEntryController, WizardGameEntryController.EnterWorld still completes. Assert that HasEnteredGameplay becomes true and GameplayEntryCount advances.
- HasValidReferences() is private, so prove it through this behavior.
- The builder test also asserts that TitleScreenController's gameplayInputBehaviours excludes SpectralDecoy and still holds exactly DebugDamageControl and DebugManaSpendControl.

## F6. Binding proof on the project asset (SP4-1)
VAL-005's Edit Mode test loads Assets/InputSystem_Actions.inputactions directly and asserts, for the Player map's SpectralDecoy action:
- the action type is Button;
- it has exactly one binding, `<Keyboard>/f`, whose groups (split on ';', empty entries ignored) contain only Keyboard&Mouse;
- it has no gamepad, joystick, touch or XR binding;
- no other Player action binds `<Keyboard>/f` (MoveToCursor, Interact, Attack, Jump, Fireball, FrostField, ForceWave, or any other);
- Attack still has exactly its six base bindings, compared as path plus group set:
  - `<Gamepad>/buttonWest` [Gamepad]
  - `<Mouse>/leftButton` [Keyboard&Mouse]
  - `<Touchscreen>/primaryTouch/tap` [Touch]
  - `<Joystick>/trigger` [Joystick]
  - `<XRController>/{PrimaryAction}` [XR]
  - `<Keyboard>/enter` [Keyboard&Mouse]

## F7. Phantom and wisp are told apart
Vincent's human review (VAL-006), at the fixed gameplay camera: with a Lantern Wraith lantern-wisp projectile in flight near the phantom, confirm the phantom (translucent teal-violet wizard silhouette with afterimages) is clearly distinct from the teal wisp. If the placeholder colors make them hard to tell apart, record that as presentation feedback rather than approving.

## F8. Cooldown UI layout (minor, matches NSC-009 revision 6)
- The builder test proves, at the 1920x1080 CanvasScaler reference resolution, that SpectralDecoyCooldownUI's rectangle overlaps none of these builder GameObjects:
  - HealthFill
  - InteractPrompt
  - ProgressFill
  - ManaFill
  - DebugDamageButton and DebugManaSpendButton
  - ControlsHud
  - ForceWave's cooldown UI
- It proves this for both the in-memory build and the committed scene.
- VAL-006 confirms readability.
