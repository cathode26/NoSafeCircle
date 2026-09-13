using UnityEditor;
using UnityEditor.Events;
using UnityEngine;
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

        // Placeholder color only (GDD: placeholder character sprites are acceptable).
        private static readonly Color32 WizardSpriteFillColor = new Color32(88, 64, 145, 255);
        private static readonly Color32 WizardSpriteBorderColor = new Color32(40, 28, 66, 255);

        // Classic 2:1 dimetric isometric camera angle (rotate -45 degrees around Y to face
        // a corner, then tilt 30 degrees down) matching Diablo 1 / Ultima Online-style
        // fixed isometric presentation.
        internal static readonly Vector3 IsometricCameraEulerAngles = new Vector3(30f, -45f, 0f);

        // Fixed, hand-picked world-space offset from the follow target to the camera. This is
        // a plain constant - NOT derived by rotating a local vector through the camera's own
        // rotation - so the camera's framing is decoupled from its orientation.
        private static readonly Vector3 IsometricCameraOffset = new Vector3(10f, 10f, -10f);

        private const float IsometricOrthographicSize = 8f;

        // Unity Isometric Z-as-Y Individual Tilemap sorting axis. X intentionally contributes no
        // depth so moving along a horizontal wall cannot flip occlusion.
        private static readonly Vector3 IsometricTransparencySortAxis = new Vector3(0f, 1f, -0.26f);

        // Every root this class owns and clears before rebuilding, split out from the
        // environment-owned roots DoorPrototypeSceneBuilder clears itself (AC-005: explicit
        // builder-owned generated roots instead of one shared, implicit clearing list).
        internal static readonly string[] OwnedRootNames =
        {
            "Directional Light",
            "Main Camera",
            "Player",
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
            camera.transparencySortAxis = IsometricTransparencySortAxis;

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

        internal static void BuildPlayer(
            out PlayerMovement movement,
            out PlayerInteractionController interactionController,
            out PlayerHealth health,
            out DebugDamageControl debugControl,
            out PlayerMana mana,
            out DebugManaSpendControl debugManaControl,
            string architecturalTileAssetFolder)
        {
            var player = new GameObject("Player");
            player.transform.position = new Vector3(0f, 0f, -4f);

            var characterController = player.AddComponent<CharacterController>();
            characterController.center = new Vector3(0f, 1f, 0f);
            characterController.height = 2f;
            characterController.radius = 0.5f;

            // CharacterController collision keeps the capsule approximately one skinWidth
            // above the collision surface. Spawn at that already-grounded root height so
            // Play Mode does not begin with the wizard visibly falling onto the floor.
            player.transform.position =
                new Vector3(0f, characterController.skinWidth, -4f);

            // Placeholder wizard sprite (GDD: placeholder character sprites are acceptable),
            // instantiated from the same reusable world-space SpriteRenderer prefab as the
            // door. Already at the ground-contact convention's neutral local position, so the
            // sprite's feet sit exactly at the player's own transform position. The hierarchy
            // child keeps the existing "Visual" name other code/tests depend on, while
            // "WizardSprite" is the persistent asset identity so a future enemy/prop that also
            // names its child "Visual" cannot silently reuse the wizard's sprite asset.
            DoorPrototypeSceneBuilder.CreateWorldSpriteVisual(
                "Visual",
                "WizardSprite",
                player.transform,
                Vector3.zero,
                Quaternion.identity,
                new Vector2(1f, 2f),
                CreateWizardSilhouettePixels(
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    DoorPrototypeSceneBuilder.WorldSpriteTextureSize,
                    WizardSpriteFillColor,
                    WizardSpriteBorderColor),
                architecturalTileAssetFolder);

            health = player.AddComponent<PlayerHealth>();
            interactionController = player.AddComponent<PlayerInteractionController>();
            movement = player.AddComponent<PlayerMovement>();
            debugControl = player.AddComponent<DebugDamageControl>();
            mana = player.AddComponent<PlayerMana>();
            debugManaControl = player.AddComponent<DebugManaSpendControl>();

            DoorPrototypeSceneBuilder.SetPrivateField(interactionController, "playerHealth", health);
            DoorPrototypeSceneBuilder.SetPrivateField(debugControl, "target", health);
            DoorPrototypeSceneBuilder.SetPrivateField(debugManaControl, "target", mana);
            DoorPrototypeSceneBuilder.SetPrivateField(movement, "interactionController", interactionController);

            var inputActions = AssetDatabase.LoadAssetAtPath<InputActionAsset>(InputActionsAssetPath);
            if (inputActions == null)
            {
                Debug.LogWarning($"DoorPrototypeGlobalSceneBuilder could not load an InputActionAsset at " +
                    $"'{InputActionsAssetPath}'; PlayerMovement will have no input actions asset assigned.");
            }
            DoorPrototypeSceneBuilder.SetPrivateField(movement, "inputActions", inputActions);
        }

        // NSC-039 human runtime correction: a readable placeholder wizard silhouette (a
        // round head over a tapered robe) instead of an undifferentiated solid/bordered
        // square, so isometric sorting/occlusion against Tilemap walls and the door is
        // actually visible during validation. This remains placeholder-quality art only;
        // no final character art is implied.
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

        internal static void BuildUI(DoorInteractable door, DebugDamageControl debugControl,
            PlayerHealth health, PlayerMana mana, DebugManaSpendControl debugManaControl)
        {
            var canvasObject = new GameObject("Canvas");
            var canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasObject.AddComponent<CanvasScaler>();
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
            DoorPrototypeSceneBuilder.SetPrivateField(uiBinding, "door", door);
            DoorPrototypeSceneBuilder.SetPrivateField(uiBinding, "promptRoot", promptRoot);
            DoorPrototypeSceneBuilder.SetPrivateField(uiBinding, "progressFillImage", progressFill);

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
        }

        /// Mirrors the door's ProgressFill pattern: a background bar with a Filled child
        /// Image whose fillAmount tracks CurrentHealth/MaxHealth. Positioned above the door
        /// progress bar so it never overlaps the door or mana indicators.
        private static void BuildHealthUI(GameObject canvasObject, PlayerHealth health)
        {
            var healthBarObject = new GameObject("HealthFill");
            healthBarObject.transform.SetParent(canvasObject.transform, false);
            var healthBarRect = healthBarObject.AddComponent<RectTransform>();
            // Keep health in its own center-screen vertical lane above the interaction
            // prompt. This leaves clear separation from the prompt, progress bar, and mana bar.
            healthBarRect.anchorMin = new Vector2(0.5f, 0.25f);
            healthBarRect.anchorMax = new Vector2(0.5f, 0.25f);
            healthBarRect.sizeDelta = new Vector2(300f, 20f);
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
            DoorPrototypeSceneBuilder.SetPrivateField(healthUiBinding, "health", health);
            DoorPrototypeSceneBuilder.SetPrivateField(healthUiBinding, "fillImage", healthFill);
        }

        /// Mirrors the door's ProgressFill pattern: a background bar with a Filled child
        /// Image whose fillAmount tracks CurrentMana/MaxMana. Positioned below the door
        /// progress bar so the two never overlap.
        private static void BuildManaUI(GameObject canvasObject, PlayerMana mana, DebugManaSpendControl debugManaControl)
        {
            var manaBarObject = new GameObject("ManaFill");
            manaBarObject.transform.SetParent(canvasObject.transform, false);
            var manaBarRect = manaBarObject.AddComponent<RectTransform>();
            manaBarRect.anchorMin = new Vector2(0.5f, 0.06f);
            manaBarRect.anchorMax = new Vector2(0.5f, 0.06f);
            manaBarRect.sizeDelta = new Vector2(300f, 20f);
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
            DoorPrototypeSceneBuilder.SetPrivateField(manaUiBinding, "mana", mana);
            DoorPrototypeSceneBuilder.SetPrivateField(manaUiBinding, "fillImage", manaFill);

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

        /// Compact, always-visible controls panel. Kept as a sibling of, not merged
        /// into, the interaction prompt and progress-fill objects, and positioned in
        /// the top-left so it never overlaps them or the bottom-left debug button.
        private static void BuildControlsHud(Transform canvasTransform)
        {
            var hudRoot = new GameObject("ControlsHud");
            hudRoot.transform.SetParent(canvasTransform, false);
            var hudRect = hudRoot.AddComponent<RectTransform>();
            hudRect.anchorMin = new Vector2(0f, 1f);
            hudRect.anchorMax = new Vector2(0f, 1f);
            hudRect.pivot = new Vector2(0f, 1f);
            hudRect.anchoredPosition = new Vector2(16f, -16f);
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
    }
}
