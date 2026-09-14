using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor.Enemies;
using NoSafeCircle.DoorPrototype.Enemies;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public sealed class StationaryEnemyPresentationIntegrationTests
    {
        private static readonly StationaryEnemyDirection[] Directions =
        {
            StationaryEnemyDirection.North, StationaryEnemyDirection.NorthEast,
            StationaryEnemyDirection.East, StationaryEnemyDirection.SouthEast,
            StationaryEnemyDirection.South, StationaryEnemyDirection.SouthWest,
            StationaryEnemyDirection.West, StationaryEnemyDirection.NorthWest
        };

        [Test]
        public void SourceInventory_RequiresExactlyBothFamiliesAndEightExplicitFacings()
        {
            StationaryEnemyPresentationBuilder.ValidateSourceInventory();
            string[] source = Directory.GetFiles(StationaryEnemyPresentationBuilder.SourceFolder, "*.png");
            Assert.AreEqual(16, source.Length);

            string temporary = Path.Combine(Path.GetTempPath(), "NSC077-Source-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temporary);
            try
            {
                foreach (StationaryEnemyArchetype archetype in Enum.GetValues(typeof(StationaryEnemyArchetype)))
                {
                    foreach (StationaryEnemyDirection direction in Directions)
                    {
                        File.WriteAllBytes(Path.Combine(temporary,
                            Path.GetFileName(StationaryEnemyPresentationBuilder.ImagePath(
                                archetype, direction, false))), new byte[] { 1 });
                    }
                }

                Assert.DoesNotThrow(() => StationaryEnemyPresentationBuilder.ValidateSourceInventory(temporary));
                File.Delete(Path.Combine(temporary, "enemy_melee_ne_idle_00.png"));
                Assert.Throws<InvalidOperationException>(() =>
                    StationaryEnemyPresentationBuilder.ValidateSourceInventory(temporary));
                File.WriteAllBytes(Path.Combine(temporary, "enemy_melee_ne_idle_00.png"), new byte[] { 1 });
                File.WriteAllBytes(Path.Combine(temporary, "enemy_melee_unknown_idle_00.png"), new byte[] { 1 });
                Assert.Throws<InvalidOperationException>(() =>
                    StationaryEnemyPresentationBuilder.ValidateSourceInventory(temporary));
            }
            finally
            {
                Directory.Delete(temporary, true);
            }
        }

        [Test]
        public void GeneratedImages_BindExactSourcesAndGroundedSpriteImportSettings()
        {
            foreach (StationaryEnemyArchetype archetype in Enum.GetValues(typeof(StationaryEnemyArchetype)))
            {
                foreach (StationaryEnemyDirection direction in Directions)
                {
                    string source = StationaryEnemyPresentationBuilder.ImagePath(archetype, direction, false);
                    string generated = StationaryEnemyPresentationBuilder.ImagePath(archetype, direction, true);
                    CollectionAssert.AreEqual(File.ReadAllBytes(source), File.ReadAllBytes(generated), generated);
                    TextureImporter importer = AssetImporter.GetAtPath(generated) as TextureImporter;
                    Assert.IsNotNull(importer, generated);
                    var settings = new TextureImporterSettings();
                    importer.ReadTextureSettings(settings);
                    Assert.AreEqual(TextureImporterType.Sprite, importer.textureType);
                    Assert.AreEqual(SpriteImportMode.Single, importer.spriteImportMode);
                    Assert.AreEqual((int)SpriteAlignment.Custom, settings.spriteAlignment);
                    Assert.AreEqual(StationaryEnemyPresentationBuilder.PixelsPerUnit, importer.spritePixelsPerUnit);
                    Assert.AreEqual(FilterMode.Point, importer.filterMode);
                    Assert.AreEqual(TextureImporterCompression.Uncompressed, importer.textureCompression);
                    Assert.AreEqual(TextureWrapMode.Clamp, importer.wrapMode);
                    Assert.IsTrue(importer.alphaIsTransparency);
                    Assert.IsFalse(importer.mipmapEnabled);
                    Assert.IsTrue(importer.isReadable);
                    Assert.That(settings.spritePivot.x, Is.EqualTo(0.5f).Within(0.0001f));
                    Assert.That(settings.spritePivot.y,
                        Is.EqualTo(archetype == StationaryEnemyArchetype.Melee ? 18f / 128f : 14f / 128f)
                            .Within(0.0001f));

                    Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(generated);
                    Assert.IsNotNull(sprite, generated);
                    Assert.AreEqual(new Rect(0f, 0f, 128f, 128f), sprite.rect);
                    Assert.That(sprite.pivot.x, Is.EqualTo(64f).Within(0.001f));
                    Assert.That(sprite.pivot.y,
                        Is.EqualTo(archetype == StationaryEnemyArchetype.Melee ? 18f : 14f).Within(0.001f));
                    Assert.IsNotEmpty(AssetDatabase.AssetPathToGUID(generated));
                    Color32[] pixels = sprite.texture.GetPixels32();
                    Assert.IsTrue(pixels.Any(pixel => pixel.a == 0));
                    Assert.IsTrue(pixels.Any(pixel => pixel.a > 0));
                }
            }
        }

        [Test]
        public void Prefabs_HaveOnlyDirectionMappedWorldSpritesAndNoGameplayComponents()
        {
            foreach (StationaryEnemyArchetype archetype in Enum.GetValues(typeof(StationaryEnemyArchetype)))
            {
                string path = StationaryEnemyPresentationBuilder.PrefabPath(archetype);
                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                Assert.IsNotNull(prefab, path);
                GameObject instance = PrefabUtility.LoadPrefabContents(path);
                try
                {
                    Assert.AreEqual(3, instance.GetComponents<Component>().Length,
                        "Review prefabs contain only Transform, SpriteRenderer and presentation.");
                    Assert.AreEqual(0, instance.transform.childCount);
                    Assert.AreEqual(0, instance.GetComponentsInChildren<Collider>().Length);
                    Assert.AreEqual(0, instance.GetComponentsInChildren<Rigidbody>().Length);
                    Assert.AreEqual(Vector3.one * (archetype == StationaryEnemyArchetype.Melee
                        ? StationaryEnemyPresentationBuilder.MeleeScale
                        : StationaryEnemyPresentationBuilder.RangedScale), instance.transform.localScale);
                    SpriteRenderer renderer = instance.GetComponent<SpriteRenderer>();
                    Assert.IsNotNull(renderer);
                    Assert.AreEqual(StationaryEnemyPresentationBuilder.SortingLayer, renderer.sortingLayerName);
                    Assert.AreEqual(StationaryEnemyPresentationBuilder.SortingOrder, renderer.sortingOrder);
                    Assert.AreEqual(SpriteSortPoint.Pivot, renderer.spriteSortPoint);
                    StationaryEnemyPresentation presentation = instance.GetComponent<StationaryEnemyPresentation>();
                    Assert.IsNotNull(presentation);
                    Assert.AreEqual(archetype, presentation.Archetype);
                    foreach (StationaryEnemyDirection direction in Directions)
                    {
                        Sprite expected = AssetDatabase.LoadAssetAtPath<Sprite>(
                            StationaryEnemyPresentationBuilder.ImagePath(archetype, direction, true));
                        Assert.AreSame(expected, presentation.SpriteFor(direction));
                        presentation.SetFacing(direction);
                        Assert.AreEqual(direction, presentation.Facing);
                        Assert.AreSame(expected, renderer.sprite);
                    }
                }
                finally
                {
                    PrefabUtility.UnloadPrefabContents(instance);
                }
            }
        }

        [Test]
        public void CommittedScene_ContainsTwoStationaryReviewSpritesPerRoom()
        {
            Scene scene = EditorSceneManager.OpenScene(
                StationaryEnemyPresentationBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                AssertReviewPlacement(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        [Test]
        public void InMemoryRebuildTwice_PreservesExactlyTheSameReviewInstances()
        {
            Scene scene = EditorSceneManager.OpenScene(
                StationaryEnemyPresentationBuilder.ScenePath, OpenSceneMode.Additive);
            try
            {
                StationaryEnemyPresentationBuilder.PlaceReviewInstances(scene);
                string[] first = Snapshot(scene);
                StationaryEnemyPresentationBuilder.PlaceReviewInstances(scene);
                string[] second = Snapshot(scene);
                CollectionAssert.AreEqual(first, second);
                AssertReviewPlacement(scene);
            }
            finally
            {
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        private static string[] Snapshot(Scene scene)
        {
            GameObject[] roots = scene.GetRootGameObjects()
                .Where(root => root.name == StationaryEnemyPresentationBuilder.ReviewRootName).ToArray();
            Assert.AreEqual(1, roots.Length);
            return roots[0].GetComponentsInChildren<StationaryEnemyPresentation>()
                .Select(enemy => $"{enemy.transform.parent.name}/{enemy.name}:" +
                                 $"{enemy.Archetype}/{enemy.Facing}/{enemy.transform.position}/" +
                                 $"{AssetDatabase.GetAssetPath(enemy.GetComponent<SpriteRenderer>().sprite)}")
                .OrderBy(value => value, StringComparer.Ordinal).ToArray();
        }

        private static void AssertReviewPlacement(Scene scene)
        {
            GameObject[] roots = scene.GetRootGameObjects()
                .Where(root => root.name == StationaryEnemyPresentationBuilder.ReviewRootName).ToArray();
            Assert.AreEqual(1, roots.Length);
            GameObject root = roots[0];
            Assert.AreEqual(5, root.transform.childCount);
            StationaryEnemyPresentation[] enemies = root.GetComponentsInChildren<StationaryEnemyPresentation>();
            Assert.AreEqual(10, enemies.Length);
            foreach (RoomId room in Enum.GetValues(typeof(RoomId)))
            {
                Transform group = root.transform.Find(room.ToString());
                Assert.IsNotNull(group);
                Assert.AreEqual(2, group.childCount);
                foreach (StationaryEnemyArchetype archetype in Enum.GetValues(typeof(StationaryEnemyArchetype)))
                {
                    StationaryEnemyReviewAnchor anchor = StationaryEnemyReviewPlacement.Anchors.Single(
                        candidate => candidate.Room == room && candidate.Archetype == archetype);
                    StationaryEnemyPresentation enemy = group.GetComponentsInChildren<StationaryEnemyPresentation>()
                        .Single(candidate => candidate.Archetype == archetype);
                    Assert.AreEqual(anchor.GroundPosition, enemy.transform.position);
                    Assert.AreEqual(anchor.Facing, enemy.Facing);
                    Assert.AreEqual(0, enemy.GetComponentsInChildren<Collider>().Length);
                    Assert.AreEqual(0, enemy.GetComponentsInChildren<Rigidbody>().Length);
                }
            }
        }
    }
}
