using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor.World;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Editor.Enemies
{
    public static class StationaryEnemyPresentationBuilder
    {
        public const string SourceFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Source";
        public const string GeneratedImageFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Enemies/Generated";
        public const string PrefabFolder = "Assets/NoSafeCircle/DoorPrototype/Generated/Enemies";
        public const string ScenePath = "Assets/Scenes/DoorPrototype.unity";
        public const string ReviewRootName = "StationaryEnemyReview";

        public const float PixelsPerUnit = 128f;
        public const float MeleeScale = 2.25f;
        public const float RangedScale = 2f;
        public const int SortingOrder = 0;
        public const string SortingLayer = "Default";

        private static readonly StationaryEnemyDirection[] Directions =
        {
            StationaryEnemyDirection.North,
            StationaryEnemyDirection.NorthEast,
            StationaryEnemyDirection.East,
            StationaryEnemyDirection.SouthEast,
            StationaryEnemyDirection.South,
            StationaryEnemyDirection.SouthWest,
            StationaryEnemyDirection.West,
            StationaryEnemyDirection.NorthWest
        };

        [MenuItem("No Safe Circle/Enemies/Build Stationary Enemy Review")]
        public static void Build()
        {
            ValidateSourceInventory();
            EnsureFolder(GeneratedImageFolder);
            EnsureFolder(PrefabFolder);

            foreach (StationaryEnemyArchetype archetype in Enum.GetValues(typeof(StationaryEnemyArchetype)))
            {
                foreach (StationaryEnemyDirection direction in Directions)
                {
                    ImportSelectedImage(archetype, direction);
                }

                BuildPrefab(archetype);
            }

            Scene scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            PlaceReviewInstances(scene);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
            Debug.Log($"Stationary enemy review prefabs and scene built at {ScenePath}");
        }

        public static string ImagePath(StationaryEnemyArchetype archetype,
            StationaryEnemyDirection direction, bool generated)
        {
            string family = archetype == StationaryEnemyArchetype.Melee ? "melee" :
                archetype == StationaryEnemyArchetype.Ranged ? "ranged" :
                throw new ArgumentOutOfRangeException(nameof(archetype));
            string suffix;
            switch (direction)
            {
                case StationaryEnemyDirection.North: suffix = "n"; break;
                case StationaryEnemyDirection.NorthEast: suffix = "ne"; break;
                case StationaryEnemyDirection.East: suffix = "e"; break;
                case StationaryEnemyDirection.SouthEast: suffix = "se"; break;
                case StationaryEnemyDirection.South: suffix = "s"; break;
                case StationaryEnemyDirection.SouthWest: suffix = "sw"; break;
                case StationaryEnemyDirection.West: suffix = "w"; break;
                case StationaryEnemyDirection.NorthWest: suffix = "nw"; break;
                default: throw new ArgumentOutOfRangeException(nameof(direction));
            }

            string folder = generated ? GeneratedImageFolder : SourceFolder;
            return $"{folder}/enemy_{family}_{suffix}_idle_00.png";
        }

        public static string PrefabPath(StationaryEnemyArchetype archetype)
        {
            switch (archetype)
            {
                case StationaryEnemyArchetype.Melee: return PrefabFolder + "/StationaryMeleeEnemy.prefab";
                case StationaryEnemyArchetype.Ranged: return PrefabFolder + "/StationaryRangedEnemy.prefab";
                default: throw new ArgumentOutOfRangeException(nameof(archetype));
            }
        }

        public static void ValidateSourceInventory()
        {
            ValidateSourceInventory(SourceFolder);
        }

        public static void ValidateSourceInventory(string sourceFolder)
        {
            if (string.IsNullOrWhiteSpace(sourceFolder) || !Directory.Exists(sourceFolder))
            {
                throw new InvalidOperationException($"Selected enemy source folder is missing: {sourceFolder}");
            }

            var expected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (StationaryEnemyArchetype archetype in Enum.GetValues(typeof(StationaryEnemyArchetype)))
            {
                foreach (StationaryEnemyDirection direction in Directions)
                {
                    expected.Add(Path.GetFileName(ImagePath(archetype, direction, false)));
                }
            }

            string[] actual = Directory.GetFiles(sourceFolder, "*.png", SearchOption.TopDirectoryOnly)
                .Select(Path.GetFileName).ToArray();
            if (actual.Length != 16 || actual.Distinct(StringComparer.OrdinalIgnoreCase).Count() != 16 ||
                actual.Any(name => !expected.Contains(name)) || expected.Any(name => !actual.Contains(name, StringComparer.OrdinalIgnoreCase)))
            {
                throw new InvalidOperationException(
                    "Stationary enemy import requires exactly one selected PNG for each of the " +
                    "eight explicit directions in both Melee and Ranged families.");
            }
        }

        public static bool HasGeneratedPrefabs()
        {
            bool melee = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(StationaryEnemyArchetype.Melee)) != null;
            bool ranged = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(StationaryEnemyArchetype.Ranged)) != null;
            if (melee != ranged)
            {
                throw new InvalidOperationException("Only one stationary enemy prefab exists; rebuild both.");
            }
            return melee;
        }

        // Called by the named production command and after a later full scene rebuild.
        // Tests call it only in a deliberately opened, unsaved scene.
        public static void PlaceReviewInstances(Scene scene)
        {
            if (!scene.IsValid() || !scene.isLoaded)
            {
                throw new ArgumentException("A loaded scene is required.", nameof(scene));
            }
            if (!HasGeneratedPrefabs())
            {
                throw new InvalidOperationException("Build both stationary enemy prefabs before placement.");
            }

            ValidateAnchors(scene);
            foreach (GameObject oldRoot in scene.GetRootGameObjects()
                         .Where(candidate => candidate.name == ReviewRootName))
            {
                Object.DestroyImmediate(oldRoot);
            }

            GameObject root = new GameObject(ReviewRootName);
            SceneManager.MoveGameObjectToScene(root, scene);
            foreach (RoomId room in Enum.GetValues(typeof(RoomId)))
            {
                GameObject roomGroup = new GameObject(room.ToString());
                SceneManager.MoveGameObjectToScene(roomGroup, scene);
                roomGroup.transform.SetParent(root.transform, false);
                foreach (StationaryEnemyReviewAnchor anchor in StationaryEnemyReviewPlacement.Anchors
                             .Where(candidate => candidate.Room == room))
                {
                    GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(anchor.Archetype));
                    GameObject instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
                    instance.name = $"{anchor.Archetype}_{room}_Review";
                    instance.transform.SetParent(roomGroup.transform, false);
                    instance.transform.position = anchor.GroundPosition;
                    instance.GetComponent<StationaryEnemyPresentation>().SetFacing(anchor.Facing);
                }
            }
        }

        private static void ValidateAnchors(Scene scene)
        {
            RoomSceneCatalog.RoomCatalogEntry[] rooms = RoomSceneCatalog.CreateCanonicalRooms();
            RoomSceneCatalog.DoorSequenceEntry[] doors = RoomSceneCatalog.CreateCanonicalDoors();
            GameObject world = scene.GetRootGameObjects().SingleOrDefault(root => root.name == "World");
            Transform composed = world != null ? world.transform.Find("ComposedRooms") : null;
            if (composed == null)
            {
                throw new InvalidOperationException("The five composed rooms must exist before enemy review placement.");
            }

            BoxCollider[] hardGeometry = composed.GetComponentsInChildren<BoxCollider>()
                .Where(collider => !collider.name.Contains("Floor"))
                .ToArray();
            foreach (StationaryEnemyReviewAnchor anchor in StationaryEnemyReviewPlacement.Anchors)
            {
                RoomSceneCatalog.RoomCatalogEntry room = rooms.Single(entry => entry.RoomId == anchor.Room);
                Vector3 point = anchor.GroundPosition;
                if (point.y != 0f || point.x <= room.Bounds.MinX + 1f ||
                    point.x >= room.Bounds.MaxX - 1f || point.z <= room.Bounds.MinZ + 1f ||
                    point.z >= room.Bounds.MaxZ - 1f)
                {
                    throw new InvalidOperationException($"{anchor.Room} enemy review anchor is outside its room floor.");
                }

                foreach (RoomSceneCatalog.DoorSequenceEntry door in doors)
                {
                    if (Vector2.Distance(new Vector2(point.x, point.z), door.ExpectedGroundCenter) < 3.5f)
                    {
                        throw new InvalidOperationException($"{anchor.Room} enemy review anchor blocks a door approach.");
                    }
                }

                foreach (BoxCollider collider in hardGeometry)
                {
                    Bounds bounds = collider.bounds;
                    if (bounds.min.y > 0.5f || bounds.max.y < 0.5f) continue;
                    if (point.x >= bounds.min.x - 0.6f && point.x <= bounds.max.x + 0.6f &&
                        point.z >= bounds.min.z - 0.6f && point.z <= bounds.max.z + 0.6f)
                    {
                        throw new InvalidOperationException(
                            $"{anchor.Room} enemy review anchor overlaps {collider.name}.");
                    }
                }
            }
        }

        private static void ImportSelectedImage(StationaryEnemyArchetype archetype,
            StationaryEnemyDirection direction)
        {
            string source = ImagePath(archetype, direction, false);
            string generated = ImagePath(archetype, direction, true);
            byte[] selectedBytes = File.ReadAllBytes(source);
            if (!File.Exists(generated) || !selectedBytes.SequenceEqual(File.ReadAllBytes(generated)))
            {
                File.WriteAllBytes(generated, selectedBytes);
            }

            AssetDatabase.ImportAsset(generated, ImportAssetOptions.ForceSynchronousImport);
            TextureImporter importer = AssetImporter.GetAtPath(generated) as TextureImporter;
            if (importer == null)
            {
                throw new InvalidOperationException($"Unity did not create a TextureImporter for {generated}.");
            }

            float pivotY = archetype == StationaryEnemyArchetype.Melee ? 18f / 128f : 14f / 128f;
            Vector2 pivot = new Vector2(0.5f, pivotY);
            bool changed = importer.textureType != TextureImporterType.Sprite ||
                importer.spriteImportMode != SpriteImportMode.Single ||
                importer.spriteAlignment != (int)SpriteAlignment.Custom ||
                Vector2.Distance(importer.spritePivot, pivot) > 0.0001f ||
                !Mathf.Approximately(importer.spritePixelsPerUnit, PixelsPerUnit) ||
                importer.filterMode != FilterMode.Point || !importer.alphaIsTransparency ||
                !importer.isReadable || importer.mipmapEnabled ||
                importer.textureCompression != TextureImporterCompression.Uncompressed ||
                importer.wrapMode != TextureWrapMode.Clamp;
            if (changed)
            {
                importer.textureType = TextureImporterType.Sprite;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.spriteAlignment = (int)SpriteAlignment.Custom;
                importer.spritePivot = pivot;
                importer.spritePixelsPerUnit = PixelsPerUnit;
                importer.filterMode = FilterMode.Point;
                importer.alphaIsTransparency = true;
                importer.isReadable = true;
                importer.mipmapEnabled = false;
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                importer.wrapMode = TextureWrapMode.Clamp;
                importer.SaveAndReimport();
            }

            Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(generated);
            Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(generated);
            if (texture == null || sprite == null || texture.width != 128 || texture.height != 128 ||
                !texture.GetPixels32().Any(pixel => pixel.a == 0) ||
                !texture.GetPixels32().Any(pixel => pixel.a > 0))
            {
                throw new InvalidOperationException($"Selected enemy image lacks a 128x128 transparent Sprite: {source}");
            }
        }

        private static void BuildPrefab(StationaryEnemyArchetype archetype)
        {
            string path = PrefabPath(archetype);
            GameObject root = new GameObject(archetype == StationaryEnemyArchetype.Melee
                ? "StationaryMeleeEnemy" : "StationaryRangedEnemy");
            try
            {
                root.transform.localScale = Vector3.one * (archetype == StationaryEnemyArchetype.Melee
                    ? MeleeScale : RangedScale);
                SpriteRenderer renderer = root.AddComponent<SpriteRenderer>();
                renderer.sortingLayerName = SortingLayer;
                renderer.sortingOrder = SortingOrder;
                renderer.spriteSortPoint = SpriteSortPoint.Pivot;

                Sprite[] sprites = Directions.Select(direction => AssetDatabase.LoadAssetAtPath<Sprite>(
                    ImagePath(archetype, direction, true))).ToArray();
                StationaryEnemyPresentation presentation = root.AddComponent<StationaryEnemyPresentation>();
                presentation.Configure(archetype, StationaryEnemyDirection.SouthEast, sprites);
                if (PrefabUtility.SaveAsPrefabAsset(root, path) == null)
                {
                    throw new InvalidOperationException($"Could not save stationary enemy prefab at {path}.");
                }
            }
            finally
            {
                Object.DestroyImmediate(root);
            }
        }

        private static void EnsureFolder(string path)
        {
            string[] parts = path.Split('/');
            string parent = parts[0];
            for (int index = 1; index < parts.Length; index++)
            {
                string next = parent + "/" + parts[index];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(parent, parts[index]);
                }
                parent = next;
            }
        }
    }
}
