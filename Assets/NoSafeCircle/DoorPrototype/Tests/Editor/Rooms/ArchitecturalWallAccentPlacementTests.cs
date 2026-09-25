using System.Collections.Generic;
using System.Linq;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    /// <summary>NSC-120 AC-001/AC-002/AC-003/VAL-001.</summary>
    /// <remarks>
    /// Test classification: pure/component test (BuildRectangularRoomGeometry, Place and
    /// ComputeGroundContactAnchorY are exercised directly) combined with an in-memory
    /// scene-builder test (RuinedEntrySceneBuilder.BuildInMemoryForTests supplies the real
    /// GameplayGeometry colliders AC-003's last sentence requires be left unchanged).
    /// <para>
    /// No committed room's own wall/door layout produces an EndCap under this placement's own
    /// classification: every committed room is a closed rectangle whose doors sit clear of every
    /// corner, so every wall endpoint is either a Corner or a Jamb. AC-001 defines EndCap as "a
    /// wall run terminates without meeting another", which BuildRectangularRoomGeometry -- the
    /// committed room-geometry builder this task delivers -- produces from a door opening as wide
    /// as the whole side it sits on, removing that side's run entirely and leaving the two
    /// adjacent walls' ends unmet. The room below is built through that committed builder for
    /// exactly that reason.
    /// </para>
    /// </remarks>
    public sealed class ArchitecturalWallAccentPlacementTests
    {
        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            RuinedEntrySceneBuilder.BuildInMemoryForTests();
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        // AC-001/AC-003/VAL-001: at least one corner, one jamb and one end cap must actually be
        // placed -- a run that places zero accents for a role fails this rather than passing
        // vacuously -- and each placed accent's ground contact and horizontal footprint must hold
        // the relations AC-003 requires. VAL-001's GameplayGeometry invariance is proven against
        // the real colliders the committed RuinedEntrySceneBuilder produces in SetUp.
        [Test]
        public void Place_ProducesEachRoleWithGroundContactInsideItsOwnRunAndLeavesGameplayGeometryUnchanged()
        {
            const float floorY = 0f;
            Bounds roomBounds = new Bounds(new Vector3(6f, 0f, 6f), new Vector3(12f, 0f, 12f));
            var doorOpenings = new List<WallAccentDoorOpening>
            {
                new WallAccentDoorOpening(WallSide.North, 6f, 4f),
                new WallAccentDoorOpening(WallSide.South, 6f, 12f)
            };
            WallAccentRoomGeometry geometry =
                ArchitecturalWallAccentPlacement.BuildRectangularRoomGeometry(roomBounds, floorY, doorOpenings);

            List<Bounds> gameplayGeometryBefore = SnapshotGameplayGeometryColliderBounds();

            GameObject accentParent = new GameObject("NSC120WallAccentPlacementTestParent");
            IReadOnlyList<PlacedWallAccent> placed =
                ArchitecturalWallAccentPlacement.Place(accentParent.transform, geometry);

            Assert.Greater(placed.Count(accent => accent.Role == WallAccentRole.Corner), 0,
                "Expected at least one Corner accent to actually be placed.");
            Assert.Greater(placed.Count(accent => accent.Role == WallAccentRole.Jamb), 0,
                "Expected at least one Jamb accent to actually be placed.");
            Assert.Greater(placed.Count(accent => accent.Role == WallAccentRole.EndCap), 0,
                "Expected at least one EndCap accent to actually be placed.");

            foreach (PlacedWallAccent accent in placed)
            {
                AssertGroundContactAndFootprint(accent, floorY);
            }

            AssertGameplayGeometryColliderBoundsUnchanged(gameplayGeometryBefore);
        }

        // AC-002: reading the sprite's own pivot and bounds at placement time -- rather than
        // assuming a bottom-centre pivot -- must keep producing the same rendered ground contact
        // whether the sprite currently imports with its committed non-zero vertical pivot or with
        // a corrected pivot of zero supplied to the same derivation.
        [Test]
        public void ComputeGroundContactAnchorY_ProducesIdenticalGroundContactForActualAndZeroVerticalPivot()
        {
            const float floorY = 3.25f;
            Sprite committedCornerSprite =
                AssetDatabase.LoadAssetAtPath<Sprite>(ArchitecturalWallAccentPlacement.CornerSpritePath);
            Assert.IsNotNull(committedCornerSprite,
                "Requires the committed sprite at " + ArchitecturalWallAccentPlacement.CornerSpritePath);

            float normalizedPivotX = committedCornerSprite.pivot.x / committedCornerSprite.rect.width;
            Sprite zeroVerticalPivotSprite = Sprite.Create(
                committedCornerSprite.texture,
                committedCornerSprite.rect,
                new Vector2(normalizedPivotX, 0f),
                committedCornerSprite.pixelsPerUnit);
            zeroVerticalPivotSprite.hideFlags = HideFlags.HideAndDontSave;
            try
            {
                float actualAnchorY =
                    ArchitecturalWallAccentPlacement.ComputeGroundContactAnchorY(committedCornerSprite, floorY);
                float zeroPivotAnchorY =
                    ArchitecturalWallAccentPlacement.ComputeGroundContactAnchorY(zeroVerticalPivotSprite, floorY);

                float actualGroundContact = actualAnchorY + committedCornerSprite.bounds.min.y;
                float zeroPivotGroundContact = zeroPivotAnchorY + zeroVerticalPivotSprite.bounds.min.y;

                Assert.That(actualGroundContact, Is.EqualTo(floorY).Within(0.01f),
                    "The committed pivot must still land on the wall run's floor plane.");
                Assert.That(zeroPivotGroundContact, Is.EqualTo(floorY).Within(0.01f),
                    "A corrected zero pivot must still land on the wall run's floor plane.");
                Assert.That(actualGroundContact, Is.EqualTo(zeroPivotGroundContact).Within(0.01f),
                    "Placement must produce identical ground contact whether the sprite's committed " +
                    "pivot or a corrected pivot of zero is supplied to the same derivation.");
            }
            finally
            {
                Object.DestroyImmediate(zeroVerticalPivotSprite);
            }
        }

        private static void AssertGroundContactAndFootprint(PlacedWallAccent accent, float floorY)
        {
            SpriteRenderer renderer = accent.Instance.GetComponent<SpriteRenderer>();
            Assert.IsNotNull(renderer, accent.Role + " accent must carry a SpriteRenderer.");
            Bounds worldBounds = renderer.bounds;

            Assert.That(worldBounds.min.y, Is.EqualTo(floorY).Within(0.01f),
                accent.Role + " accent's rendered ground contact must equal its wall run's floor plane.");

            if (accent.Run.RunsAlongX)
            {
                float extentMinX = Mathf.Min(accent.Run.Start.x, accent.Run.End.x);
                float extentMaxX = Mathf.Max(accent.Run.Start.x, accent.Run.End.x);
                Assert.GreaterOrEqual(worldBounds.min.x, extentMinX - 0.01f,
                    accent.Role + " accent footprint must stay inside its own wall run's X extent.");
                Assert.LessOrEqual(worldBounds.max.x, extentMaxX + 0.01f,
                    accent.Role + " accent footprint must stay inside its own wall run's X extent.");
            }
            else
            {
                float extentMinZ = Mathf.Min(accent.Run.Start.z, accent.Run.End.z);
                float extentMaxZ = Mathf.Max(accent.Run.Start.z, accent.Run.End.z);
                Assert.GreaterOrEqual(worldBounds.min.z, extentMinZ - 0.01f,
                    accent.Role + " accent footprint must stay inside its own wall run's Z extent.");
                Assert.LessOrEqual(worldBounds.max.z, extentMaxZ + 0.01f,
                    accent.Role + " accent footprint must stay inside its own wall run's Z extent.");
            }
        }

        private static List<Bounds> SnapshotGameplayGeometryColliderBounds()
        {
            Transform geometry = GameObject.Find("Room_RuinedEntry/GameplayGeometry")?.transform;
            Assert.IsNotNull(geometry, "Expected Room_RuinedEntry/GameplayGeometry from the committed room builder.");
            return geometry.GetComponentsInChildren<BoxCollider>(true)
                .Select(collider => collider.bounds)
                .ToList();
        }

        private static void AssertGameplayGeometryColliderBoundsUnchanged(List<Bounds> before)
        {
            List<Bounds> after = SnapshotGameplayGeometryColliderBounds();
            Assert.AreEqual(before.Count, after.Count,
                "Wall accent placement must not add or remove any GameplayGeometry collider.");
            for (int index = 0; index < before.Count; index++)
            {
                Assert.AreEqual(before[index].center, after[index].center,
                    "Wall accent placement must not move any GameplayGeometry collider.");
                Assert.AreEqual(before[index].size, after[index].size,
                    "Wall accent placement must not resize any GameplayGeometry collider.");
            }
        }
    }
}
