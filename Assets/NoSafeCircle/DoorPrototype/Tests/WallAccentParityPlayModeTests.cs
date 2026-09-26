using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using Object = UnityEngine.Object;

namespace NoSafeCircle.DoorPrototype.Tests
{
    /// <summary>
    /// Does the runtime world carry the wall accents the committed room scenes hold - per ROLE,
    /// with shared doorways counted once rather than twice?
    /// </summary>
    /// <remarks>
    /// <para>
    /// WHY THIS EXISTS, AND WHY IT IS TEMPORARY. Vincent approved deleting the five committed room
    /// scenes. The question that had to be answered first was whether anything else carries the
    /// accents in them, because the composer rule runs in both directions: a committed scene can
    /// receive art invisibly, and it can equally be the SOLE CARRIER of art, so deleting it removes
    /// something no builder will regenerate and NO TEST WILL FAIL.
    /// </para>
    /// <para>
    /// A PREFAB SWEEP CANNOT ANSWER IT, and one was run and reported "nothing carries them". That is
    /// true and misleading: the OLD path did not keep accents in a prefab either. It generated them
    /// from an EDITOR builder (ArchitecturalWallAccentPlacement.CreateAccent). The NEW path
    /// generates them from a RUNTIME spawner. Neither stores an accent prefab, so a prefab sweep
    /// returns zero for both worlds and cannot distinguish "not carried" from "generated".
    /// </para>
    /// <para>
    /// THE EXPECTATION IS READ FROM THE SCENES, NOT WRITTEN DOWN. The count comes from the very
    /// artifact the new path is replacing, which is a DIFFERENT artifact from the one under test -
    /// the property this project's rules ask for, because an expectation copied from the code it
    /// checks is self-consistent by construction and passes while proving nothing.
    /// </para>
    /// <para>
    /// COUNT THE OBJECTS, NOT THE LINES. Each scene holds one "WallAccents" CONTAINER ROOT beside
    /// its accents, so a grep for "accent" returns 43 across the five scenes while only 38 are
    /// accents. The figure 43 reached CLAUDE.md and a decision record that way, past a control
    /// (m_Name: ZZZNotAThing = 0) that was itself correct - a control proves the query RUNS, never
    /// that it counts the right noun.
    /// </para>
    /// <para>
    /// AND COMPARE PER ROLE, NOT ON THE TOTAL - THIS TEST'S FIRST VERSION GOT THAT WRONG AND
    /// REPORTED A DEFECT THAT DOES NOT EXIST. It asserted runtime 30 against scenes 38 and called
    /// eight accents missing. Per role: corners 20 = 20, end caps 0 = 0, and jambs 10 against 18.
    /// The jamb difference is not a shortfall. The scenes are PER-ROOM, so a doorway in a shared
    /// wall is drawn by BOTH adjoining rooms; the single combined world draws it once. Measured in
    /// the layouts: D1 is in RuinedEntry and BoneArchive, D2 in BoneArchive and ChapelOfAsh, D3 in
    /// ChapelOfAsh and LowerVault, D4 in LowerVault and FinalRoom, D5 in FinalRoom alone - four
    /// SHARED plus one BOUNDARY, five distinct doorways, exactly what DoorSpawner creates. The
    /// scenes' nine openings are those same five seen twice from four of them.
    /// </para>
    /// <para>
    /// SO TWO ARTIFACTS CAN COUNT THE SAME WORLD DIFFERENTLY AND BOTH BE RIGHT, and a total hides
    /// it. Assert the RELATION each role actually obeys: corners are per-room and compare directly,
    /// jambs are two per DOORWAY and compare against the doors the world builds.
    /// </para>
    /// <para>
    /// DELETE THIS FILE IN THE SAME COMMIT AS THE SCENES. It ignores itself if they are already
    /// gone, so it cannot become a false alarm during the cutover, but it has no purpose once the
    /// thing it compares against does not exist. What remains true afterwards is
    /// WallSpawnerPlayModeTests.CornerPostsAndJambsReproduceTheApprovedPlacerArithmetic, which
    /// checks the arithmetic rather than the tally.
    /// </para>
    /// </remarks>
    public sealed class WallAccentParityPlayModeTests
    {
        private static readonly string[] RoomScenes =
        {
            "RuinedEntry", "BoneArchive", "ChapelOfAsh", "LowerVault", "FinalRoom"
        };

        private static readonly string[] AccentSprites = { "wall_corner", "wall_door_jamb", "wall_end_cap" };

        private GameObject managers;

        [TearDown]
        public void TearDown()
        {
            if (managers != null)
            {
                Object.DestroyImmediate(managers);
                managers = null;
            }
        }

