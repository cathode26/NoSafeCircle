using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.World
{
    /// Imports the approved enemy source sprites in place and owns their generated clips and
    /// Animator controllers. The scene builder is the only production caller.
    public static class EnemyAnimationAssetBuilder
    {
        public const float EnemyPixelsPerUnit = 64f;

        internal const string SourceRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source";
        internal const string WalkSourceRoot = SourceRoot + "/Walk";
        internal const string GeneratedRoot =
            "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Generated";

        /// <summary>True when an asset path lies in a directory this builder manages.</summary>
        /// <remarks>
        /// This builder owns exactly two directories: the idle root and Walk/. Art/Enemies/Source
        /// also carries sibling deliveries -- Death/ arrived with NSC-098/099 -- which this
        /// builder neither reads nor generates. Anything asserting an EXACT enemy-source
        /// inventory must ask this question instead of enumerating SourceRoot recursively,
        /// because a recursive scan makes the caller police folders it does not own. That is
        /// exactly what stopped composition for a day: 12 unrelated PNGs under Death/ fell out
        /// of an Except() as "Unexpected enemy source PNG" and aborted the whole scene build.
        /// Narrowing one caller is not enough -- a second reader of the same directory fails
        /// the same way -- so the managed set is declared ONCE, here, and asked for by name.
        /// </remarks>
        public static bool ManagesSourcePath(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath))
            {
                return false;
            }

            string normalized = assetPath.Replace("\\", "/");
            int lastSlash = normalized.LastIndexOf('/');
            if (lastSlash < 0)
            {
                return false;
            }

            string directory = normalized.Substring(0, lastSlash);
            return string.Equals(directory, SourceRoot, StringComparison.OrdinalIgnoreCase)
                || string.Equals(directory, WalkSourceRoot, StringComparison.OrdinalIgnoreCase);
        }

        private const int IdleSourceSize = 128;
        private const int WalkSourceSize = 176;
        private const int WalkFrameCount = 6;
        private const int WalkFrameRate = 12;

        private static readonly EnemyDefinition[] EnemyDefinitions =
        {
            new EnemyDefinition("melee", "MeleeEnemy"),
            new EnemyDefinition("ranged", "LanternWraith")
        };

        private static readonly DirectionDefinition[] DirectionDefinitions =
        {
            new DirectionDefinition("n", "north"),
            new DirectionDefinition("ne", "north-east"),
            new DirectionDefinition("e", "east"),
            new DirectionDefinition("se", "south-east"),
            new DirectionDefinition("s", "south"),
            new DirectionDefinition("sw", "south-west"),
            new DirectionDefinition("w", "west"),
            new DirectionDefinition("nw", "north-west")
        };

        // Reserved for Vincent-approved whole-pixel corrections after the in-game visual gate.
        // Builder and audit tests both read this single table; revision 4 starts with no offsets.
        private static readonly IReadOnlyDictionary<string, int> PivotCorrections =
            new Dictionary<string, int>();

        public static int PivotCorrectionPixels(string sourceEnemyName, string directionName)
        {
            string key = sourceEnemyName + "/" + directionName;
            return PivotCorrections.TryGetValue(key, out int correction) ? correction : 0;
        }

        internal static EnemyAnimationAssets Build()
        {
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art");
            EnsureFolder("Assets/NoSafeCircle/DoorPrototype/Art/Enemies");
            EnsureFolder(GeneratedRoot);

            WalkInventory inventory = LoadAndValidateInventory();
            List<SourceFrame> frames = CollectAndValidateSourceFrames(inventory);
            Dictionary<string, Sprite> spritesByPath = ImportSprites(frames);

            HashSet<string> expectedClipPaths = ExpectedClipPaths();
            RemoveUnexpectedGeneratedClips(expectedClipPaths);

            AnimatorController meleeController = BuildController(
                EnemyDefinitions[0], spritesByPath);
            AnimatorController wraithController = BuildController(
                EnemyDefinitions[1], spritesByPath);

            Sprite meleeSouthIdle = spritesByPath[IdlePath("melee", "s")];
            Sprite wraithSouthIdle = spritesByPath[IdlePath("ranged", "s")];
            return new EnemyAnimationAssets(
                meleeController,
                wraithController,
                meleeSouthIdle,
                wraithSouthIdle);
        }

        internal static EnemyAnimationAssets Load()
        {
            RuntimeAnimatorController meleeController = LoadRequired<RuntimeAnimatorController>(
                GeneratedRoot + "/MeleeEnemyAnimator.controller");
            RuntimeAnimatorController wraithController = LoadRequired<RuntimeAnimatorController>(
                GeneratedRoot + "/LanternWraithAnimator.controller");
            Sprite meleeSouthIdle = LoadRequired<Sprite>(IdlePath("melee", "s"));
            Sprite wraithSouthIdle = LoadRequired<Sprite>(IdlePath("ranged", "s"));
            return new EnemyAnimationAssets(
                meleeController,
                wraithController,
                meleeSouthIdle,
                wraithSouthIdle);
        }

        private static T LoadRequired<T>(string path) where T : Object
        {
            T asset = AssetDatabase.LoadAssetAtPath<T>(path);
            if (asset == null)
            {
                throw new FileNotFoundException(
                    "Required enemy animation asset is missing: " + path, path);
            }

            return asset;
        }

        private static List<SourceFrame> CollectAndValidateSourceFrames(WalkInventory inventory)
        {
            var frames = new List<SourceFrame>(112);
            var expectedPaths = new HashSet<string>(StringComparer.Ordinal);

            foreach (EnemyDefinition enemy in EnemyDefinitions)
            {
                foreach (DirectionDefinition direction in DirectionDefinitions)
                {
                    string idlePath = IdlePath(enemy.SourceName, direction.Code);
                    AddExpectedPath(expectedPaths, idlePath);
                    frames.Add(LoadSourceFrame(
                        idlePath,
                        enemy.SourceName,
                        direction.Name,
                        IdleSourceSize,
                        FindIdleGroundLineFromBottom(idlePath)));

                    for (int frameIndex = 0; frameIndex < WalkFrameCount; frameIndex++)
                    {
                        string walkPath = WalkPath(
                            enemy.SourceName, direction.Code, frameIndex);
                        AddExpectedPath(expectedPaths, walkPath);
                        frames.Add(LoadSourceFrame(
                            walkPath,
                            enemy.SourceName,
                            direction.Name,
                            WalkSourceSize,
                            WalkSourceSize - inventory.alpha_bottom_y_from_top));
                    }
                }
            }

            // SCAN ONLY THE TWO DIRECTORIES THIS BUILDER ACTUALLY MANAGES.
            // This used to be SearchOption.AllDirectories over SourceRoot, which made the
            // builder police every subdirectory beneath it -- including ones belonging to
            // deliveries it knows nothing about. Landing the NSC-098/099 death sprites into
            // Source/Death put 12 PNGs under that recursive scan, and because the expected
            // set is built exclusively from fully-qualified idle paths (SourceRoot/*.png)
            // and walk paths (SourceRoot/Walk/*.png), every one of them fell out of
            // actualPaths.Except(expectedPaths) as an "Unexpected enemy source PNG" --
            // which threw out of BuildChaseEnemies and stopped DoorPrototypeSceneBuilder.Build
            // BEFORE it composed a single room. Four real rooms were unreachable because an
            // animation builder was validating a sibling folder.
            //
            // The guard itself is kept, not weakened: a stray or misnamed PNG in either
            // managed directory is still caught, and a Death/ file could never have
            // satisfied an expected path anyway because those paths are fully qualified.
            // What it stops doing is claiming authority over directories it does not own.
            string[] actualPaths = Directory
                .GetFiles(SourceRoot, "*.png", SearchOption.TopDirectoryOnly)
                .Concat(Directory.Exists(WalkSourceRoot)
                    ? Directory.GetFiles(WalkSourceRoot, "*.png", SearchOption.TopDirectoryOnly)
                    : Array.Empty<string>())
                .Select(NormalizePath)
                .OrderBy(path => path, StringComparer.Ordinal)
                .ToArray();
            string[] duplicatePaths = actualPaths
                .GroupBy(path => path, StringComparer.Ordinal)
                .Where(group => group.Count() > 1)
                .Select(group => group.Key)
                .ToArray();
            if (duplicatePaths.Length > 0)
            {
                throw new InvalidDataException(
                    "Duplicate enemy source PNG: " + duplicatePaths[0]);
            }

            string missingPath = expectedPaths.Except(actualPaths).FirstOrDefault();
            if (missingPath != null)
            {
                throw new FileNotFoundException(
                    "Missing enemy source PNG: " + missingPath, missingPath);
            }

            string extraPath = actualPaths.Except(expectedPaths).FirstOrDefault();
            if (extraPath != null)
            {
                throw new InvalidDataException("Unexpected enemy source PNG: " + extraPath);
            }

            return frames;
        }

        private static void AddExpectedPath(ISet<string> expectedPaths, string path)
        {
            if (!expectedPaths.Add(path))
            {
                throw new InvalidDataException("Duplicate expected enemy source PNG: " + path);
            }
        }

        private static SourceFrame LoadSourceFrame(
            string path,
            string sourceEnemyName,
            string directionName,
            int expectedSize,
            int groundLineFromBottom)
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Missing enemy source PNG: " + path, path);
            }

            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                if (!texture.LoadImage(File.ReadAllBytes(path)))
                {
                    throw new InvalidDataException("Enemy source is not a readable PNG: " + path);
                }

                if (texture.width != expectedSize || texture.height != expectedSize)
                {
                    throw new InvalidDataException(
                        $"Enemy source has wrong size: {path} ({texture.width}x{texture.height}, " +
                        $"expected {expectedSize}x{expectedSize})");
                }
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }

            int correction = PivotCorrectionPixels(sourceEnemyName, directionName);
            int correctedGroundLine = groundLineFromBottom + correction;
            if (correctedGroundLine < 0 || correctedGroundLine > expectedSize)
            {
                throw new InvalidDataException("Enemy pivot correction is outside the source: " + path);
            }

            return new SourceFrame(path, correctedGroundLine / (float)expectedSize);
        }

        private static int FindIdleGroundLineFromBottom(string path)
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Missing enemy source PNG: " + path, path);
            }

            var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                if (!texture.LoadImage(File.ReadAllBytes(path)))
                {
                    throw new InvalidDataException("Enemy idle source is not a readable PNG: " + path);
                }

                Color32[] pixels = texture.GetPixels32();
                for (int y = 0; y < texture.height; y++)
                {
                    int rowStart = y * texture.width;
                    for (int x = 0; x < texture.width; x++)
                    {
                        if (pixels[rowStart + x].a > 0)
                        {
                            return y;
                        }
                    }
                }
            }
            finally
            {
                Object.DestroyImmediate(texture);
            }

            throw new InvalidDataException("Enemy idle source has no opaque pixels: " + path);
        }

        private static WalkInventory LoadAndValidateInventory()
        {
            string path = WalkSourceRoot + "/inventory.json";
            if (!File.Exists(path))
            {
                throw new FileNotFoundException(
                    "Enemy walk inventory is missing: " + path, path);
            }

            WalkInventory inventory = JsonUtility.FromJson<WalkInventory>(File.ReadAllText(path));
            if (inventory == null || inventory.canvas_size == null ||
                inventory.canvas_size.Length != 2 ||
                inventory.canvas_size[0] != WalkSourceSize ||
                inventory.canvas_size[1] != WalkSourceSize)
            {
                throw new InvalidDataException("Enemy walk inventory has the wrong canvas size: " + path);
            }

            if (inventory.alpha_bottom_y_from_top != 132)
            {
                throw new InvalidDataException("Enemy walk inventory has the wrong ground line: " + path);
            }

            string[] entryFiles = inventory.entries == null
                ? Array.Empty<string>()
                : inventory.entries.Select(entry => entry.file).ToArray();
            string duplicate = entryFiles.GroupBy(file => file, StringComparer.Ordinal)
                .FirstOrDefault(group => group.Count() > 1)?.Key;
            if (duplicate != null)
            {
                throw new InvalidDataException(
                    "Duplicate enemy walk inventory entry: " + WalkSourceRoot + "/" + duplicate);
            }

            string[] expectedFiles = ExpectedWalkFileNames().ToArray();
            string missing = expectedFiles.Except(entryFiles).FirstOrDefault();
            if (missing != null)
            {
                throw new InvalidDataException(
                    "Missing enemy walk inventory entry: " + WalkSourceRoot + "/" + missing);
            }

            string extra = entryFiles.Except(expectedFiles).FirstOrDefault();
            if (extra != null)
            {
                throw new InvalidDataException(
                    "Unexpected enemy walk inventory entry: " + WalkSourceRoot + "/" + extra);
            }

            return inventory;
        }

        private static Dictionary<string, Sprite> ImportSprites(IEnumerable<SourceFrame> frames)
        {
            var spritesByPath = new Dictionary<string, Sprite>(StringComparer.Ordinal);
            foreach (SourceFrame frame in frames)
            {
                AssetDatabase.ImportAsset(frame.Path, ImportAssetOptions.ForceUpdate);
                TextureImporter importer = AssetImporter.GetAtPath(frame.Path) as TextureImporter;
                if (importer == null)
                {
                    throw new FileNotFoundException(
                        "Enemy source is not a texture: " + frame.Path, frame.Path);
                }

                importer.textureType = TextureImporterType.Sprite;
                importer.textureShape = TextureImporterShape.Texture2D;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.filterMode = FilterMode.Point;
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                importer.mipmapEnabled = false;
                importer.spritePixelsPerUnit = EnemyPixelsPerUnit;

                var settings = new TextureImporterSettings();
                importer.ReadTextureSettings(settings);
                settings.spriteAlignment = (int)SpriteAlignment.Custom;
                settings.spritePivot = new Vector2(0.5f, frame.PivotY);
                importer.SetTextureSettings(settings);
                ClearCookieImportDefaults(importer);
                importer.SaveAndReimport();

                Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(frame.Path);
                if (sprite == null)
                {
                    throw new InvalidDataException(
                        "Enemy source did not import as a Sprite: " + frame.Path);
                }

                spritesByPath.Add(frame.Path, sprite);
            }

            return spritesByPath;
        }

        private static void ClearCookieImportDefaults(TextureImporter importer)
        {
            var serializedImporter = new SerializedObject(importer);
            foreach (string propertyName in new[] { "m_ApplyGammaDecoding", "m_CookieLightType" })
            {
                SerializedProperty property = serializedImporter.FindProperty(propertyName);
                if (property == null)
                {
                    throw new InvalidDataException(
                        "TextureImporter for " + importer.assetPath +
                        " has no serialized property " + propertyName);
                }

                if (property.propertyType == SerializedPropertyType.Boolean)
                {
                    property.boolValue = false;
                }
                else
                {
                    property.intValue = 0;
                }
            }

            serializedImporter.ApplyModifiedPropertiesWithoutUndo();
        }

        private static AnimatorController BuildController(
            EnemyDefinition enemy,
            IReadOnlyDictionary<string, Sprite> spritesByPath)
        {
            string controllerPath = GeneratedRoot + "/" + enemy.AnimatorName + "Animator.controller";
            AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            if (controller == null)
            {
                controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
            }

            if (controller.layers.Length == 0)
            {
                throw new InvalidDataException("Enemy Animator has no layer: " + controllerPath);
            }

            if (controller.layers.Length != 1)
            {
                controller.layers = new[] { controller.layers[0] };
            }

            AnimatorStateMachine stateMachine = controller.layers[0].stateMachine;
            HashSet<string> expectedStateNames = ExpectedStateNames(enemy.AnimatorName);
            RemoveUnexpectedOrDuplicateStates(stateMachine, expectedStateNames);

            AnimatorState southIdleState = null;
            foreach (DirectionDefinition direction in DirectionDefinitions)
            {
                string idleName = StateName(enemy.AnimatorName, "idle", direction.Name);
                AnimationClip idleClip = EnsureClip(
                    idleName,
                    new[] { spritesByPath[IdlePath(enemy.SourceName, direction.Code)] },
                    1);
                AnimatorState idleState = EnsureState(stateMachine, idleName, idleClip);
                if (direction.Name == "south")
                {
                    southIdleState = idleState;
                }

                var walkSprites = new Sprite[WalkFrameCount];
                for (int frame = 0; frame < WalkFrameCount; frame++)
                {
                    walkSprites[frame] = spritesByPath[
                        WalkPath(enemy.SourceName, direction.Code, frame)];
                }

                string walkName = StateName(enemy.AnimatorName, "walk", direction.Name);
                AnimationClip walkClip = EnsureClip(walkName, walkSprites, WalkFrameRate);
                EnsureState(stateMachine, walkName, walkClip);
            }

            stateMachine.defaultState = southIdleState;
            EditorUtility.SetDirty(stateMachine);
            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssetIfDirty(controller);
            return controller;
        }

        private static void RemoveUnexpectedOrDuplicateStates(
            AnimatorStateMachine stateMachine,
            ISet<string> expectedNames)
        {
            var retainedNames = new HashSet<string>(StringComparer.Ordinal);
            foreach (ChildAnimatorState child in stateMachine.states)
            {
                if (!expectedNames.Contains(child.state.name) ||
                    !retainedNames.Add(child.state.name))
                {
                    stateMachine.RemoveState(child.state);
                }
            }
        }

        private static AnimatorState EnsureState(
            AnimatorStateMachine stateMachine,
            string name,
            AnimationClip clip)
        {
            foreach (ChildAnimatorState child in stateMachine.states)
            {
                if (child.state.name != name) continue;

                child.state.motion = clip;
                EditorUtility.SetDirty(child.state);
                return child.state;
            }

            AnimatorState state = stateMachine.AddState(name);
            state.motion = clip;
            return state;
        }

        private static AnimationClip EnsureClip(string name, Sprite[] sprites, int frameRate)
        {
            string path = GeneratedRoot + "/" + name + ".anim";
            AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null)
            {
                clip = new AnimationClip { name = name };
                AssetDatabase.CreateAsset(clip, path);
            }

            clip.name = name;
            clip.frameRate = frameRate;
            foreach (EditorCurveBinding binding in AnimationUtility.GetObjectReferenceCurveBindings(clip))
            {
                AnimationUtility.SetObjectReferenceCurve(clip, binding, null);
            }
            foreach (EditorCurveBinding binding in AnimationUtility.GetCurveBindings(clip))
            {
                AnimationUtility.SetEditorCurve(clip, binding, null);
            }

            var keyframes = new ObjectReferenceKeyframe[sprites.Length];
            for (int frame = 0; frame < sprites.Length; frame++)
            {
                keyframes[frame] = new ObjectReferenceKeyframe
                {
                    time = frame / (float)frameRate,
                    value = sprites[frame]
                };
            }

            AnimationUtility.SetObjectReferenceCurve(
                clip,
                EditorCurveBinding.PPtrCurve("Visual", typeof(SpriteRenderer), "m_Sprite"),
                keyframes);
            AnimationClipSettings settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = true;
            AnimationUtility.SetAnimationClipSettings(clip, settings);
            EditorUtility.SetDirty(clip);
            AssetDatabase.SaveAssetIfDirty(clip);
            return clip;
        }

        private static void RemoveUnexpectedGeneratedClips(ISet<string> expectedClipPaths)
        {
            string[] clipPaths = AssetDatabase.FindAssets("t:AnimationClip", new[] { GeneratedRoot })
                .Select(AssetDatabase.GUIDToAssetPath)
                .ToArray();
            foreach (string clipPath in clipPaths)
            {
                if (!expectedClipPaths.Contains(clipPath))
                {
                    AssetDatabase.DeleteAsset(clipPath);
                }
            }
        }

        private static HashSet<string> ExpectedClipPaths()
        {
            var paths = new HashSet<string>(StringComparer.Ordinal);
            foreach (EnemyDefinition enemy in EnemyDefinitions)
            {
                foreach (string stateName in ExpectedStateNames(enemy.AnimatorName))
                {
                    paths.Add(GeneratedRoot + "/" + stateName + ".anim");
                }
            }

            return paths;
        }

        private static HashSet<string> ExpectedStateNames(string animatorName)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (DirectionDefinition direction in DirectionDefinitions)
            {
                names.Add(StateName(animatorName, "idle", direction.Name));
                names.Add(StateName(animatorName, "walk", direction.Name));
            }

            return names;
        }

        private static IEnumerable<string> ExpectedWalkFileNames()
        {
            foreach (EnemyDefinition enemy in EnemyDefinitions)
            {
                foreach (DirectionDefinition direction in DirectionDefinitions)
                {
                    for (int frame = 0; frame < WalkFrameCount; frame++)
                    {
                        yield return Path.GetFileName(
                            WalkPath(enemy.SourceName, direction.Code, frame));
                    }
                }
            }
        }

        private static string IdlePath(string sourceEnemyName, string directionCode)
        {
            return SourceRoot + "/enemy_" + sourceEnemyName + "_" + directionCode +
                "_idle_00.png";
        }

        private static string WalkPath(
            string sourceEnemyName,
            string directionCode,
            int frameIndex)
        {
            return WalkSourceRoot + "/enemy_" + sourceEnemyName + "_" + directionCode +
                "_walk_" + frameIndex.ToString("00") + ".png";
        }

        private static string StateName(string animatorName, string motion, string directionName)
        {
            return animatorName + "_" + motion + "_" + directionName;
        }

        private static string NormalizePath(string path)
        {
            return path.Replace('\\', '/');
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;

            string[] parts = path.Split('/');
            string current = parts[0];
            for (int index = 1; index < parts.Length; index++)
            {
                string next = current + "/" + parts[index];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, parts[index]);
                }

                current = next;
            }
        }

        internal readonly struct EnemyAnimationAssets
        {
            public readonly RuntimeAnimatorController MeleeController;
            public readonly RuntimeAnimatorController WraithController;
            public readonly Sprite MeleeSouthIdle;
            public readonly Sprite WraithSouthIdle;

            public EnemyAnimationAssets(
                RuntimeAnimatorController meleeController,
                RuntimeAnimatorController wraithController,
                Sprite meleeSouthIdle,
                Sprite wraithSouthIdle)
            {
                MeleeController = meleeController;
                WraithController = wraithController;
                MeleeSouthIdle = meleeSouthIdle;
                WraithSouthIdle = wraithSouthIdle;
            }
        }

        private readonly struct EnemyDefinition
        {
            public readonly string SourceName;
            public readonly string AnimatorName;

            public EnemyDefinition(string sourceName, string animatorName)
            {
                SourceName = sourceName;
                AnimatorName = animatorName;
            }
        }

        private readonly struct DirectionDefinition
        {
            public readonly string Code;
            public readonly string Name;

            public DirectionDefinition(string code, string name)
            {
                Code = code;
                Name = name;
            }
        }

        private readonly struct SourceFrame
        {
            public readonly string Path;
            public readonly float PivotY;

            public SourceFrame(string path, float pivotY)
            {
                Path = path;
                PivotY = pivotY;
            }
        }

        [Serializable]
        private sealed class WalkInventory
        {
            public int[] canvas_size;
            public int alpha_bottom_y_from_top;
            public WalkInventoryEntry[] entries;
        }

        [Serializable]
        private sealed class WalkInventoryEntry
        {
            public string file;
        }
    }
}
