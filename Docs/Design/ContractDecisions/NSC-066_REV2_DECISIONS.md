# NSC-066 revision 2: title screen over a live chase (GER Orchestrator decisions, 2026-09-17)

This carries out Vincent's 2026-09-15 direction, recorded in the graph-lead journal ("Title screen direction settled from Vincent's own SpaceInvaders project"). His lobby is the live game scene with UI over it: characters standing in the real world under real lighting, chunky buttons stacked left, and a UFO drifting across every 10-20 seconds. His notes on the backdrop and panel are quoted below. It is an owner revision, not a GER cycle.

## T1. Correct file ownership
The title screen is built in DoorPrototypeGlobalSceneBuilder.BuildTitleScreen, not DoorPrototypeSceneBuilder.cs.
- **Replace** the claim on repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs with repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs.
  - That file is already shared through a resource group; the commit tool reconciles the group.
- **Keep:**
  - logical:game-entry-menu-flow
  - TitleScreenController.cs (grouped with NSC-007/008/009/088)
  - TitleScreenPlayModeTests.cs
  - unity-scene:Assets/Scenes/DoorPrototype.unity
- **Claim** Assets/NoSafeCircle/DoorPrototype/Tests/Editor/TitleScreenSceneBuilderTests.cs, which already exists on main. If another task already claims it, report the conflict instead.
- **Add**, each with its .meta:
  - Assets/NoSafeCircle/DoorPrototype/Scripts/TitleScreenChaseBackdrop.cs
  - Assets/NoSafeCircle/DoorPrototype/Tests/TitleScreenChaseBackdropPlayModeTests.cs

## T2. No solid panel; left-stacked layout
Vincent: "Drop the solid background panel so the chase shows through."
- **Remove the opaque backdrop.** The full-screen title panel no longer draws the Color32(16, 10, 23, 255) backdrop. Its Image stays as a raycast blocker but is fully transparent (alpha 0), so title clicks never reach gameplay.
- **Legibility.** A soft, semi-transparent left-side gradient or vignette (at most 60% opacity at the far-left edge, fading to 0 before screen center) is allowed. No solid card may cover the world behind it.
- **Text.** Keep all three sayings exactly: "WELCOME, TINY WIZARD", "NO SAFE CIRCLE", "Cute wizards. Terrible odds.". Stack them on the left side of the screen, as in the SpaceInvaders lobby.
- **Start Game button.** A chunky button stacked below the text on the left. It keeps the current colors and hover/pressed states, stays readable at the canonical game resolution, and still triggers TitleScreenController.StartGame.

## T3. The chase backdrop
Vincent: "a mage fleeing an enemy, cycling through pairings — 4 mage identities against melee and ranged. Keep all three sayings."

**TitleScreenChaseBackdrop** runs only while TitleScreenController.IsTitleScreenVisible is true.
- **Spawning.** After a random interval between 10 and 20 seconds (the first pairing may appear sooner, within 3 seconds of the title screen showing), it spawns one pairing just off-screen on a randomly chosen side.
- **The pairing.** A fleeing wizard, followed about 2.5 world units behind by a pursuer. Both walk straight across the camera's view at a readable speed of about 1.5 world units per second, then despawn once past the far edge.
- **Pairing order.**
  - The wizard cycles through the 4 selectable wizard identities in their selection order; the drafter reads them from the wizard selection code on main.
  - The pursuer alternates the Dungeon Brute (MeleeEnemy art) and the Lantern Wraith.
  - All 8 identity-and-pursuer combinations appear within 8 pairings.
- **Animation only.** Actors use the existing walk animations: WizardAnimationController with the identity's clips, and EnemyAnimationController with NSC-077's MeleeEnemyAnimator/LanternWraithAnimator controllers. Each actor faces its travel direction.
- **Nothing gameplay-facing.** Actors have no NavMeshAgent, no collider, and no EnemyTargetKnowledge, attack, health, registry or input component. They never register with ActiveEnemyRegistry and never touch the Player.
- **Path.** The chase runs along the gameplay plane in front of the title camera's starting view, inside the Ruined Entry floor bounds X[-14,14] Z[-26,0]. At mid-path, both actors are inside the camera viewport and not behind the left-side title text. The drafter picks concrete path endpoints from the builder's camera and spawn setup on main, and a test asserts both conditions.
- **Lifecycle.** When StartGame hides the title screen, every backdrop actor is destroyed that frame and no new pairing spawns. The backdrop never runs during gameplay, wizard selection or victory.
- **Deterministic seam.** A public Tick(float deltaTime), plus a serialized seed or an injectable interval and side selector, so tests control timing and sides.

## T4. Gates
- **Play Mode tests (TitleScreenChaseBackdropPlayModeTests):**
  - the spawn interval stays within 10-20 seconds, and the first pairing appears within 3 seconds;
  - both sides are used;
  - identity and pursuer cycling covers all 8 combinations within 8 pairings;
  - actors carry only presentation components (no collider, NavMeshAgent or gameplay components) and never register;
  - actors despawn past the far edge;
  - the mid-path viewport and Ruined Entry bounds conditions hold;
  - after StartGame, all actors are destroyed and nothing spawns again.
- **Existing TitleScreenPlayModeTests** keep proving that gameplay input is inactive before Start Game and that one Start Game press makes exactly one wizard-selection request.
- **TitleScreenSceneBuilderTests:**
  - the in-memory build has one transparent full-screen raycast-blocking panel (alpha 0), the three sayings with exact text, a left-anchored Start Game button, and one TitleScreenChaseBackdrop;
  - the solid Color32(16, 10, 23, 255) panel color is gone;
  - a second build creates no duplicate UI or backdrop component.
- **Scene idempotence.** Assets/Scenes/DoorPrototype.unity is excluded from byte comparison because Unity regenerates its local fileIDs, as in NSC-077 VAL-007. Content is proven by the builder tests.
- **Vincent's review (VAL-003).** Vincent opens the scene in Play Mode and confirms:
  - the title reads over the live chase with no solid panel;
  - all three sayings are present;
  - the chunky Start Game button is on the left;
  - pairings cycle through all 4 mages and both enemies;
  - starting the game clears the chase and moves to wizard selection.

## T5. Dependencies
Add NSC-077 (enemy walk controllers and EnemyAnimationController) and NSC-075 (wizard walk animation and controller). Keep the existing relationship to NSC-067/NSC-068: selection and entry stay theirs.

## T6. Unchanged
No account, save, settings, credits, networking or runtime AI features. The GDD's first screen and transition remain the scope. The chase is presentation only.