        [UnityTest]
        public IEnumerator TheRuntimeWorldPlacesAsManyAccentsAsTheCommittedScenesHold()
        {
            int sceneCorners = 0, sceneJambs = 0, sceneEndCaps = 0;
            var perScene = new List<string>();
            foreach (string scene in RoomScenes)
            {
                string path = Path.Combine(Application.dataPath, "Scenes", "Rooms", scene + ".unity");
                if (!File.Exists(path))
                {
                    Assert.Ignore("Assets/Scenes/Rooms/" + scene + ".unity is gone, so the cutover "
                        + "has happened and this comparison has nothing left to compare against. "
                        + "Delete this file.");
                }

                string yaml = File.ReadAllText(path);
                int c = Regex.Matches(yaml, "m_Name: CornerAccent").Count;
                int j = Regex.Matches(yaml, "m_Name: JambAccent").Count;
                int e = Regex.Matches(yaml, "m_Name: EndCapAccent").Count;
                sceneCorners += c;
                sceneJambs += j;
                sceneEndCaps += e;
                perScene.Add(scene + " c" + c + "/j" + j + "/e" + e);
            }

            // A scene that parsed to zero would make the whole comparison vacuous, and it would
            // look like a pass the moment the runtime also placed none.
            Assert.Greater(sceneCorners + sceneJambs + sceneEndCaps, 0,
                "Read " + string.Join(", ", perScene) + " from the committed scenes. Zero accents "
                + "means the regex no longer matches how they are named, not that none exist.");

            var prefab = Resources.Load<GameObject>("GameManagers");
            Assert.IsNotNull(prefab, "Resources/GameManagers.prefab did not load.");

            managers = Object.Instantiate(prefab);
            var bootstrap = managers.GetComponent<GameBootstrap>();
            Assert.IsNotNull(bootstrap, "GameManagers carries no GameBootstrap.");

            // Start() builds on the next frame; wait for it rather than calling BuildWorld, so this
            // measures what pressing Play produces.
            yield return null;
            yield return null;
            Assert.IsTrue(bootstrap.HasBuilt, "GameBootstrap had not built after two frames.");

            var placed = new Dictionary<string, int>();
            foreach (string sprite in AccentSprites)
            {
                placed[sprite] = 0;
            }

            foreach (SpriteRenderer renderer in managers.GetComponentsInChildren<SpriteRenderer>(true))
            {
                if (renderer.sprite == null)
                {
                    continue;
                }

                if (placed.ContainsKey(renderer.sprite.name))
                {
                    placed[renderer.sprite.name]++;
                }
            }

            string breakdown = string.Join(", ", placed.Select(p => p.Key + " " + p.Value));

            // CORNERS ARE PER-ROOM AND MUST MATCH EXACTLY. A corner belongs to one room's own wall
            // run, so no two scenes can describe the same corner and the totals are comparable.
            Assert.AreEqual(sceneCorners, placed["wall_corner"],
                "The runtime placed " + placed["wall_corner"] + " corner accents where the committed "
                + "scenes hold " + sceneCorners + ". Corners are per-room and cannot be shared, so "
                + "this is a straight shortfall and deleting the scenes would drop the difference.");

            // JAMBS CANNOT BE COMPARED ON THE TOTAL, AND COMPARING THEM THAT WAY IS WHAT THIS TEST
            // GOT WRONG FIRST. The five room scenes are PER-ROOM, so a doorway in a shared wall is
            // drawn by BOTH rooms and counted twice; the single combined world draws it once.
            // Measured at main: D1 appears in RuinedEntryLayout and BoneArchiveLayout, D2 in
            // BoneArchive and ChapelOfAsh, D3 in ChapelOfAsh and LowerVault, D4 in LowerVault and
            // FinalRoom, and D5 in FinalRoom alone. That is 4 SHARED doorways plus 1 BOUNDARY = 5
            // distinct doorways, which is exactly what DoorSpawner creates, while the scenes hold
            // 4*2 + 1 = 9 openings' worth. So 18 in the scenes and 10 at runtime are THE SAME FIVE
            // DOORWAYS, and the apparent 8-jamb shortfall was an artifact of the comparison.
            //
            // THE DURABLE RELATION IS TWO JAMBS PER DOORWAY, so that is what is asserted - against
            // the door count the world actually builds, not against a number copied from the scenes.
            int doors = GameObject.FindObjectsByType<DoorInteractable>(FindObjectsInactive.Include,
                FindObjectsSortMode.None).Length;
            Assert.Greater(doors, 0, "No doors were spawned, so the jamb relation would assert on nothing.");
            Assert.AreEqual(doors * 2, placed["wall_door_jamb"],
                "The runtime placed " + placed["wall_door_jamb"] + " door jambs for " + doors
                + " doors. A doorway carries one jamb on each side, so this must be " + (doors * 2)
                + ". The committed scenes' " + sceneJambs + " is NOT the expectation: they are "
                + "per-room and draw a shared doorway twice.");

            // AND THE ROLE THE SCENES NEVER HAD. Asserted so that "0 == 0" is recorded as a
            // deliberate match rather than read later as two independent absences.
            Assert.AreEqual(sceneEndCaps, placed["wall_end_cap"],
                "End caps differ: runtime " + placed["wall_end_cap"] + ", scenes " + sceneEndCaps
                + ". Both were 0 when this was written.");

            TestContext.WriteLine("accent parity | runtime " + breakdown + " | scenes corner "
                + sceneCorners + ", jamb " + sceneJambs + ", endCap " + sceneEndCaps
                + " (" + string.Join(", ", perScene) + ") | doors " + doors);
        }
    }
}
