using System.IO;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.Events;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.World
{
    // NSC-069 AC-005: extracted from DoorPrototypeSceneBuilder so that class can stay the public
    // menu/test facade while this class owns building and clearing the global camera, lighting,
    // Player, UI, and input systems the prototype scene needs regardless of which room content it
    // currently displays.
    internal static class DoorPrototypeGlobalSceneBuilder
    {
        private const string InputActionsAssetPath = "Assets/InputSystem_Actions.inputactions";

        private const string WizardSourceRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab";
        private const string WizardGeneratedRoot = "Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated";
        private const string WizardCanonicalInitialDirection = "south-east";

        private static readonly string[] WizardVariants =
        {
            "Masculine_White",
            "Masculine_Black",
            "Feminine_White",
            "Feminine_Black"
        };

        private static readonly string[] WizardDirections =
        {
            "north",
            "north-east",
            "east",
            "south-east",
            "south",
            "south-west",
            "west",
            "north-west"
        };

        private static readonly string[] WizardStandingDirections = WizardDirections;

        private static readonly WizardSelectionDefinition[] WizardSelectionDefinitions =
        {
            new WizardSelectionDefinition(
                WizardPresentation.Masculine,
                WizardSkin.White,
                "masculine-light",
                "Ember Wizard"),
            new WizardSelectionDefinition(
                WizardPresentation.Masculine,
                WizardSkin.Black,
                "masculine-dark",
                "Ash Wizard"),
            new WizardSelectionDefinition(
                WizardPresentation.Feminine,
                WizardSkin.White,
                "feminine-light",
                "Frost Wizard"),
            new WizardSelectionDefinition(
                WizardPresentation.Feminine,
                WizardSkin.Black,
                "feminine-dark",
                "Dusk Wizard")
        };

        // Placeholder color only (GDD: placeholder character sprites are acceptable).
        // The world size the PLACEHOLDER silhouette is stretched to. It is 1 x 2 because
        // CreateWizardSilhouettePixels draws on a SQUARE texture, so the humanoid proportion
        // has to come from the transform. Named here because the real-sprite path below has
        // to undo exactly this and must not carry a second copy of the number.
        private static readonly Vector2 PlaceholderWizardWorldSize = new Vector2(1f, 2f);

        private static readonly Color32 WizardSpriteFillColor = new Color32(88, 64, 145, 255);
        private static readonly Color32 WizardSpriteBorderColor = new Color32(40, 28, 66, 255);
        private static readonly Color32 EnemySpriteFillColor = new Color32(168, 46, 46, 255);
        private static readonly Color32 EnemySpriteBorderColor = new Color32(72, 18, 18, 255);

        // Single owned root for every authored enemy, so one entry in the scene builder's clear
        // list removes the whole squad instead of leaving copies behind on each rebuild.
        internal const string EnemiesRootName = "Enemies";

        // Classic 2:1 dimetric isometric camera angle (rotate -45 degrees around Y to face
        // a corner, then tilt 30 degrees down) matching Diablo 1 / Ultima Online-style
        // fixed isometric presentation.
        internal static readonly Vector3 IsometricCameraEulerAngles =
            new Vector3(30f, -45f, 0f);

        // Fixed, hand-picked world-space offset from the follow target to the camera. This is
        // a plain constant - NOT derived by rotating a local vector through the camera's own
        // rotation - so the camera's framing is decoupled from its orientation.
        private static readonly Vector3 IsometricCameraOffset = new Vector3(10f, 10f, -10f);

        private const float IsometricOrthographicSize = 8f;

        // Unity Isometric Z-as-Y Individual Tilemap sorting axis. X intentionally contributes no
        // depth so moving along a horizontal wall cannot flip occlusion.
        // Unity draws the LARGER custom-axis dot product first (farther back). This camera sits
        // at -Z looking toward +Z, so a larger world Z is genuinely farther and must produce the
        // larger value: the Z coefficient is positive. A negative coefficient inverted depth and
        // rendered a door in front of a wizard standing south of it. Sourced from
        // IsometricCameraFollow.IsometricTransparencySortAxis, which reapplies the same value on
        // every scene load/Play Mode enable, so the two can never drift apart again.

        // Every root this class owns and clears before rebuilding, split out from the
        // environment-owned roots DoorPrototypeSceneBuilder clears itself (AC-005: explicit
        // builder-owned generated roots instead of one shared, implicit clearing list).
        internal static readonly string[] OwnedRootNames =
        {
            "Directional Light",
            "Main Camera",
            "Player",
            "PlayerSpawn",
            "Canvas",
            "EventSystem"
        };

        internal static void ClearOwnedRoots(Scene scene)
        {
            foreach (var root in scene.GetRootGameObjects())
            {
                if (System.Array.IndexOf(OwnedRootNames, root.name) >= 0)
                {
                    Object.DestroyImmediate(root);
                }
            }
        }

        internal static void BuildLighting()
        {
            var light = new GameObject("Directional Light");
            var lightComponent = light.AddComponent<Light>();
            lightComponent.type = LightType.Directional;
            lightComponent.intensity = 1f;
            light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }

        // Fixed 2.5D isometric presentation per the GDD (Diablo 1 / Ultima Online-style):
        // orthographic projection, no free rotation, at the classic 30/45 dimetric angle
        // used by Unity's isometric ("Z as Y") authoring conventions. The camera's position
        // is the follow target plus a fixed, hand-picked world-space offset - it is
        // deliberately NOT computed by rotating a local vector through the camera's own
        // rotation, since that couples the position to the rotation and produces a camera
        // whose forward axis always points exactly at the target regardless of whether that
        // actually frames the gameplay space well. An IsometricCameraFollow component then
        // translates the camera by that same fixed offset every frame while its rotation is
        // never touched again, so the fixed isometric orientation is preserved and the
        // gameplay area (including the starting door) stays in view as the player moves.
        internal static void BuildCamera(Transform followTarget)
        {
            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            var camera = cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();

            camera.orthographic = true;
            camera.orthographicSize = IsometricOrthographicSize;

            // NSC-039 AC-001: makes the established isometric sorting convention an explicit,
            // intentional part of the fixed camera setup rather than an unstated implicit
            // default. With an orthographic camera this already sorts transparent renderers
            // that share a sortingLayer/sortingOrder (world-space SpriteRenderer prefabs and
            // the Isometric Tilemap layers) by distance along the camera's fixed view
            // direction, so world sprites at different isometric positions order correctly
            // relative to one another without any per-object runtime sorting script.
            camera.transparencySortMode = TransparencySortMode.CustomAxis;
            camera.transparencySortAxis = IsometricCameraFollow.IsometricTransparencySortAxis;

            cameraObject.transform.rotation = Quaternion.Euler(IsometricCameraEulerAngles);

            if (followTarget == null)
            {
                Debug.LogWarning("DoorPrototypeGlobalSceneBuilder.BuildCamera called with a null follow target; " +
                    "the camera will be placed at the world origin plus its isometric offset instead of " +
                    "framing the player, which will fail the fixed isometric framing requirement.");
            }

            var targetPosition = followTarget != null ? followTarget.position : Vector3.zero;
            cameraObject.transform.position = targetPosition + IsometricCameraOffset;

            var follow = cameraObject.AddComponent<IsometricCameraFollow>();
            follow.Initialize(followTarget);
        }

        private static Color32[] CreateWizardSilhouettePixels(int width, int height, Color32 fill, Color32 border)
        {
            var pixels = new Color32[width * height];
            var transparent = new Color32(0, 0, 0, 0);

            var headCenterX = width * 0.5f;
            var headCenterY = height * 0.78f;
            var headRadius = width * 0.16f;
            const float headBorderThicknessPx = 1.5f;

            var robeTopY = height * 0.62f;
            var robeBottomY = height * 0.04f;
            var robeTopHalfWidth = width * 0.14f;
            var robeBottomHalfWidth = width * 0.32f;
            const float robeBorderThicknessPx = 1.5f;

            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var pixelCenterX = x + 0.5f;
                    var pixelCenterY = y + 0.5f;

                    var headOffsetX = pixelCenterX - headCenterX;
                    var headOffsetY = pixelCenterY - headCenterY;
                    var headDistance = Mathf.Sqrt(headOffsetX * headOffsetX + headOffsetY * headOffsetY);
                    var inHead = headDistance <= headRadius;
                    var onHeadBorder = inHead && headDistance >= headRadius - headBorderThicknessPx;

                    var inRobe = false;
                    var onRobeBorder = false;
                    if (pixelCenterY <= robeTopY && pixelCenterY >= robeBottomY)
                    {
                        var robeHeightFraction = (robeTopY - pixelCenterY) / (robeTopY - robeBottomY);
                        var robeHalfWidth = Mathf.Lerp(robeTopHalfWidth, robeBottomHalfWidth, robeHeightFraction);
                        var robeOffsetX = Mathf.Abs(pixelCenterX - headCenterX);
                        inRobe = robeOffsetX <= robeHalfWidth;
                        onRobeBorder = inRobe && robeOffsetX >= robeHalfWidth - robeBorderThicknessPx;
                    }

                    pixels[y * width + x] = inHead || inRobe
                        ? (onHeadBorder || onRobeBorder ? border : fill)
                        : transparent;
                }
            }

            return pixels;
        }

        internal static void BuildPlayer(
            out PlayerMovement movement,
            out PlayerInteractionController interactionController,
            out PlayerHealth health,
            out DebugDamageControl debugControl,
            out PlayerMana mana,
            out DebugManaSpendControl debugManaControl,
            out WizardAnimationController wizardAnimationController,
            out Transform playerSpawn,
            string architecturalTileAssetFolder)
        {
            var player = new GameObject("Player");

            // AC-003: NSC-044 records the Ruined Entry start point authoritatively in
            // RuinedEntryLayout; this facade reads it from there instead of re-authoring its own copy.
            player.transform.position = PlayerSpawnPosition;

            var characterController = player.AddComponent<CharacterController>();
            characterController.center = new Vector3(0f, 1f, 0f);
            characterController.height = 2f;
            characterController.radius = 0.5f;

            // CharacterController collision keeps the capsule approximately one skinWidth
            // above the collision surface. Spawn at that already-grounded root height so
            // Play Mode does not begin with the wizard visibly falling onto the floor.
            player.transform.position = new Vector3(
                PlayerSpawnPosition.x,
                characterController.skinWidth,
                PlayerSpawnPosition.z);

            // Placeholder wizard sprite (GDD: placeholder character sprites are acceptable),
            // instantiated from the same reusable world-space SpriteRenderer prefab as the
            // door. Already at the ground-contact convention's neutral local position, so the
            // sprite's feet sit exactly at the player's own transform position. The hierarchy
            // child keeps the existing "Visual" name other code/tests depend on, while
            // "WizardSprite" is the persistent asset identity so a future enemy/prop that also
            // names its child "Visual" cannot silently reuse the wizard's sprite asset.
            SpriteRenderer playerVisual = DoorPrototypeSceneBuilder.CreateWorldSpriteVisual(
                "Visual",
                "WizardSprite",
                player.transform,
                Vector3.zero,
                Quaternion.identity,
                PlaceholderWizardWorldSize,
                CreateWizardSilhouettePixels(
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    WizardSpriteFillColor,
                    WizardSpriteBorderColor),
                architecturalTileAssetFolder);

            // The CharacterController root intentionally rides one skinWidth above the floor,
            // but transparent sorting must use the wizard's actual floor-contact point. If the
            // renderer inherits that clearance, the Y component of the isometric custom axis
            // biases it behind a doorway until the wizard has moved too far through the door.
            // Keep the controller settled while anchoring the SpriteRenderer itself to y = 0.
            playerVisual.transform.localPosition = Vector3.down * characterController.skinWidth;

            WizardAnimationAssets wizardAssets = string.IsNullOrEmpty(architecturalTileAssetFolder)
                ? LoadWizardAnimationAssets()
                : BuildWizardAnimationAssets();
            var animator = player.AddComponent<Animator>();
            animator.runtimeAnimatorController = wizardAssets.controller;
            wizardAnimationController = player.AddComponent<WizardAnimationController>();
            SetPrivateField(wizardAnimationController, "animator", animator);
            SetPrivateFieldValue(wizardAnimationController, "presentation", WizardPresentation.Masculine);
            SetPrivateFieldValue(wizardAnimationController, "skin", WizardSkin.White);
            if (wizardAssets.defaultIdle != null)
            {
                player.transform.Find("Visual").GetComponent<SpriteRenderer>().sprite = wizardAssets.defaultIdle;

                // Vincent, 2026-09-25: "it has its scale wrong... a scale on the y but not on the x".
                // PlaceholderWizardWorldSize is a correction for the placeholder's SQUARE texture,
                // and the real PixelLab frames are square too - 180x180 at PPU 180 is exactly
                // 1 x 1 world units, with the drawn figure padded inside it (58x146 for
                // masculine-light, 65x153 for feminine-dark). So the 1:2 was being applied to
                // artwork that already carries its own proportion, stretching it vertically.
                // Scale UNIFORMLY to the same world height the placeholder targeted: the aspect is
                // corrected and the wizard's rendered height does not change, so nothing that was
                // tuned against his height moves. Derived from the sprite rather than written as a
                // literal so a pixels-per-unit change cannot silently reintroduce the stretch.
                float wizardScale =
                    PlaceholderWizardWorldSize.y / wizardAssets.defaultIdle.bounds.size.y;
                playerVisual.transform.localScale = new Vector3(wizardScale, wizardScale, 1f);
            }

            health = player.AddComponent<PlayerHealth>();
            interactionController = player.AddComponent<PlayerInteractionController>();
            movement = player.AddComponent<PlayerMovement>();
            debugControl = player.AddComponent<DebugDamageControl>();
            mana = player.AddComponent<PlayerMana>();
            debugManaControl = player.AddComponent<DebugManaSpendControl>();

            SetPrivateField(interactionController, "playerHealth", health);
            SetPrivateField(debugControl, "target", health);
            SetPrivateField(debugManaControl, "target", mana);
            SetPrivateField(movement, "interactionController", interactionController);

            InputActionAsset inputActions = AssetDatabase.LoadAssetAtPath<InputActionAsset>(InputActionsAssetPath);
            if (inputActions == null)
            {
                Debug.LogWarning($"DoorPrototypeGlobalSceneBuilder could not load an InputActionAsset at " +
                    $"'{InputActionsAssetPath}'; PlayerMovement will have no input actions asset assigned.");
            }
            SetPrivateField(movement, "inputActions", inputActions);
            playerSpawn = BuildPlayerSpawn(movement.transform).transform;
        }

        // Places one melee enemy that acquires the wizard through EnemyTargetKnowledge, pursues
        // across the already-baked gameplay NavMesh, and can be escaped by crossing a door. The
        // visual reuses the same world-space SpriteRenderer prefab as the wizard and door so
        // transparent sorting stays consistent with everything else in the scene. Must run after
        // BuildGameplayNavigation has baked, or the agent has no surface to path on.
        //
        // 2026-09-25: the two Bone Archive spawns moved because NSC-045's widened blockout landed.
        // They were authored against the PRE-WIDENING room and both fell inside new geometry: the
        // melee at X 2.0 reached ShelfC, which moved from X[3.5,5.0] to X[2.5,4.0], and the wraith
        // at (9,13) sat INSIDE East Archive Bay E-1 at X[7.0,11.75] Z[5.5,13.5], which did not
        // exist at all. Melee is now centred in the BA-1-to-ShelfC lane, 1.75 from the D1-D2
        // midpoint (3,10) and inside AC-005's 4-unit rule, and the wraith moved north of E-1,
        // still east of the D1-D2 line and now 9.8 units from the melee against AC-005's 6.
        //
        // AC-005 (contract revision 8): repositioned to the 2026-09-15 approved room bounds -
        // BoneArchive X[-12,12] Z[0,20] D1(0,0)/D2(6,20); ChapelOfAsh X[-18,18] Z[20,54]
        // D2(6,20)/D3(-8,54); LowerVault X[-20,20] Z[54,76] D3(-8,54)/D4(4,76); FinalRoom
        // X[-15,15] Z[76,104] D4(4,76)/D5(0,104) - per the AC-005 oracles: each single-melee
        // room's spawn sits within 4 units of its room's own entry/exit door-line midpoint, and
        // Final Room's two melee spawns flank FR-1 (X[-3.5,3.5] Z[87,94]) on opposite sides of
        // the D4-D5 line while staying within 6 units of that line's midpoint (2,90). RuinedEntry
        // is deliberately left empty; the wizard spawns there instead.
        private static readonly Vector3[] EnemySpawnPositions =
        {
            new Vector3(1.25f, 0f, 10f),// BoneArchive: 1.75 from the D1-D2 midpoint (3,10), centred in the BA-1-to-ShelfC lane
            new Vector3(-2f, 0f, 36f),  // ChapelOfAsh: ~1.4 units from the D2-D3 midpoint (-1,37)
            // LowerVault: 2.51 from the D3-D4 midpoint (-2,65), on the room's FLAT floor.
            // AC-006 needs NavMesh.SamplePosition to succeed within 0.1 of the authored y=0, and
            // the old (-2,0,66) measured 0.129 away - purely vertical, same X and Z. NSC-047
            // AC-002 specifies LV-H1 as 0.5-unit-high spans and the project agent's climb is
            // 0.75, so those spans are CLIMBABLE: the bake rides up onto them (0.51-0.58 measured
            // on top) and ramps the floor around them to 0.10-0.19, where Chapel of Ash reads a
            // flat 0.083 across its whole room. This point measures 0.0833 - the same height as
            // every other room's floor - so it passes on flat ground rather than by a hundredth.
            new Vector3(-4.5f, 0f, 64.75f),
            new Vector3(-2f, 0f, 86f),  // FinalRoom west flank of FR-1, ~5.7 from midpoint (2,90)
            new Vector3(4f, 0f, 95f),   // FinalRoom east flank of FR-1, opposite side of D4-D5 line
        };

        // Half a room, so a leashed enemy never reaches either of its room's doorways.
        private const float EnemyPursuitLeashDistance = 5f;

        // AC-003: the start point NSC-044 records in RuinedEntryLayout, read here rather than
        // re-authored as a second copy of that value.
        private static readonly Vector3 PlayerSpawnPosition = RuinedEntryLayout.PlayerStart;

        // AC-005: stationary Lantern Wraiths, repositioned alongside EnemySpawnPositions above to
        // the same 2026-09-15 approved room bounds. Each sits on the opposite side of its room's
        // door line from that room's melee spawn, at least 6 units clear of it, with a Linecast
        // sight line to at least one of that room's two door approach points.
        private static readonly Vector3[] LanternWraithSpawnPositions =
        {
            new Vector3(9f, 0f, 16f),   // BoneArchive, opposite side from melee (1.25,10), north of E-1; sees D2
            new Vector3(0f, 0f, 45f),   // ChapelOfAsh, opposite side from melee (-2,36); sees D3
            // LowerVault, opposite side of the D3-D4 line from its melee partner, 10.9 units
            // clear of it, with a Linecast sight line to the D4 approach (4,74.5) that passes
            // OVER the 0.5-high LV-H1 spans at the 1.0 test height. The old (4,0,73) measured
            // 0.123 off the navmesh for the same LV-H1 ramp described above.
            //
            // It moved SOUTH rather than staying beside D4, and that is a real change to the
            // encounter: among all 521 AC-006-legal partners, every point that still covers D4
            // from the north band measures ~0.098 against a 0.1 gate - a pass by 0.002 that the
            // next rebake could flip. The southern flat band is the only place a robust legal
            // partner exists while LV-H1 ramps this room. Worth revisiting if LV-H1 is ever made
            // unclimbable, which would also restore its stated job as a walking boundary.
            new Vector3(2f, 0f, 56f),
            new Vector3(10f, 0f, 80f),  // FinalRoom, within 12 units of D4 (4,76); sees D4
        };

        internal static void BuildChaseEnemies(Transform player, string architecturalTileAssetFolder)
        {
            var enemiesRoot = new GameObject(EnemiesRootName);
            EnemyAnimationAssetBuilder.EnemyAnimationAssets animationAssets =
                string.IsNullOrEmpty(architecturalTileAssetFolder)
                    ? EnemyAnimationAssetBuilder.Load()
                    : EnemyAnimationAssetBuilder.Build();

            if (!string.IsNullOrEmpty(architecturalTileAssetFolder))
            {
                AssetDatabase.DeleteAsset(
                    architecturalTileAssetFolder + "/FireCasterEnemySprite.asset");
            }

            foreach (Vector3 spawnPosition in EnemySpawnPositions)
            {
                BuildChaseEnemy(
                    player,
                    architecturalTileAssetFolder,
                    enemiesRoot.transform,
                    spawnPosition,
                    animationAssets);
            }

            foreach (Vector3 spawnPosition in LanternWraithSpawnPositions)
            {
                BuildLanternWraith(
                    player,
                    architecturalTileAssetFolder,
                    enemiesRoot.transform,
                    spawnPosition,
                    animationAssets);
            }
        }

        // The Lantern Wraith holds its ground and casts until its mana runs out. No NavMeshAgent
        // or pursuit components: it owns its range and sight
        // tests directly, so it needs nothing from the navigation surface.
        private static void BuildLanternWraith(
            Transform player,
            string architecturalTileAssetFolder,
            Transform enemiesRoot,
            Vector3 spawnPosition,
            EnemyAnimationAssetBuilder.EnemyAnimationAssets animationAssets)
        {
            var wraith = new GameObject("LanternWraith");
            wraith.transform.SetParent(enemiesRoot, false);
            wraith.transform.position = spawnPosition;

            SpriteRenderer visual = DoorPrototypeSceneBuilder.CreateWorldSpriteVisual(
                "Visual",
                "LanternWraithSprite",
                wraith.transform,
                Vector3.zero,
                Quaternion.Euler(IsometricCameraEulerAngles),
                Vector2.one,
                CreateWizardSilhouettePixels(
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    EnemySpriteFillColor,
                    EnemySpriteBorderColor),
                architecturalTileAssetFolder);
            visual.sprite = animationAssets.WraithSouthIdle;

            EnemyLanternWispCaster caster = wraith.AddComponent<EnemyLanternWispCaster>();
            caster.Initialize(player);

            // EnemyHealth keeps the stationary enemy in the existing damage and defeat flow.
            wraith.AddComponent<EnemyHealth>();

            Animator animator = wraith.AddComponent<Animator>();
            animator.runtimeAnimatorController = animationAssets.WraithController;
            EnemyAnimationController animation = wraith.AddComponent<EnemyAnimationController>();
            animation.Initialize(animator, EnemyAnimationKind.LanternWraith);
        }

        private static void BuildChaseEnemy(
            Transform player,
            string architecturalTileAssetFolder,
            Transform enemiesRoot,
            Vector3 spawnPosition,
            EnemyAnimationAssetBuilder.EnemyAnimationAssets animationAssets)
        {
            var enemy = new GameObject("MeleeEnemy");
            enemy.transform.SetParent(enemiesRoot, false);
            enemy.transform.position = spawnPosition;

            // Match the agent to the project-configured type the surface was baked with; a
            // mismatched radius/height silently refuses to produce a complete path.
            var agent = enemy.AddComponent<NavMeshAgent>();
            NavMeshBuildSettings navigationSettings = NavMesh.GetSettingsByIndex(0);
            agent.agentTypeID = navigationSettings.agentTypeID;
            agent.radius = navigationSettings.agentRadius;
            agent.height = navigationSettings.agentHeight;
            agent.speed = 2.2f;
            agent.acceleration = 12f;
            agent.angularSpeed = 720f;
            agent.stoppingDistance = 0.6f;
            agent.autoBraking = true;

            SpriteRenderer visual = DoorPrototypeSceneBuilder.CreateWorldSpriteVisual(
                "Visual",
                "MeleeEnemySprite",
                enemy.transform,
                Vector3.zero,
                Quaternion.Euler(IsometricCameraEulerAngles),
                Vector2.one,
                CreateWizardSilhouettePixels(
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    EnemySpriteFillColor,
                    EnemySpriteBorderColor),
                architecturalTileAssetFolder);
            visual.sprite = animationAssets.MeleeSouthIdle;

            // EnemyPursuitMovement and EnemyLockedDoorAttack both resolve their collaborators
            // through GetComponent in Awake, so only the wizard Transform needs injecting here.
            EnemyTargetKnowledge targetKnowledge = enemy.AddComponent<EnemyTargetKnowledge>();
            targetKnowledge.Initialize(player);

            // Authored enemies only: a closed door's doorwayBlocker or a wall must hide the
            // wizard. Component tests construct EnemyTargetKnowledge directly and keep the
            // distance-only acquisition contract, which defaults this off.
            targetKnowledge.SetRequiresLineOfSight(true);

            // Each room is 20-26 units deep with a door at either boundary, so a 5-unit leash
            // around a mid-room post keeps every enemy at least ~5 units clear of both doors.
            // Without it, pursuit converges on the doorway and the wizard opens a door into an
            // enemy already standing in it.
            targetKnowledge.SetMaximumPursuitDistanceFromStart(EnemyPursuitLeashDistance);

            enemy.AddComponent<EnemyPursuitMovement>();
            enemy.AddComponent<EnemyHealth>();

            Animator animator = enemy.AddComponent<Animator>();
            animator.runtimeAnimatorController = animationAssets.MeleeController;
            EnemyAnimationController animation = enemy.AddComponent<EnemyAnimationController>();
            animation.Initialize(animator, EnemyAnimationKind.MeleeEnemy);
        }

        private static GameObject BuildPlayerSpawn(Transform player)
        {
            var playerSpawn = new GameObject("PlayerSpawn");
            playerSpawn.transform.SetPositionAndRotation(player.position, player.rotation);
            return playerSpawn;
        }

        private readonly struct WizardAnimationAssets
        {
            public readonly RuntimeAnimatorController controller;
            public readonly Sprite defaultIdle;

            public WizardAnimationAssets(RuntimeAnimatorController controller, Sprite defaultIdle)
            {
                this.controller = controller;
                this.defaultIdle = defaultIdle;
            }
        }

        private static WizardAnimationAssets BuildWizardAnimationAssets()
        {
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art");
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art/Wizard");
            EnsureFolder(WizardGeneratedRoot);
            var controllerPath = WizardGeneratedRoot + "/WizardAnimator.controller";
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            if (controller == null) controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);

            var stateMachine = controller.layers[0].stateMachine;
            Sprite defaultIdle = null;
            foreach (var variant in WizardVariants)
            {
                var sourceVariant = variant.Replace("_White", "-light").Replace("_Black", "-dark")
                    .Replace("Masculine", "masculine").Replace("Feminine", "feminine");
                foreach (var standingDirection in WizardStandingDirections)
                {
                    ImportWizardSprite(WizardSourceRoot + "/" + sourceVariant + "/selected/standing/" + standingDirection + ".png");
                }
                foreach (var direction in WizardDirections)
                {
                    var standingPath = WizardSourceRoot + "/" + sourceVariant + "/selected/standing/" + direction + ".png";
                    var idle = ImportWizardSprite(standingPath);
                    var idleName = "Wizard_" + variant + "_idle_" + direction;
                    EnsureWizardState(stateMachine, idleName, EnsureWizardClip(idleName, new[] { idle }, 1));
                    if (variant == "Masculine_White" && direction == WizardCanonicalInitialDirection)
                        defaultIdle = idle;

                    var walk = new Sprite[6];
                    for (var frame = 0; frame < walk.Length; frame++)
                    {
                        var walkPath = WizardSourceRoot + "/" + sourceVariant + "/selected/walk/" + direction + "/frame_00" + frame + ".png";
                        walk[frame] = ImportWizardSprite(walkPath);
                    }
                    var walkName = "Wizard_" + variant + "_walk_" + direction;
                    EnsureWizardState(stateMachine, walkName, EnsureWizardClip(walkName, walk, 12));
                }
            }
            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssetIfDirty(controller);
            return new WizardAnimationAssets(controller, defaultIdle);
        }

        private static WizardAnimationAssets LoadWizardAnimationAssets()
        {
            var controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(
                WizardGeneratedRoot + "/WizardAnimator.controller");
            var defaultIdle = AssetDatabase.LoadAssetAtPath<Sprite>(
                WizardSourceRoot + "/masculine-light/selected/standing/south-east.png");
            return new WizardAnimationAssets(controller, defaultIdle);
        }

        private static Sprite ImportWizardSprite(string path)
        {
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) throw new FileNotFoundException("Wizard source is not a texture", path);
            importer.textureType = TextureImporterType.Sprite;
            importer.textureShape = TextureImporterShape.Texture2D;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.spritePixelsPerUnit = 180f;
            var textureSettings = new TextureImporterSettings();
            importer.ReadTextureSettings(textureSettings);
            textureSettings.spriteAlignment = (int)SpriteAlignment.Custom;
            textureSettings.spritePivot = new Vector2(0.5f, 0f);
            importer.SetTextureSettings(textureSettings);
            ClearCookieImportDefaults(importer);
            importer.SaveAndReimport();
            var sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null) throw new InvalidDataException("Wizard source did not import as a Sprite: " + path);
            return sprite;
        }

        // A GUID-only .meta imports with point-light cookie defaults; reset them to match every other wizard source.
        private static void ClearCookieImportDefaults(TextureImporter importer)
        {
            var serializedImporter = new SerializedObject(importer);
            foreach (var propertyName in new[] { "m_ApplyGammaDecoding", "m_CookieLightType" })
            {
                var property = serializedImporter.FindProperty(propertyName);
                if (property == null) throw new InvalidDataException("TextureImporter has no serialized property " + propertyName);
                if (property.propertyType == SerializedPropertyType.Boolean) property.boolValue = false;
                else property.intValue = 0;
            }

            serializedImporter.ApplyModifiedPropertiesWithoutUndo();
        }

        private static AnimationClip EnsureWizardClip(string name, Sprite[] sprites, int frameRate)
        {
            var path = WizardGeneratedRoot + "/" + name + ".anim";
            var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null)
            {
                clip = new AnimationClip { name = name };
                AssetDatabase.CreateAsset(clip, path);
            }
            clip.frameRate = frameRate;
            var keys = new ObjectReferenceKeyframe[sprites.Length];
            for (var i = 0; i < sprites.Length; i++)
                keys[i] = new ObjectReferenceKeyframe { time = i / (float)frameRate, value = sprites[i] };
            AnimationUtility.SetObjectReferenceCurve(clip,
                EditorCurveBinding.PPtrCurve("", typeof(SpriteRenderer), "m_Sprite"), null);
            AnimationUtility.SetObjectReferenceCurve(clip,
                EditorCurveBinding.PPtrCurve("Visual", typeof(SpriteRenderer), "m_Sprite"), keys);
            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = true;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            EditorUtility.SetDirty(clip);
            AssetDatabase.SaveAssetIfDirty(clip);
            return clip;
        }

        private static void EnsureWizardState(AnimatorStateMachine stateMachine, string name, AnimationClip clip)
        {
            foreach (var child in stateMachine.states)
            {
                if (child.state.name != name) continue;
                child.state.motion = clip;
                return;
            }
            stateMachine.AddState(name).motion = clip;
        }

        internal static void BuildUI(DoorInteractable door, DebugDamageControl debugControl,
            PlayerHealth health, PlayerMana mana, DebugManaSpendControl debugManaControl,
            PlayerMovement movement, PlayerInteractionController interactionController,
            WizardAnimationController wizardAnimationController, Transform playerSpawn)
        {
            var canvasObject = new GameObject("Canvas");
            var canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var canvasScaler = canvasObject.AddComponent<CanvasScaler>();
            canvasScaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            canvasScaler.referenceResolution = new Vector2(1920f, 1080f);
            canvasScaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            canvasScaler.matchWidthOrHeight = 0.5f;
            canvasObject.AddComponent<GraphicRaycaster>();

            var eventSystemObject = new GameObject("EventSystem");
            eventSystemObject.AddComponent<EventSystem>();
            eventSystemObject.AddComponent<InputSystemUIInputModule>();

            var promptRoot = new GameObject("InteractPrompt");
            promptRoot.transform.SetParent(canvasObject.transform, false);
            var promptRect = promptRoot.AddComponent<RectTransform>();
            promptRect.anchorMin = new Vector2(0.5f, 0.2f);
            promptRect.anchorMax = new Vector2(0.5f, 0.2f);
            promptRect.sizeDelta = new Vector2(400f, 40f);
            var promptText = promptRoot.AddComponent<Text>();
            promptText.text = "Sealed Door - Click to Open";
            promptText.alignment = TextAnchor.MiddleCenter;
            promptText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            promptText.color = Color.white;

            var progressObject = new GameObject("ProgressFill");
            progressObject.transform.SetParent(canvasObject.transform, false);
            var progressRect = progressObject.AddComponent<RectTransform>();
            progressRect.anchorMin = new Vector2(0.5f, 0.12f);
            progressRect.anchorMax = new Vector2(0.5f, 0.12f);
            progressRect.sizeDelta = new Vector2(300f, 20f);
            var progressBackgroundImage = progressObject.AddComponent<Image>();
            progressBackgroundImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            progressBackgroundImage.type = Image.Type.Sliced;
            progressBackgroundImage.color = new Color(0.15f, 0.15f, 0.15f, 0.85f);

            var progressFillObject = new GameObject("Fill");
            progressFillObject.transform.SetParent(progressObject.transform, false);
            var progressFillRect = progressFillObject.AddComponent<RectTransform>();
            progressFillRect.anchorMin = Vector2.zero;
            progressFillRect.anchorMax = Vector2.one;
            progressFillRect.offsetMin = Vector2.zero;
            progressFillRect.offsetMax = Vector2.zero;
            var progressFill = progressFillObject.AddComponent<Image>();
            // A Filled Image with no sprite bypasses fill geometry and always renders as a full
            // solid rect, so fillAmount visibly does nothing without a sprite assigned here.
            progressFill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            progressFill.type = Image.Type.Filled;
            progressFill.fillMethod = Image.FillMethod.Horizontal;
            progressFill.fillOrigin = (int)Image.OriginHorizontal.Left;
            progressFill.fillAmount = 0f;
            progressFill.color = Color.green;

            var uiBinding = canvasObject.AddComponent<DoorInteractionUI>();
            SetPrivateField(uiBinding, "interactionController", interactionController);
            SetPrivateField(uiBinding, "door", door);
            SetPrivateField(uiBinding, "promptRoot", promptRoot);
            SetPrivateField(uiBinding, "progressFillImage", progressFill);

            var buttonObject = new GameObject("DebugDamageButton");
            buttonObject.transform.SetParent(canvasObject.transform, false);
            var buttonRect = buttonObject.AddComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0.02f, 0.02f);
            buttonRect.anchorMax = new Vector2(0.02f, 0.02f);
            buttonRect.pivot = Vector2.zero;
            buttonRect.sizeDelta = new Vector2(260f, 40f);
            var buttonImage = buttonObject.AddComponent<Image>();
            buttonImage.color = new Color(0.6f, 0.1f, 0.1f);
            var damageButton = buttonObject.AddComponent<Button>();
            damageButton.targetGraphic = buttonImage;

            var buttonTextObject = new GameObject("Text");
            buttonTextObject.transform.SetParent(buttonObject.transform, false);
            var buttonTextRect = buttonTextObject.AddComponent<RectTransform>();
            buttonTextRect.anchorMin = Vector2.zero;
            buttonTextRect.anchorMax = Vector2.one;
            buttonTextRect.sizeDelta = Vector2.zero;
            var buttonText = buttonTextObject.AddComponent<Text>();
            buttonText.text = "DEBUG: Take Damage (K)";
            buttonText.alignment = TextAnchor.MiddleCenter;
            buttonText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            buttonText.color = Color.white;
            buttonText.fontSize = 14;

            UnityEventTools.AddPersistentListener(damageButton.onClick, debugControl.TriggerDebugDamage);

            BuildHealthUI(canvasObject, health);
            BuildManaUI(canvasObject, mana, debugManaControl);

            BuildControlsHud(canvasObject.transform);
            TitleScreenController titleScreenController = BuildTitleScreen(
                canvasObject,
                movement,
                interactionController,
                debugControl,
                debugManaControl,
                out GameObject titlePanel);
            WizardSelectionController wizardSelectionController = BuildWizardSelectionScreen(
                canvasObject,
                titleScreenController,
                out GameObject selectionPanel);
            BuildWizardGameEntry(
                canvasObject,
                wizardSelectionController,
                wizardAnimationController,
                movement,
                interactionController,
                playerSpawn,
                titlePanel,
                selectionPanel);
        }

        private static TitleScreenController BuildTitleScreen(GameObject canvasObject, PlayerMovement movement,
            PlayerInteractionController interactionController, DebugDamageControl debugControl,
            DebugManaSpendControl debugManaControl, out GameObject titlePanel)
        {
            titlePanel = new GameObject(
                "TitleScreen",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image));
            titlePanel.transform.SetParent(canvasObject.transform, false);

            var titlePanelRect = titlePanel.GetComponent<RectTransform>();
            titlePanelRect.anchorMin = Vector2.zero;
            titlePanelRect.anchorMax = Vector2.one;
            titlePanelRect.offsetMin = Vector2.zero;
            titlePanelRect.offsetMax = Vector2.zero;

            var titlePanelImage = titlePanel.GetComponent<Image>();
            titlePanelImage.color = new Color32(16, 10, 23, 255);
            titlePanelImage.raycastTarget = true;

            var card = new GameObject(
                "TitleCard",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image),
                typeof(Outline));
            card.transform.SetParent(titlePanel.transform, false);

            var cardRect = card.GetComponent<RectTransform>();
            cardRect.anchorMin = new Vector2(0.5f, 0.5f);
            cardRect.anchorMax = new Vector2(0.5f, 0.5f);
            cardRect.sizeDelta = new Vector2(900f, 590f);

            var cardImage = card.GetComponent<Image>();
            cardImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            cardImage.type = Image.Type.Sliced;
            cardImage.color = new Color32(43, 24, 50, 255);

            var cardOutline = card.GetComponent<Outline>();
            cardOutline.effectColor = new Color32(128, 70, 119, 255);
            cardOutline.effectDistance = new Vector2(3f, -3f);

            var accent = new GameObject("Accent", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            accent.transform.SetParent(card.transform, false);
            var accentRect = accent.GetComponent<RectTransform>();
            accentRect.anchorMin = new Vector2(0.5f, 1f);
            accentRect.anchorMax = new Vector2(0.5f, 1f);
            accentRect.pivot = new Vector2(0.5f, 1f);
            accentRect.anchoredPosition = new Vector2(0f, -34f);
            accentRect.sizeDelta = new Vector2(130f, 8f);
            accent.GetComponent<Image>().color = new Color32(232, 132, 165, 255);

            Text eyebrow = CreateTitleText(
                "Eyebrow",
                card.transform,
                new Vector2(0.12f, 0.78f),
                new Vector2(0.88f, 0.88f),
                "WELCOME, TINY WIZARD",
                24,
                new Color32(232, 132, 165, 255));
            eyebrow.fontStyle = FontStyle.Bold;

            Text title = CreateTitleText(
                "Title",
                card.transform,
                new Vector2(0.08f, 0.53f),
                new Vector2(0.92f, 0.78f),
                "NO SAFE CIRCLE",
                78,
                new Color32(255, 238, 224, 255));
            title.fontStyle = FontStyle.Bold;
            var titleShadow = title.gameObject.AddComponent<Shadow>();
            titleShadow.effectColor = new Color32(8, 4, 12, 220);
            titleShadow.effectDistance = new Vector2(5f, -5f);

            Text tagline = CreateTitleText(
                "Tagline",
                card.transform,
                new Vector2(0.15f, 0.39f),
                new Vector2(0.85f, 0.53f),
                "Cute wizards. Terrible odds.",
                28,
                new Color32(205, 185, 210, 255));
            tagline.fontStyle = FontStyle.Italic;

            var buttonObject = new GameObject(
                "StartGameButton",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image),
                typeof(Button),
                typeof(Shadow));
            buttonObject.transform.SetParent(card.transform, false);

            var buttonRect = buttonObject.GetComponent<RectTransform>();
            buttonRect.anchorMin = new Vector2(0.5f, 0.22f);
            buttonRect.anchorMax = new Vector2(0.5f, 0.22f);
            buttonRect.sizeDelta = new Vector2(380f, 82f);

            var buttonImage = buttonObject.GetComponent<Image>();
            buttonImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            buttonImage.type = Image.Type.Sliced;
            buttonImage.color = new Color32(152, 65, 119, 255);

            var startButton = buttonObject.GetComponent<Button>();
            startButton.targetGraphic = buttonImage;
            startButton.navigation = new UnityEngine.UI.Navigation { mode = UnityEngine.UI.Navigation.Mode.None };
            ColorBlock buttonColors = startButton.colors;
            buttonColors.normalColor = Color.white;
            buttonColors.highlightedColor = new Color32(255, 211, 225, 255);
            buttonColors.pressedColor = new Color32(205, 145, 178, 255);
            buttonColors.selectedColor = buttonColors.highlightedColor;
            buttonColors.disabledColor = new Color32(110, 85, 103, 160);
            buttonColors.fadeDuration = 0.08f;
            startButton.colors = buttonColors;

            var buttonShadow = buttonObject.GetComponent<Shadow>();
            buttonShadow.effectColor = new Color32(7, 3, 10, 210);
            buttonShadow.effectDistance = new Vector2(5f, -5f);

            Text buttonLabel = CreateTitleText(
                "Text",
                buttonObject.transform,
                Vector2.zero,
                Vector2.one,
                "START GAME",
                32,
                new Color32(255, 245, 229, 255));
            buttonLabel.fontStyle = FontStyle.Bold;

            CreateTitleText(
                "Footer",
                card.transform,
                new Vector2(0.14f, 0.05f),
                new Vector2(0.86f, 0.13f),
                "THE DARKNESS THINKS YOU LOOK SNACK-SIZED.",
                18,
                new Color32(159, 137, 164, 255));

            var controller = canvasObject.AddComponent<TitleScreenController>();
            SetPrivateField(controller, "titlePanel", titlePanel);
            SetPrivateField(controller, "startGameButton", startButton);
            SetPrivateField(controller, "playerMovement", movement);
            SetPrivateField(controller, "playerInteractionController", interactionController);
            SetPrivateObjectArray(controller, "gameplayInputBehaviours", debugControl, debugManaControl);

            UnityEventTools.AddPersistentListener(startButton.onClick, controller.StartGame);
            return controller;
        }

        private static WizardSelectionController BuildWizardSelectionScreen(
            GameObject canvasObject,
            TitleScreenController titleScreenController,
            out GameObject selectionPanel)
        {
            selectionPanel = new GameObject(
                "WizardSelectionScreen",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image));
            selectionPanel.transform.SetParent(canvasObject.transform, false);

            RectTransform panelRect = selectionPanel.GetComponent<RectTransform>();
            panelRect.anchorMin = Vector2.zero;
            panelRect.anchorMax = Vector2.one;
            panelRect.offsetMin = Vector2.zero;
            panelRect.offsetMax = Vector2.zero;

            Image panelImage = selectionPanel.GetComponent<Image>();
            panelImage.color = new Color32(16, 10, 23, 255);
            panelImage.raycastTarget = true;

            Text heading = CreateTitleText(
                "Heading",
                selectionPanel.transform,
                new Vector2(0.18f, 0.84f),
                new Vector2(0.82f, 0.96f),
                "CHOOSE YOUR WIZARD",
                52,
                new Color32(255, 238, 224, 255));
            heading.fontStyle = FontStyle.Bold;

            Text instruction = CreateTitleText(
                "Instruction",
                selectionPanel.transform,
                new Vector2(0.2f, 0.78f),
                new Vector2(0.8f, 0.85f),
                "Select one wizard to enter the darkness.",
                23,
                new Color32(205, 185, 210, 255));
            instruction.fontStyle = FontStyle.Italic;

            var builtOptions = new BuiltWizardSelectionOption[WizardSelectionDefinitions.Length];
            for (var index = 0; index < WizardSelectionDefinitions.Length; index++)
            {
                float x = index % 2 == 0 ? 0.32f : 0.68f;
                float y = index < 2 ? 0.62f : 0.34f;
                builtOptions[index] = BuildWizardSelectionOption(
                    selectionPanel.transform,
                    WizardSelectionDefinitions[index],
                    index,
                    new Vector2(x, y));
            }

            var confirmObject = new GameObject(
                "ConfirmSelectionButton",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image),
                typeof(Button),
                typeof(Shadow));
            confirmObject.transform.SetParent(selectionPanel.transform, false);

            RectTransform confirmRect = confirmObject.GetComponent<RectTransform>();
            confirmRect.anchorMin = new Vector2(0.5f, 0.105f);
            confirmRect.anchorMax = new Vector2(0.5f, 0.105f);
            confirmRect.sizeDelta = new Vector2(420f, 72f);

            Image confirmImage = confirmObject.GetComponent<Image>();
            confirmImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            confirmImage.type = Image.Type.Sliced;
            confirmImage.color = new Color32(152, 65, 119, 255);

            Button confirmButton = confirmObject.GetComponent<Button>();
            confirmButton.targetGraphic = confirmImage;
            confirmButton.interactable = false;
            confirmButton.navigation = new UnityEngine.UI.Navigation { mode = UnityEngine.UI.Navigation.Mode.None };
            ColorBlock confirmColors = confirmButton.colors;
            confirmColors.normalColor = Color.white;
            confirmColors.highlightedColor = new Color32(255, 211, 225, 255);
            confirmColors.pressedColor = new Color32(205, 145, 178, 255);
            confirmColors.selectedColor = confirmColors.highlightedColor;
            confirmColors.disabledColor = new Color32(90, 72, 88, 180);
            confirmButton.colors = confirmColors;

            Shadow confirmShadow = confirmObject.GetComponent<Shadow>();
            confirmShadow.effectColor = new Color32(7, 3, 10, 210);
            confirmShadow.effectDistance = new Vector2(5f, -5f);

            Text confirmLabel = CreateTitleText(
                "Text",
                confirmObject.transform,
                Vector2.zero,
                Vector2.one,
                "CONFIRM WIZARD",
                28,
                new Color32(255, 245, 229, 255));
            confirmLabel.fontStyle = FontStyle.Bold;

            WizardSelectionController controller = canvasObject.AddComponent<WizardSelectionController>();
            SetPrivateField(controller, "titleScreenController", titleScreenController);
            SetPrivateField(controller, "selectionPanel", selectionPanel);
            SetPrivateField(controller, "confirmButton", confirmButton);
            SetWizardSelectionOptions(controller, builtOptions);

            for (var index = 0; index < builtOptions.Length; index++)
            {
                UnityEventTools.AddIntPersistentListener(
                    builtOptions[index].button.onClick,
                    controller.SelectOption,
                    index);
            }

            UnityEventTools.AddPersistentListener(confirmButton.onClick, controller.ConfirmSelection);
            selectionPanel.SetActive(false);
            return controller;
        }

        private static void BuildWizardGameEntry(
            GameObject canvasObject,
            WizardSelectionController wizardSelectionController,
            WizardAnimationController wizardAnimationController,
            PlayerMovement movement,
            PlayerInteractionController interactionController,
            Transform playerSpawn,
            GameObject titlePanel,
            GameObject selectionPanel)
        {
            WizardGameEntryController controller = canvasObject.AddComponent<WizardGameEntryController>();
            SetPrivateField(controller, "wizardSelectionController", wizardSelectionController);
            SetPrivateField(controller, "wizardAnimationController", wizardAnimationController);
            SetPrivateField(controller, "player", movement.transform);
            SetPrivateField(controller, "worldSpawn", playerSpawn);
            SetPrivateField(controller, "playerMovement", movement);
            SetPrivateField(controller, "playerInteractionController", interactionController);
            SetPrivateObjectArray(controller, "menuUiRoots", titlePanel, selectionPanel);
        }

        private static BuiltWizardSelectionOption BuildWizardSelectionOption(
            Transform parent,
            WizardSelectionDefinition definition,
            int index,
            Vector2 anchor)
        {
            var optionObject = new GameObject(
                $"WizardOption{index + 1}",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image),
                typeof(Button),
                typeof(Outline));
            optionObject.transform.SetParent(parent, false);

            RectTransform optionRect = optionObject.GetComponent<RectTransform>();
            optionRect.anchorMin = anchor;
            optionRect.anchorMax = anchor;
            optionRect.sizeDelta = new Vector2(560f, 260f);

            Image optionImage = optionObject.GetComponent<Image>();
            optionImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            optionImage.type = Image.Type.Sliced;
            optionImage.color = new Color32(43, 24, 50, 255);

            Button optionButton = optionObject.GetComponent<Button>();
            optionButton.targetGraphic = optionImage;
            optionButton.navigation = new UnityEngine.UI.Navigation { mode = UnityEngine.UI.Navigation.Mode.None };
            ColorBlock optionColors = optionButton.colors;
            optionColors.normalColor = Color.white;
            optionColors.highlightedColor = new Color32(255, 222, 235, 255);
            optionColors.pressedColor = new Color32(205, 145, 178, 255);
            optionColors.selectedColor = optionColors.highlightedColor;
            optionButton.colors = optionColors;

            Outline optionOutline = optionObject.GetComponent<Outline>();
            optionOutline.effectColor = new Color32(128, 70, 119, 255);
            optionOutline.effectDistance = new Vector2(3f, -3f);

            var previewObject = new GameObject(
                "Preview",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image));
            previewObject.transform.SetParent(optionObject.transform, false);
            RectTransform previewRect = previewObject.GetComponent<RectTransform>();
            previewRect.anchorMin = new Vector2(0.06f, 0.08f);
            previewRect.anchorMax = new Vector2(0.43f, 0.92f);
            previewRect.offsetMin = Vector2.zero;
            previewRect.offsetMax = Vector2.zero;

            Image previewImage = previewObject.GetComponent<Image>();
            previewImage.sprite = LoadWizardSelectionPreview(definition.sourceVariant);
            previewImage.preserveAspect = true;
            previewImage.raycastTarget = false;

            Text optionLabel = CreateTitleText(
                "Label",
                optionObject.transform,
                new Vector2(0.45f, 0.22f),
                new Vector2(0.96f, 0.78f),
                definition.label,
                26,
                new Color32(255, 238, 224, 255));
            optionLabel.fontStyle = FontStyle.Bold;

            var selectedIndicator = new GameObject(
                "SelectedIndicator",
                typeof(RectTransform),
                typeof(CanvasRenderer),
                typeof(Image));
            selectedIndicator.transform.SetParent(optionObject.transform, false);
            RectTransform indicatorRect = selectedIndicator.GetComponent<RectTransform>();
            indicatorRect.anchorMin = new Vector2(0.59f, 0.72f);
            indicatorRect.anchorMax = new Vector2(0.92f, 0.91f);
            indicatorRect.offsetMin = Vector2.zero;
            indicatorRect.offsetMax = Vector2.zero;

            Image indicatorImage = selectedIndicator.GetComponent<Image>();
            indicatorImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            indicatorImage.type = Image.Type.Sliced;
            indicatorImage.color = new Color32(232, 132, 165, 255);
            indicatorImage.raycastTarget = false;

            Text indicatorLabel = CreateTitleText(
                "Text",
                selectedIndicator.transform,
                Vector2.zero,
                Vector2.one,
                "SELECTED",
                18,
                new Color32(36, 18, 39, 255));
            indicatorLabel.fontStyle = FontStyle.Bold;
            selectedIndicator.SetActive(false);

            return new BuiltWizardSelectionOption(
                definition,
                optionButton,
                previewImage,
                optionLabel,
                selectedIndicator);
        }

        private static Sprite LoadWizardSelectionPreview(string sourceVariant)
        {
            string path = WizardSourceRoot + "/" + sourceVariant +
                "/selected/standing/" + WizardCanonicalInitialDirection + ".png";
            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(path);
            if (sprite == null)
            {
                throw new InvalidDataException("Wizard selection preview is missing: " + path);
            }

            return sprite;
        }

        private static Text CreateTitleText(string name, Transform parent, Vector2 anchorMin,
            Vector2 anchorMax, string value, int fontSize, Color color)
        {
            var textObject = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            textObject.transform.SetParent(parent, false);

            var rect = textObject.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;

            var text = textObject.GetComponent<Text>();
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = fontSize;
            text.resizeTextForBestFit = true;
            text.resizeTextMinSize = Mathf.Max(12, fontSize / 2);
            text.resizeTextMaxSize = fontSize;
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Truncate;
            text.color = color;
            text.text = value;
            text.raycastTarget = false;
            return text;
        }

        /// Mirrors the door's ProgressFill pattern: a background bar with a Filled child
        /// Image whose fillAmount tracks CurrentHealth/MaxHealth. Positioned above the door
        /// progress bar so it never overlaps the door or mana indicators.
        private static void BuildHealthUI(GameObject canvasObject, PlayerHealth health)
        {
            var healthBarObject = new GameObject("HealthFill");
            healthBarObject.transform.SetParent(canvasObject.transform, false);
            var healthBarRect = healthBarObject.AddComponent<RectTransform>();
            // Was a 300x20 bar anchored (0.50, 0.25) - centre screen, a quarter up - which put a
            // player stat in the middle of the play space where the wizard and the fireball have
            // to stay legible, and read to Vincent as a bar floating detached from the HUD.
            // Now the second row of the single top-left column, directly under its own label.
            healthBarRect.anchorMin = new Vector2(0f, 1f);
            healthBarRect.anchorMax = new Vector2(0f, 1f);
            healthBarRect.pivot = new Vector2(0f, 1f);
            healthBarRect.anchoredPosition = new Vector2(HudLeftMargin, -HudHealthBarTop);
            healthBarRect.sizeDelta = new Vector2(HudBarWidth, HudBarHeight);
            var healthBarBackgroundImage = healthBarObject.AddComponent<Image>();
            healthBarBackgroundImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            healthBarBackgroundImage.type = Image.Type.Sliced;
            healthBarBackgroundImage.color = new Color(0.15f, 0.15f, 0.15f, 0.85f);

            var healthFillObject = new GameObject("Fill");
            healthFillObject.transform.SetParent(healthBarObject.transform, false);
            var healthFillRect = healthFillObject.AddComponent<RectTransform>();
            healthFillRect.anchorMin = Vector2.zero;
            healthFillRect.anchorMax = Vector2.one;
            healthFillRect.offsetMin = Vector2.zero;
            healthFillRect.offsetMax = Vector2.zero;
            var healthFill = healthFillObject.AddComponent<Image>();
            healthFill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            healthFill.type = Image.Type.Filled;
            healthFill.fillMethod = Image.FillMethod.Horizontal;
            healthFill.fillOrigin = (int)Image.OriginHorizontal.Left;
            healthFill.fillAmount = 1f;
            healthFill.color = Color.red;

            var healthUiBinding = canvasObject.AddComponent<PlayerHealthUI>();
            SetPrivateField(healthUiBinding, "health", health);
            SetPrivateField(healthUiBinding, "fillImage", healthFill);
            healthUiBinding.Bind(health, healthFill);
        }

        /// Mirrors the door's ProgressFill pattern: a background bar with a Filled child
        /// Image whose fillAmount tracks CurrentMana/MaxMana. Positioned below the door
        /// progress bar so the two never overlap.
        private static void BuildManaUI(GameObject canvasObject, PlayerMana mana, DebugManaSpendControl debugManaControl)
        {
            var manaBarObject = new GameObject("ManaFill");
            manaBarObject.transform.SetParent(canvasObject.transform, false);
            var manaBarRect = manaBarObject.AddComponent<RectTransform>();
            // Was anchored (0.50, 0.06) - centre screen, near the bottom edge - for the same
            // reason the health bar was centre screen, and with the same result. Third row of
            // the single top-left column now, matching the health bar's width and height so the
            // two read as one control rather than two unrelated strips.
            manaBarRect.anchorMin = new Vector2(0f, 1f);
            manaBarRect.anchorMax = new Vector2(0f, 1f);
            manaBarRect.pivot = new Vector2(0f, 1f);
            manaBarRect.anchoredPosition = new Vector2(HudLeftMargin, -HudManaBarTop);
            manaBarRect.sizeDelta = new Vector2(HudBarWidth, HudBarHeight);
            var manaBarBackgroundImage = manaBarObject.AddComponent<Image>();
            manaBarBackgroundImage.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            manaBarBackgroundImage.type = Image.Type.Sliced;
            manaBarBackgroundImage.color = new Color(0.15f, 0.15f, 0.15f, 0.85f);

            var manaFillObject = new GameObject("Fill");
            manaFillObject.transform.SetParent(manaBarObject.transform, false);
            var manaFillRect = manaFillObject.AddComponent<RectTransform>();
            manaFillRect.anchorMin = Vector2.zero;
            manaFillRect.anchorMax = Vector2.one;
            manaFillRect.offsetMin = Vector2.zero;
            manaFillRect.offsetMax = Vector2.zero;
            var manaFill = manaFillObject.AddComponent<Image>();
            manaFill.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/UISprite.psd");
            manaFill.type = Image.Type.Filled;
            manaFill.fillMethod = Image.FillMethod.Horizontal;
            manaFill.fillOrigin = (int)Image.OriginHorizontal.Left;
            manaFill.fillAmount = 1f;
            manaFill.color = Color.blue;

            var manaUiBinding = canvasObject.AddComponent<PlayerManaUI>();
            SetPrivateField(manaUiBinding, "mana", mana);
            SetPrivateField(manaUiBinding, "fillImage", manaFill);
            manaUiBinding.Bind(mana, manaFill);

            var manaButtonObject = new GameObject("DebugManaSpendButton");
            manaButtonObject.transform.SetParent(canvasObject.transform, false);
            var manaButtonRect = manaButtonObject.AddComponent<RectTransform>();
            manaButtonRect.anchorMin = new Vector2(0.02f, 0.02f);
            manaButtonRect.anchorMax = new Vector2(0.02f, 0.02f);
            manaButtonRect.pivot = Vector2.zero;
            manaButtonRect.anchoredPosition = new Vector2(0f, 44f);
            manaButtonRect.sizeDelta = new Vector2(260f, 40f);
            var manaButtonImage = manaButtonObject.AddComponent<Image>();
            manaButtonImage.color = new Color(0.1f, 0.1f, 0.6f);
            var manaButton = manaButtonObject.AddComponent<Button>();
            manaButton.targetGraphic = manaButtonImage;

            var manaButtonTextObject = new GameObject("Text");
            manaButtonTextObject.transform.SetParent(manaButtonObject.transform, false);
            var manaButtonTextRect = manaButtonTextObject.AddComponent<RectTransform>();
            manaButtonTextRect.anchorMin = Vector2.zero;
            manaButtonTextRect.anchorMax = Vector2.one;
            manaButtonTextRect.sizeDelta = Vector2.zero;
            var manaButtonText = manaButtonTextObject.AddComponent<Text>();
            manaButtonText.text = "DEBUG: Spend Mana (L)";
            manaButtonText.alignment = TextAnchor.MiddleCenter;
            manaButtonText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            manaButtonText.color = Color.white;
            manaButtonText.fontSize = 14;

            UnityEventTools.AddPersistentListener(manaButton.onClick, debugManaControl.TriggerDebugSpend);
        }

        // ONE top-left HUD column, the Art Director's arrangement of 2026-09-25 after Vincent
        // reported text drawn on top of text and bars floating mid-screen.
        //
        // WHAT WAS ACTUALLY WRONG: there were THREE layers drawing at once and no panel that
        // owned the corner. This ControlsHud sat at y 16..146; DemoRunFlow's IMGUI labels sit at
        // y 16..100 in a bigger, bolder face; and the health and mana bars were deliberately
        // centre-screen at anchors (0.50,0.25) and (0.50,0.06). "Detached from the HUD panel"
        // had no panel to be detached from.
        //
        // DemoRunFlow.cs is declared by NSC-086, NSC-119 and NSC-122 and NOT by NSC-049, so its
        // block is immovable from here and its own internal 4px overlap is routed to those tasks.
        // Everything below therefore starts BELOW that block rather than competing with it.
        //
        // The rows are derived as height + gap, never written as literal y values. DemoRunFlow's
        // overlap is precisely what literal y values cause: 32px-high rects placed on a 28px
        // pitch, so every adjacent pair collides by 4. Deriving each row from the previous one
        // makes that class of defect unrepresentable instead of fixing this instance of it.
        private const float HudLeftMargin = 16f;
        private const float HudRowGap = 8f;
        private const float HudBarWidth = 220f;
        private const float HudBarHeight = 14f;

        // The band DemoRunFlow's IMGUI owns: Health y16 h32, Mana y44 h32, Legend y72 h28.
        private const float DemoRunFlowTextBottom = 100f;

        private const float HudHealthBarTop = DemoRunFlowTextBottom + HudRowGap;
        private const float HudManaBarTop = HudHealthBarTop + HudBarHeight + HudRowGap;
        private const float HudControlsTop = HudManaBarTop + HudBarHeight + HudRowGap;

        /// Compact, always-visible controls panel, in the single top-left HUD column below the
        /// health and mana bars. It used to start at y16 and overlap DemoRunFlow's labels outright.
        private static void BuildControlsHud(Transform canvasTransform)
        {
            var hudRoot = new GameObject("ControlsHud");
            hudRoot.transform.SetParent(canvasTransform, false);
            var hudRect = hudRoot.AddComponent<RectTransform>();
            hudRect.anchorMin = new Vector2(0f, 1f);
            hudRect.anchorMax = new Vector2(0f, 1f);
            hudRect.pivot = new Vector2(0f, 1f);
            hudRect.anchoredPosition = new Vector2(HudLeftMargin, -HudControlsTop);
            hudRect.sizeDelta = new Vector2(300f, 130f);

            var hudBackground = hudRoot.AddComponent<Image>();
            hudBackground.sprite = AssetDatabase.GetBuiltinExtraResource<Sprite>("UI/Skin/Background.psd");
            hudBackground.type = Image.Type.Sliced;
            hudBackground.color = new Color(0f, 0f, 0f, 0.6f);

            var hudTextObject = new GameObject("Text");
            hudTextObject.transform.SetParent(hudRoot.transform, false);
            var hudTextRect = hudTextObject.AddComponent<RectTransform>();
            hudTextRect.anchorMin = Vector2.zero;
            hudTextRect.anchorMax = Vector2.one;
            hudTextRect.offsetMin = new Vector2(10f, 8f);
            hudTextRect.offsetMax = new Vector2(-10f, -8f);
            var hudText = hudTextObject.AddComponent<Text>();
            hudText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            hudText.fontSize = 14;
            hudText.alignment = TextAnchor.UpperLeft;
            hudText.color = Color.white;
            hudText.horizontalOverflow = HorizontalWrapMode.Wrap;
            hudText.verticalOverflow = VerticalWrapMode.Overflow;
            hudText.text =
                "Click/Hold Left Mouse - Move\n" +
                "Click Sealed Door - Approach and Open\n" +
                "Taking damage or moving away once opening starts\ncancels the opening attempt\n" +
                "[Debug/Test] K - Take Damage\n" +
                "[Debug/Test] L - Spend Mana";
        }

        private static void SetPrivateField(Object target, string fieldName, Object value)
        {
            var serializedObject = new SerializedObject(target);
            var property = serializedObject.FindProperty(fieldName);
            if (property == null)
            {
                Debug.LogWarning($"Field '{fieldName}' not found on {target.GetType().Name}.");
                return;
            }

            property.objectReferenceValue = value;
            serializedObject.ApplyModifiedPropertiesWithoutUndo();
        }

        private static void SetPrivateObjectArray(Object target, string fieldName, params Object[] values)
        {
            var serializedObject = new SerializedObject(target);
            var property = serializedObject.FindProperty(fieldName);
            if (property == null || !property.isArray)
            {
                Debug.LogWarning($"Array field '{fieldName}' not found on {target.GetType().Name}.");
                return;
            }

            property.arraySize = values.Length;
            for (var i = 0; i < values.Length; i++)
            {
                property.GetArrayElementAtIndex(i).objectReferenceValue = values[i];
            }
            serializedObject.ApplyModifiedPropertiesWithoutUndo();
        }

        private static void SetWizardSelectionOptions(
            WizardSelectionController controller,
            BuiltWizardSelectionOption[] options)
        {
            var serializedObject = new SerializedObject(controller);
            SerializedProperty optionsProperty = serializedObject.FindProperty("options");
            optionsProperty.arraySize = options.Length;

            for (var index = 0; index < options.Length; index++)
            {
                SerializedProperty optionProperty = optionsProperty.GetArrayElementAtIndex(index);
                BuiltWizardSelectionOption option = options[index];
                optionProperty.FindPropertyRelative("presentation").enumValueIndex =
                    (int)option.definition.presentation;
                optionProperty.FindPropertyRelative("skin").enumValueIndex = (int)option.definition.skin;
                optionProperty.FindPropertyRelative("button").objectReferenceValue = option.button;
                optionProperty.FindPropertyRelative("previewImage").objectReferenceValue = option.previewImage;
                optionProperty.FindPropertyRelative("label").objectReferenceValue = option.label;
                optionProperty.FindPropertyRelative("selectedIndicator").objectReferenceValue =
                    option.selectedIndicator;
            }

            serializedObject.ApplyModifiedPropertiesWithoutUndo();
        }

        private readonly struct WizardSelectionDefinition
        {
            public readonly WizardPresentation presentation;
            public readonly WizardSkin skin;
            public readonly string sourceVariant;
            public readonly string label;

            public WizardSelectionDefinition(
                WizardPresentation presentation,
                WizardSkin skin,
                string sourceVariant,
                string label)
            {
                this.presentation = presentation;
                this.skin = skin;
                this.sourceVariant = sourceVariant;
                this.label = label;
            }
        }

        private readonly struct BuiltWizardSelectionOption
        {
            public readonly WizardSelectionDefinition definition;
            public readonly Button button;
            public readonly Image previewImage;
            public readonly Text label;
            public readonly GameObject selectedIndicator;

            public BuiltWizardSelectionOption(
                WizardSelectionDefinition definition,
                Button button,
                Image previewImage,
                Text label,
                GameObject selectedIndicator)
            {
                this.definition = definition;
                this.button = button;
                this.previewImage = previewImage;
                this.label = label;
                this.selectedIndicator = selectedIndicator;
            }
        }

        // SerializedProperty has no generic value-type setter, so plain-data fields (Vector3,
        // float, etc.) are assigned directly through reflection instead.
        private static void SetPrivateFieldValue(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName,
                System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
            if (field == null)
            {
                Debug.LogWarning($"Field '{fieldName}' not found on {target.GetType().Name}.");
                return;
            }

            field.SetValue(target, value);
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;

            string[] parts = path.Split('/');
            string current = parts[0];
            for (var index = 1; index < parts.Length; index++)
            {
                string next = current + "/" + parts[index];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, parts[index]);
                }

                current = next;
            }
        }
    }
}
