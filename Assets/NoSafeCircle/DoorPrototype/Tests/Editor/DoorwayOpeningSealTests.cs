using System.Linq;
using System.Reflection;
using NUnit.Framework;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.World;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    // NSC-097 VAL-001/VAL-002 (Edit Mode half): builds the doorway through
    // DoorPrototypeSceneBuilder's existing non-saving in-memory seam (BuildInMemoryForTests)
    // and proves two independent things against that one built door:
    //
    //  1. AC-001: the doorway blocker's span is derived from the door's own authored opening
    //     width rather than a hard-coded literal, and while enabled it blocks every ray across
    //     the FULL opening - including lateral offsets a 2-unit blocker never covered - at
    //     several heights and from both sides; while disabled, the identical rays pass.
    //  2. AC-002: DoorStateSpriteBinder binds exactly the four DoorPassabilityState-reachable
    //     bonestone sprites (never damaged/opening/broken), each imported as a real Sprite at
    //     the project's 64 pixels-per-unit convention, and the final-door skin only ever
    //     appears while that specific door is closed.
    //
    // The two simple gameplay wall cubes this in-memory seam also builds (BuildWalls) are a
    // lightweight stand-in with their own narrower physical gap; they do not represent the
    // authored 3-unit doorway opening AC-001 measures against (that geometry only exists in the
    // composed dungeon rooms, exercised by the companion Play Mode fixture). Their colliders are
    // disabled before raycasting so the doorway blocker is the only occluder under test here.
    public sealed class DoorwayOpeningSealTests
    {
        private const string DoorArtSourceFolder = "Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source";
        private const string SealedSpriteAssetPath = DoorArtSourceFolder + "/door_bonestone_sealed_S_000.png";
        private const string LockedSpriteAssetPath = DoorArtSourceFolder + "/door_bonestone_locked_S_000.png";
        private const string OpenSpriteAssetPath = DoorArtSourceFolder + "/door_bonestone_open_S_000.png";
        private const string FinalSpriteAssetPath = DoorArtSourceFolder + "/door_bonestone_final_S_000.png";

        // VAL-001: fractions of the blocker's own current half-width. 0.95 sits well outside the
        // former hard-coded blocker's half-width (1.0) whenever the authored opening is wider
        // than 2 units (measured default: 3), which is exactly the previously open sightline.
        private static readonly float[] LateralOffsetFractions = { -0.95f, -0.4f, 0f, 0.4f, 0.95f };
        private static readonly float[] HeightFractions = { -0.9f, 0f, 0.9f };

        [SetUp]
        public void SetUp()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [TearDown]
        public void TearDown()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        [Test]
        public void DoorwayBlocker_SpanIsDerivedFromAuthoredOpeningWidth_NotHardcodedLiteralTwo()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorRoot = GameObject.Find("DoorRoot");
            var blocker = doorRoot.transform.Find("DoorVisual").GetComponent<BoxCollider>();
            var passability = doorRoot.GetComponent<DoorEnemyPassability>();
            Assert.IsNotNull(blocker);
            Assert.IsNotNull(passability);

            var obstacleSizeField = typeof(DoorEnemyPassability).GetField(
                "obstacleSize", BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(obstacleSizeField, "Expected a private 'obstacleSize' field on DoorEnemyPassability.");
            var authoredOpeningWidth = ((Vector3)obstacleSizeField.GetValue(passability)).x;

            Assert.AreEqual(authoredOpeningWidth, blocker.size.x, 0.001f,
                "AC-001: the doorway blocker's width must be derived from this door's own authored " +
                "opening width (DoorEnemyPassability.obstacleSize.x), not authored a second time.");
            Assert.Greater(Mathf.Abs(blocker.size.x - 2f), 0.01f,
                "AC-001: the blocker must not remain (or become) hard-coded to the old literal 2-unit " +
                "footprint; a later change to the authored opening must not silently reopen the jamb gap.");
        }

        [Test]
        public void DoorwayBlockerEnabled_BlocksRaysAcrossFullOpeningWidthAndHeight_FromBothSides()
        {
            var blocker = BuildDoorwayForRaycastTest(out var center, out var halfWidth, out var halfHeight);
            Assert.IsTrue(blocker.enabled, "Test setup expects the door to still be sealed (blocker enabled).");

            Assert.GreaterOrEqual(LateralOffsetFractions.Length, 5,
                "A single centre-line ray is explicitly insufficient (that is how ten open sightlines " +
                "survived every existing gate); this fixture must sweep at least five lateral offsets.");
            Assert.GreaterOrEqual(HeightFractions.Length, 3);

            foreach (var offsetFraction in LateralOffsetFractions)
            {
                foreach (var heightFraction in HeightFractions)
                {
                    var x = center.x + offsetFraction * halfWidth;
                    var y = center.y + heightFraction * halfHeight;

                    Assert.IsTrue(RaycastHits(new Vector3(x, y, center.z - 1f), Vector3.forward, 2f),
                        $"Expected the enabled doorway blocker to stop a ray from the near side at " +
                        $"offset={offsetFraction}, height={heightFraction}.");
                    Assert.IsTrue(RaycastHits(new Vector3(x, y, center.z + 1f), Vector3.back, 2f),
                        $"Expected the enabled doorway blocker to stop a ray from the far side at " +
                        $"offset={offsetFraction}, height={heightFraction}.");
                }
            }
        }

        [Test]
        public void DoorwayBlockerDisabled_AllowsRaysAcrossFullOpeningWidthAndHeight_FromBothSides()
        {
            var blocker = BuildDoorwayForRaycastTest(out var center, out var halfWidth, out var halfHeight);
            blocker.enabled = false;
            Physics.SyncTransforms();

            foreach (var offsetFraction in LateralOffsetFractions)
            {
                foreach (var heightFraction in HeightFractions)
                {
                    var x = center.x + offsetFraction * halfWidth;
                    var y = center.y + heightFraction * halfHeight;

                    Assert.IsFalse(RaycastHits(new Vector3(x, y, center.z - 1f), Vector3.forward, 2f),
                        $"Expected a disabled doorway blocker to let a ray from the near side pass at " +
                        $"offset={offsetFraction}, height={heightFraction}.");
                    Assert.IsFalse(RaycastHits(new Vector3(x, y, center.z + 1f), Vector3.back, 2f),
                        $"Expected a disabled doorway blocker to let a ray from the far side pass at " +
                        $"offset={offsetFraction}, height={heightFraction}.");
                }
            }
        }

        [Test]
        public void DoorSpriteBinder_BindsFourApprovedBonestoneSprites_ImportedAsSpritesAtSixtyFourPixelsPerUnit()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorRoot = GameObject.Find("DoorRoot");
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            Assert.IsNotNull(binder, "Expected a DoorStateSpriteBinder on the generated DoorRoot.");

            var doorSpriteRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite").GetComponent<SpriteRenderer>();
            Assert.IsNotNull(doorSpriteRenderer, "Expected a SpriteRenderer on the generated DoorVisual/DoorSprite.");

            var expectedByField = new (string FieldName, string AssetPath)[]
            {
                ("sealedSprite", SealedSpriteAssetPath),
                ("lockedSprite", LockedSpriteAssetPath),
                ("openSprite", OpenSpriteAssetPath),
                ("finalSprite", FinalSpriteAssetPath),
            };

            foreach (var (fieldName, expectedPath) in expectedByField)
            {
                var sprite = GetPrivateSprite(binder, fieldName);
                Assert.IsNotNull(sprite, $"'{fieldName}' must be bound to an actual imported Sprite, " +
                    "not left null (which would leave the placeholder rectangle behind).");
                Assert.AreEqual(expectedPath, AssetDatabase.GetAssetPath(sprite),
                    $"'{fieldName}' must reference the approved art asset at '{expectedPath}', not a " +
                    "placeholder or differently named asset.");

                var importer = AssetImporter.GetAtPath(expectedPath) as TextureImporter;
                Assert.IsNotNull(importer, expectedPath);
                Assert.AreEqual(TextureImporterType.Sprite, importer.textureType, expectedPath);
                Assert.AreEqual(64f, importer.spritePixelsPerUnit, expectedPath);
            }

            var sealedSprite = GetPrivateSprite(binder, "sealedSprite");
            Assert.AreSame(sealedSprite, doorSpriteRenderer.sprite,
                "A freshly built door starts sealed and must render the approved sealed bonestone sprite, " +
                "not the superseded placeholder rectangle.");
        }

        [Test]
        public void DoorSpriteBinder_NeverReferencesDamagedOpeningOrBrokenSprites()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var doorRoot = GameObject.Find("DoorRoot");
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            Assert.IsNotNull(binder);

            var spriteFields = typeof(DoorStateSpriteBinder)
                .GetFields(BindingFlags.NonPublic | BindingFlags.Instance)
                .Where(field => field.FieldType == typeof(Sprite))
                .ToArray();

            Assert.AreEqual(4, spriteFields.Length,
                "DoorStateSpriteBinder must expose exactly the four DoorPassabilityState-reachable sprite " +
                "slots (sealed/locked/open, plus the isFinalDoor closed-leaf skin) - binding a sprite no " +
                "state can reach would ship a gate that cannot pass.");

            var forbiddenWords = new[] { "damaged", "opening", "broken" };
            foreach (var field in spriteFields)
            {
                var sprite = (Sprite)field.GetValue(binder);
                Assert.IsNotNull(sprite, field.Name);
                var assetPath = AssetDatabase.GetAssetPath(sprite).ToLowerInvariant();

                foreach (var forbiddenWord in forbiddenWords)
                {
                    Assert.IsFalse(assetPath.Contains(forbiddenWord),
                        $"'{field.Name}' must not reference a {forbiddenWord} sprite ('{assetPath}'); no " +
                        "code path can reach that art state yet.");
                }
            }
        }

        [Test]
        public void FinalDoor_Opened_RendersOpenSprite_NeverFinalSprite()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var doorRoot = GameObject.Find("DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var doorSpriteRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite").GetComponent<SpriteRenderer>();
            SetIsFinalDoor(door, true);

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);

            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door.");
            Assert.AreSame(GetPrivateSprite(binder, "openSprite"), doorSpriteRenderer.sprite,
                "AC-002: the win-condition door must show the open sprite once opened, even though it is " +
                "the final door - the closed-leaf gold-glow skin must never be shown for an open passage.");
            Assert.AreNotSame(GetPrivateSprite(binder, "finalSprite"), doorSpriteRenderer.sprite);
        }

        [Test]
        public void FinalDoor_LockedAfterForwardCrossing_RendersFinalSprite()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var doorRoot = GameObject.Find("DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var doorSpriteRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite").GetComponent<SpriteRenderer>();
            SetIsFinalDoor(door, true);

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            var playerCollider = GameObject.Find("Player").GetComponent<CharacterController>();
            InvokeForwardCrossingTriggerEnter(door, playerCollider);

            Assert.IsTrue(door.IsLocked, "Test setup must actually lock the door.");
            Assert.AreSame(GetPrivateSprite(binder, "finalSprite"), doorSpriteRenderer.sprite,
                "AC-002: a closed final door shows the gold-glow closed-leaf skin, not the generic locked " +
                "sprite.");
        }

        [Test]
        public void NonFinalDoor_LockedAfterForwardCrossing_RendersLockedSprite_NeverFinalSprite()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var doorRoot = GameObject.Find("DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var doorSpriteRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite").GetComponent<SpriteRenderer>();
            Assert.IsFalse(door.IsFinalDoor, "Test setup expects a non-final door.");

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before crossing.");

            var playerCollider = GameObject.Find("Player").GetComponent<CharacterController>();
            InvokeForwardCrossingTriggerEnter(door, playerCollider);

            Assert.IsTrue(door.IsLocked, "Test setup must actually lock the door.");
            Assert.AreSame(GetPrivateSprite(binder, "lockedSprite"), doorSpriteRenderer.sprite);
            Assert.AreNotSame(GetPrivateSprite(binder, "finalSprite"), doorSpriteRenderer.sprite,
                "AC-002: a door with isFinalDoor false must never render the closed-leaf gold-glow skin.");
        }

        [Test]
        public void NonFinalDoor_ResetCompleted_RendersSealedSprite_NeverFinalSprite()
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();
            var doorRoot = GameObject.Find("DoorRoot");
            var door = doorRoot.GetComponent<DoorInteractable>();
            var binder = doorRoot.GetComponent<DoorStateSpriteBinder>();
            var doorSpriteRenderer = doorRoot.transform.Find("DoorVisual/DoorSprite").GetComponent<SpriteRenderer>();
            Assert.IsFalse(door.IsFinalDoor, "Test setup expects a non-final door.");

            door.StartInteraction();
            door.Tick(door.Duration + 0.1f);
            Assert.IsTrue(door.IsOpen, "Test setup must actually open the door before reset.");
            Assert.AreSame(GetPrivateSprite(binder, "openSprite"), doorSpriteRenderer.sprite,
                "Test setup must actually change the rendered sprite away from sealed before reset.");

            door.ResetDoor();

            Assert.IsFalse(door.IsOpen);
            Assert.AreSame(GetPrivateSprite(binder, "sealedSprite"), doorSpriteRenderer.sprite);
            Assert.AreNotSame(GetPrivateSprite(binder, "finalSprite"), doorSpriteRenderer.sprite,
                "AC-002: a door with isFinalDoor false must never render the closed-leaf gold-glow skin.");
        }

        // Builds the doorway through the non-saving in-memory seam, then disables the two simple
        // gameplay wall cubes (see the class-level comment) so the doorway blocker is the only
        // possible occluder for the raycast sweeps above.
        private static BoxCollider BuildDoorwayForRaycastTest(out Vector3 center, out float halfWidth, out float halfHeight)
        {
            DoorPrototypeSceneBuilder.BuildInMemoryForTests();

            var leftWallCollider = GameObject.Find("Walls/WallLeft")?.GetComponent<Collider>();
            var rightWallCollider = GameObject.Find("Walls/WallRight")?.GetComponent<Collider>();
            Assert.IsNotNull(leftWallCollider);
            Assert.IsNotNull(rightWallCollider);
            leftWallCollider.enabled = false;
            rightWallCollider.enabled = false;

            var doorRoot = GameObject.Find("DoorRoot");
            var blocker = doorRoot.transform.Find("DoorVisual").GetComponent<BoxCollider>();
            Assert.IsNotNull(blocker);

            Physics.SyncTransforms();
            center = blocker.bounds.center;
            halfWidth = blocker.size.x / 2f;
            halfHeight = blocker.size.y / 2f;
            return blocker;
        }

        private static bool RaycastHits(Vector3 origin, Vector3 direction, float maxDistance)
        {
            return Physics.Raycast(origin, direction, maxDistance, Physics.DefaultRaycastLayers,
                QueryTriggerInteraction.Ignore);
        }

        private static Sprite GetPrivateSprite(object target, string fieldName)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(field, $"Expected a private Sprite field named '{fieldName}' on {target.GetType().Name}.");
            return (Sprite)field.GetValue(target);
        }

        private static void SetIsFinalDoor(DoorInteractable door, bool value)
        {
            var serialized = new SerializedObject(door);
            serialized.FindProperty("isFinalDoor").boolValue = value;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static void InvokeForwardCrossingTriggerEnter(DoorInteractable target, Collider other)
        {
            var method = target.GetType().GetMethod("HandleForwardCrossingTriggerEnter",
                BindingFlags.NonPublic | BindingFlags.Instance);
            Assert.IsNotNull(method,
                "Expected a private HandleForwardCrossingTriggerEnter(Collider) method on DoorInteractable.");
            method.Invoke(target, new object[] { other });
        }
    }
}
