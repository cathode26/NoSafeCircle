using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor.World;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using NoSafeCircle.DoorPrototype.Editor.Rooms;
using NoSafeCircle.DoorPrototype.World;
using NoSafeCircle.DoorPrototype.World.Rooms;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.Rooms
{
    // NSC-045. THESE ASSERTIONS WERE WRONG UNTIL 2026-09-25 AND THAT IS WHY THE TASK READ
    // CONFORMANT AGAINST A CONTRACT IT DID NOT SATISFY. The file asserted RoomBounds -10/+10 while
    // AC-001 has required -12/+12 since revision 4; it asserted shelf sizes that no longer matched
    // AC-001; it never mentioned West Archive Bay W-1, East Archive Bay E-1 or the Archive
    // Reliquary in any spelling; and AssertBounds required each visual to EQUAL its collider,
    // which directly contradicts AC-001/AC-003's separate 1.0-unit visual height. Code, test and
    // delivery record agreed with each other and all three disagreed with the contract, so a
    // revalidation run would have re-approved the false delivery rather than catching it.
    //
    // Every expectation below is now derived from the contract, and the room-relative ones are
    // derived from RoomBounds rather than written as literals so widening the room cannot leave
    // this file quietly asserting stale numbers again.
    public class BoneArchiveSceneTests
    {
        [Test] // AC-001: the authored room measurements match the approved widened blockout.
        public void Layout_ContainsApprovedShellShelvesAndDoors()
        {
            Assert.That(BoneArchiveLayout.RoomBounds.min, Is.EqualTo(new Vector3(-12f, 0f, 0f)),
                "AC-001 requires a 24-by-20 room with walkable bounds X [-12,+12], Z [0,20], and "
                + "RoomSceneCatalog already declares exactly that for Bone Archive.");
            Assert.That(BoneArchiveLayout.RoomBounds.max, Is.EqualTo(new Vector3(12f, 0f, 20f)));

            AssertFootprint("Shelf A", BoneArchiveLayout.ShelfA, -7.5f, -6f, 4f, 15f, 2.5f);
            AssertFootprint("Shelf B", BoneArchiveLayout.ShelfB, -2.5f, -1f, 4f, 13.5f, 2.5f);
            AssertFootprint("Shelf C", BoneArchiveLayout.ShelfC, 2.5f, 4f, 5.5f, 15.5f, 2.5f);
            AssertFootprint("BA-1", BoneArchiveLayout.CollapsedFurnitureBA1, -1f, 0f, 9f, 11f, 1.25f);
            AssertFootprint("W-1", BoneArchiveLayout.WestArchiveBayW1, -11.75f, -10.5f, 7f, 16f, 2.5f);
            AssertFootprint("E-1", BoneArchiveLayout.EastArchiveBayE1, 7f, 11.75f, 5.5f, 13.5f, 2.5f);

            Assert.That(BoneArchiveLayout.D1, Is.EqualTo(new Vector3(0f, 0f, 0f)));
            Assert.That(BoneArchiveLayout.D2, Is.EqualTo(new Vector3(6f, 0f, 20f)));
        }

        [Test] // AC-003: the reliquary is a landmark, not an obstacle.
        public void Layout_PlacesArchiveReliquaryAgainstNorthWallOutsideTheD2Opening()
        {
            Bounds reliquary = BoneArchiveLayout.ArchiveReliquary;
            AssertFootprint("Archive Reliquary", reliquary, -2f, 2f, 18.75f, 19.75f,
                BoneArchiveLayout.ShelfVisualHeight);

            Assert.That(reliquary.max.z, Is.LessThanOrEqualTo(BoneArchiveLayout.RoomBounds.max.z),
                "The reliquary sits against the north wall and must stay inside the room.");

            // AC-003: it must not intrude on the D2 staging rectangle. D2's clear opening spans
            // DoorWidth centred on D2.x, so the reliquary footprint must not overlap that span.
            float openingMinX = BoneArchiveLayout.D2.x - (BoneArchiveLayout.DoorWidth * 0.5f);
            float openingMaxX = BoneArchiveLayout.D2.x + (BoneArchiveLayout.DoorWidth * 0.5f);
            bool overlapsOpening = reliquary.max.x > openingMinX && reliquary.min.x < openingMaxX;
            Assert.That(overlapsOpening, Is.False,
                "The Archive Reliquary must stay clear of the D2 staging rectangle, but its X span ["
                + reliquary.min.x + "," + reliquary.max.x + "] overlaps the D2 opening ["
                + openingMinX + "," + openingMaxX + "].");
        }

        [Test] // AC-002: deliberate pinch, ordinary lanes, and both bypass narrowings.
        public void Layout_PreservesLaneWidthsAndBypasses()
        {
            Assert.That(BoneArchiveLayout.ClearWidthBetween(BoneArchiveLayout.ShelfA, BoneArchiveLayout.ShelfB),
                Is.EqualTo(3.5f).Within(0.001f));
            Assert.That(BoneArchiveLayout.ClearWidthBetween(BoneArchiveLayout.ShelfB, BoneArchiveLayout.ShelfC),
                Is.EqualTo(3.5f).Within(0.001f));

            // The BA-1 pinch is the tactical narrowing and sits exactly at the minimum.
            Assert.That(BoneArchiveLayout.ShelfC.min.x - BoneArchiveLayout.CollapsedFurnitureBA1.max.x,
                Is.EqualTo(BoneArchiveLayout.MinLaneWidth).Within(0.001f));

            // BOTH BYPASS NARROWINGS, which is what the archive bays are for. Each is measured
            // against the bay rather than against the wall, because the bay is what narrows it.
            float westBypass = BoneArchiveLayout.ClearWidthBetween(
                BoneArchiveLayout.WestArchiveBayW1, BoneArchiveLayout.ShelfA);
            float eastBypass = BoneArchiveLayout.ClearWidthBetween(
                BoneArchiveLayout.ShelfC, BoneArchiveLayout.EastArchiveBayE1);
            Assert.That(westBypass, Is.GreaterThanOrEqualTo(BoneArchiveLayout.MinLaneWidth),
                "The west bypass between W-1 and Shelf A is " + westBypass + ".");
            Assert.That(eastBypass, Is.GreaterThanOrEqualTo(BoneArchiveLayout.MinLaneWidth),
                "The east bypass between Shelf C and E-1 is " + eastBypass + ".");

            // The bays are wall-side clusters, so each must sit inside its own room edge.
            Assert.That(BoneArchiveLayout.WestArchiveBayW1.min.x,
                Is.GreaterThanOrEqualTo(BoneArchiveLayout.RoomBounds.min.x));
            Assert.That(BoneArchiveLayout.EastArchiveBayE1.max.x,
                Is.LessThanOrEqualTo(BoneArchiveLayout.RoomBounds.max.x));

            Assert.That(BoneArchiveLayout.MinLaneWidth, Is.EqualTo(2.5f));
        }

        [Test] // AC-001: D2 is offset, so the north wall segments must straddle X=+6.
        public void Builder_OffsetsNorthOpeningToD2()
        {
            BoneArchiveSceneBuilder.BuildInMemoryForTests();

            try
            {
                GameObject west = GameObject.Find("NorthWallWestVisual");
                GameObject east = GameObject.Find("NorthWallEastVisual");

                Assert.That(west, Is.Not.Null);
                Assert.That(east, Is.Not.Null);

                // Derived from RoomBounds and DoorWidth rather than copied literals, so widening
                // the room moves these expectations with it.
                float roomMinX = BoneArchiveLayout.RoomBounds.min.x;
                float roomMaxX = BoneArchiveLayout.RoomBounds.max.x;
                float halfOpening = BoneArchiveLayout.DoorWidth * 0.5f;
                float westLength = BoneArchiveLayout.D2.x - halfOpening - roomMinX;
                float eastLength = roomMaxX - BoneArchiveLayout.D2.x - halfOpening;

                Assert.That(west.transform.localScale.x, Is.EqualTo(westLength).Within(0.001f));
                Assert.That(west.transform.position.x,
                    Is.EqualTo(roomMinX + (westLength * 0.5f)).Within(0.001f));
                Assert.That(east.transform.localScale.x, Is.EqualTo(eastLength).Within(0.001f));
                Assert.That(east.transform.position.x,
                    Is.EqualTo(roomMaxX - (eastLength * 0.5f)).Within(0.001f));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        [Test] // VAL-001: visible blockouts and gameplay colliders are separate twins.
        public void Builder_SeparatesApprovedVisualAndGameplayFootprints()
        {
            BoneArchiveSceneBuilder.BuildInMemoryForTests();

            try
            {
                GameObject visuals = GameObject.Find("Room_BoneArchive/Visuals");
                GameObject gameplay = GameObject.Find("Room_BoneArchive/GameplayGeometry");

                Assert.That(visuals, Is.Not.Null);
                Assert.That(gameplay, Is.Not.Null);
                Assert.That(visuals.GetComponentsInChildren<Renderer>(), Has.Length.GreaterThan(0));
                Assert.That(visuals.GetComponentsInChildren<Collider>(), Is.Empty);
                Assert.That(gameplay.GetComponentsInChildren<Renderer>(), Is.Empty);

                // Floor, six blockouts, two side walls and four door-wall segments. The Archive
                // Reliquary deliberately contributes NONE: it is non-colliding by contract.
                Assert.That(gameplay.GetComponentsInChildren<BoxCollider>(), Has.Length.EqualTo(13));

                AssertBlockout("Shelf A", BoneArchiveLayout.ShelfA, BoneArchiveLayout.ShelfVisualHeight);
                AssertBlockout("Shelf B", BoneArchiveLayout.ShelfB, BoneArchiveLayout.ShelfVisualHeight);
                AssertBlockout("Shelf C", BoneArchiveLayout.ShelfC, BoneArchiveLayout.ShelfVisualHeight);
                AssertBlockout("West Archive Bay W-1", BoneArchiveLayout.WestArchiveBayW1,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertBlockout("East Archive Bay E-1", BoneArchiveLayout.EastArchiveBayE1,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertBlockout("Collapsed Furniture BA-1", BoneArchiveLayout.CollapsedFurnitureBA1,
                    BoneArchiveLayout.CollapsedFurnitureHeight);

                // AC-003: the reliquary has a visual and NO collision twin at all.
                GameObject reliquaryVisual = GameObject.Find("Archive ReliquaryVisual");
                Assert.That(reliquaryVisual, Is.Not.Null,
                    "AC-003 requires an Archive Reliquary blockout against the north wall.");
                Assert.That(GameObject.Find("Archive ReliquaryCollision"), Is.Null,
                    "The Archive Reliquary must be non-colliding; a collision twin would narrow "
                    + "the north lane the contract requires it to leave clear.");
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        [Test] // Downstream composition gate: the committed source scene satisfies RoomSceneComposer.
        public void CommittedScene_ValidatesForComposition()
        {
            Scene scene = EditorSceneManager.OpenScene(BoneArchiveSceneBuilder.ScenePath, OpenSceneMode.Single);

            try
            {
                RoomSceneComposer.RoomValidationResult result = RoomSceneComposer.ValidateOpenRoomScene(
                    RoomId.BoneArchive,
                    scene,
                    FindRoomEntry(RoomId.BoneArchive),
                    RoomSceneCatalog.CreateCanonicalDoors());

                CollectionAssert.IsEmpty(result.Errors, string.Join("\n", result.Errors));
                Assert.That(result.DoorAnchors, Has.Count.EqualTo(2));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        // VAL-001 asks for COMMITTED-SCENE conformance: open the exact committed
        // BoneArchive.unity, scope every lookup to that scene, verify the AC-001 footprints and
        // heights there, and close without saving. The in-memory builder test above cannot serve
        // this clause - it proves what the builder WOULD produce, not what is committed, and the
        // two disagreed for weeks without anything noticing.
        [Test]
        public void CommittedScene_ContainsEveryApprovedBlockoutAtItsAuthoredFootprint()
        {
            Scene scene = EditorSceneManager.OpenScene(BoneArchiveSceneBuilder.ScenePath, OpenSceneMode.Single);

            try
            {
                AssertCommittedBlockout(scene, "Shelf A", BoneArchiveLayout.ShelfA,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertCommittedBlockout(scene, "Shelf B", BoneArchiveLayout.ShelfB,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertCommittedBlockout(scene, "Shelf C", BoneArchiveLayout.ShelfC,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertCommittedBlockout(scene, "West Archive Bay W-1", BoneArchiveLayout.WestArchiveBayW1,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertCommittedBlockout(scene, "East Archive Bay E-1", BoneArchiveLayout.EastArchiveBayE1,
                    BoneArchiveLayout.ShelfVisualHeight);
                AssertCommittedBlockout(scene, "Collapsed Furniture BA-1",
                    BoneArchiveLayout.CollapsedFurnitureBA1, BoneArchiveLayout.CollapsedFurnitureHeight);

                // AC-003: present as a visual landmark, and carrying no gameplay collider at all.
                GameObject reliquary = FindInScene(scene, "Archive ReliquaryVisual");
                Assert.That(reliquary, Is.Not.Null,
                    "The committed scene must contain the Archive Reliquary blockout.");
                Assert.That(FindInScene(scene, "Archive ReliquaryCollision"), Is.Null,
                    "The Archive Reliquary must remain non-colliding in the committed scene.");

                Bounds reliquaryBounds = reliquary.GetComponent<Renderer>().bounds;
                Assert.That(reliquaryBounds.min.x,
                    Is.EqualTo(BoneArchiveLayout.ArchiveReliquary.min.x).Within(0.01f));
                Assert.That(reliquaryBounds.max.x,
                    Is.EqualTo(BoneArchiveLayout.ArchiveReliquary.max.x).Within(0.01f));
                Assert.That(reliquaryBounds.min.z,
                    Is.EqualTo(BoneArchiveLayout.ArchiveReliquary.min.z).Within(0.01f));
                Assert.That(reliquaryBounds.max.z,
                    Is.EqualTo(BoneArchiveLayout.ArchiveReliquary.max.z).Within(0.01f));
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        // THE GUARD THAT WAS MISSING, AND THE TEST ABOVE IS WHY IT WAS MISSING. Seven blockout
        // cubes stood in the committed Bone Archive with their renderers enabled, Vincent
        // photographed them in the running game, and the fixture above passed the entire time --
        // it asserts the blockouts are CORRECT (present, at the right footprint, the right
        // height), and a cube that should be invisible is correct by every measure it takes.
        // An assertion that a thing is right cannot notice that the thing should not be drawn.
        //
        // Tilemaps are the visible surface in this room, so the blockout meshes exist only to
        // carry footprints for the layout assertions and must never render. The builder hides
        // them by setting renderer.enabled = false rather than destroying them, precisely so the
        // Renderer.bounds reads above keep working -- which means "hidden" is a property that
        // nothing else in this fixture is able to see.
        //
        // Scoped to activeInHierarchy as well as enabled, because a renderer on a deactivated
        // object draws nothing and counting it would be a false positive.
        [Test]
        public void CommittedScene_LeavesNoBlockoutMeshRendererDrawing()
        {
            Scene scene = EditorSceneManager.OpenScene(BoneArchiveSceneBuilder.ScenePath, OpenSceneMode.Single);

            try
            {
                var drawing = string.Empty;
                var count = 0;

                foreach (GameObject root in scene.GetRootGameObjects())
                {
                    foreach (MeshRenderer renderer in root.GetComponentsInChildren<MeshRenderer>(true))
                    {
                        if (!renderer.enabled || !renderer.gameObject.activeInHierarchy) continue;

                        count++;
                        drawing += (drawing.Length == 0 ? string.Empty : ", ") + renderer.gameObject.name;
                    }
                }

                Assert.AreEqual(0, count,
                    "The committed Bone Archive scene still draws " + count + " MeshRenderer(s): "
                    + drawing + ". Tilemaps are the visible surface here, so every blockout mesh "
                    + "must be hidden in the COMMITTED scene and not merely in what the builder "
                    + "would produce. Re-bake the room scene if the builder is already correct.");
            }
            finally
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            }
        }

        // Same assertions as AssertBlockout, but scoped to the opened committed scene rather than
        // to whatever GameObject.Find happens to reach.
        private static void AssertCommittedBlockout(
            Scene scene, string baseName, Bounds colliderFootprint, float visualHeight)
        {
            GameObject visual = FindInScene(scene, baseName + "Visual");
            GameObject collision = FindInScene(scene, baseName + "Collision");
            Assert.That(visual, Is.Not.Null, baseName + " must exist in the committed scene.");
            Assert.That(collision, Is.Not.Null,
                baseName + " must have a gameplay collider in the committed scene.");

            Bounds rendered = visual.GetComponent<Renderer>().bounds;
            Assert.That(rendered.min.x, Is.EqualTo(colliderFootprint.min.x).Within(0.01f),
                baseName + " committed visual min X.");
            Assert.That(rendered.max.x, Is.EqualTo(colliderFootprint.max.x).Within(0.01f),
                baseName + " committed visual max X.");
            Assert.That(rendered.min.z, Is.EqualTo(colliderFootprint.min.z).Within(0.01f),
                baseName + " committed visual min Z.");
            Assert.That(rendered.max.z, Is.EqualTo(colliderFootprint.max.z).Within(0.01f),
                baseName + " committed visual max Z.");
            Assert.That(rendered.min.y, Is.EqualTo(0f).Within(0.01f),
                baseName + " committed visual must rest on the floor.");
            Assert.That(rendered.max.y, Is.EqualTo(visualHeight).Within(0.01f),
                baseName + " committed visual must span Y [0," + visualHeight + "].");

            Bounds collider = collision.GetComponent<BoxCollider>().bounds;
            Assert.That(collider.min.x, Is.EqualTo(colliderFootprint.min.x).Within(0.01f));
            Assert.That(collider.max.x, Is.EqualTo(colliderFootprint.max.x).Within(0.01f));
            Assert.That(collider.min.z, Is.EqualTo(colliderFootprint.min.z).Within(0.01f));
            Assert.That(collider.max.z, Is.EqualTo(colliderFootprint.max.z).Within(0.01f));
            Assert.That(collider.size.y, Is.EqualTo(colliderFootprint.size.y).Within(0.01f),
                baseName + " committed gameplay collider height.");
        }

        // Scoped to the given scene, so nothing in another loaded scene can satisfy a lookup.
        private static GameObject FindInScene(Scene scene, string name)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                foreach (Transform candidate in root.GetComponentsInChildren<Transform>(true))
                {
                    if (candidate.gameObject.name == name)
                    {
                        return candidate.gameObject;
                    }
                }
            }

            return null;
        }

        // AC-001: asserts a layout constant against the contract's own X/Z range and height,
        // stated as the contract states them rather than as a precomputed centre and size, so a
        // reader can check this line against the contract without doing arithmetic.
        private static void AssertFootprint(
            string label, Bounds actual, float minX, float maxX, float minZ, float maxZ, float height)
        {
            Assert.That(actual.min.x, Is.EqualTo(minX).Within(0.001f), label + " min X.");
            Assert.That(actual.max.x, Is.EqualTo(maxX).Within(0.001f), label + " max X.");
            Assert.That(actual.min.z, Is.EqualTo(minZ).Within(0.001f), label + " min Z.");
            Assert.That(actual.max.z, Is.EqualTo(maxZ).Within(0.001f), label + " max Z.");
            Assert.That(actual.size.y, Is.EqualTo(height).Within(0.001f), label + " height.");
        }

        // VAL-001: the visual shares the collider's X/Z footprint but is its own height and rests
        // on the floor, so its Renderer spans Y [0, visualHeight] while the gameplay collider
        // stays full height. Asserting on Renderer.bounds is what the gate asks for.
        private static void AssertBlockout(string baseName, Bounds colliderFootprint, float visualHeight)
        {
            GameObject visual = GameObject.Find(baseName + "Visual");
            GameObject collision = GameObject.Find(baseName + "Collision");
            Assert.That(visual, Is.Not.Null, baseName + " must have a visual blockout.");
            Assert.That(collision, Is.Not.Null, baseName + " must have a gameplay collider.");

            Bounds rendered = visual.GetComponent<Renderer>().bounds;
            Assert.That(rendered.min.x, Is.EqualTo(colliderFootprint.min.x).Within(0.01f),
                baseName + " visual must share its collider's X footprint.");
            Assert.That(rendered.max.x, Is.EqualTo(colliderFootprint.max.x).Within(0.01f));
            Assert.That(rendered.min.z, Is.EqualTo(colliderFootprint.min.z).Within(0.01f),
                baseName + " visual must share its collider's Z footprint.");
            Assert.That(rendered.max.z, Is.EqualTo(colliderFootprint.max.z).Within(0.01f));
            Assert.That(rendered.min.y, Is.EqualTo(0f).Within(0.01f),
                baseName + " visual must rest on the floor.");
            Assert.That(rendered.max.y, Is.EqualTo(visualHeight).Within(0.01f),
                baseName + " visual must be exactly " + visualHeight + " units high; AC-003 forbids "
                + "choosing a different visual height without a contract revision.");

            Assert.That(collision.GetComponent<BoxCollider>().bounds, Is.EqualTo(colliderFootprint),
                baseName + " gameplay collider must match its authored footprint exactly.");
        }

        private static RoomSceneCatalog.RoomCatalogEntry FindRoomEntry(RoomId roomId)
        {
            foreach (RoomSceneCatalog.RoomCatalogEntry entry in RoomSceneCatalog.CreateCanonicalRooms())
            {
                if (entry.RoomId == roomId)
                {
                    return entry;
                }
            }

            Assert.Fail($"Missing canonical catalog entry for {roomId}.");
            return null;
        }
    }
}
