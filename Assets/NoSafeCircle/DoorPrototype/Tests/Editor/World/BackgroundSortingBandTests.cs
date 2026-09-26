using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using NoSafeCircle.DoorPrototype.Editor;
using NoSafeCircle.DoorPrototype.World;
using NUnit.Framework;
using UnityEngine;

namespace NoSafeCircle.DoorPrototype.Tests.Editor.World
{
    /// <summary>
    /// The background sorting band must sit strictly below every authored dressing sorting_order.
    /// </summary>
    /// <remarks>
    /// WHY THIS EXISTS. Unity compares sortingOrder BEFORE the camera's custom transparency axis,
    /// so an integer order is absolute: a prop at -1165 renders behind a floor at -100 no matter
    /// where either one stands. The band was -100/-90 and the five room dressing catalogs author
    /// orders down to -1165, so 189 of the 222 authored props were painted over by their own floor.
    ///
    /// WHY IT RECOMPUTES INSTEAD OF ASSERTING A NUMBER. -1165 is today's minimum and nothing stops
    /// the Art Director authoring past it; a test pinned to -1165 would rot the moment a catalog
    /// changed, which is precisely the event it exists to catch. So the minimum is derived from the
    /// catalogs on every run and the assertion is the RELATION. This fixture holds no expected
    /// sorting_order value of its own, by design.
    ///
    /// The catalogs are the authored input and this fixture does not second-guess them. It takes no
    /// view on whether -1165 is a good number; only on whether the band clears whatever they say.
    /// </remarks>
    public sealed class BackgroundSortingBandTests
    {
        private const string CatalogDirectory =
            "Assets/NoSafeCircle/DoorPrototype/Art/Environment/RoomDressing";

        private const string RoomSceneDirectory = "Assets/Scenes/Rooms";

        [Test]
        public void BackgroundBand_SitsBelowEveryAuthoredDressingSortingOrder()
        {
            CatalogSweep sweep = SweepCatalogs();

            Assert.Less(
                DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder,
                sweep.MinimumSortingOrder,
                "The ground band must sit strictly below every authored dressing sorting_order, or "
                + "the floor paints over the props. Band is "
                + DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder + ", lowest authored order is "
                + sweep.MinimumSortingOrder + " (" + sweep.MinimumSource + "), across "
                + sweep.PlacementCount + " placements in " + sweep.CatalogCount + " catalogs.");

            // The architectural border is ground decoration painted just above the floor plane, so
            // props stand on it too and it is subject to the same rule. Checked separately because a
            // band with one of its two members raised back above the catalogs is the likely mistake.
            Assert.Less(
                DoorPrototypeSceneBuilder.BackgroundArchitecturalBorderSortingOrder,
                sweep.MinimumSortingOrder,
                "The architectural border band must also sit strictly below every authored dressing "
                + "sorting_order. Border is "
                + DoorPrototypeSceneBuilder.BackgroundArchitecturalBorderSortingOrder
                + ", lowest authored order is " + sweep.MinimumSortingOrder + ".");
        }

        [Test]
        public void BackgroundBand_PaintsItsFloorBeneathItsArchitecturalBorder()
        {
            // The border tilemap is offset further from the floor plane than the floor is, so it has
            // to draw AFTER the floor. Both being below the catalogs is not enough; their order
            // relative to each other is a separate statement and nothing else asserts it.
            Assert.Less(
                DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder,
                DoorPrototypeSceneBuilder.BackgroundArchitecturalBorderSortingOrder,
                "The floor must draw beneath the ground-flush architectural border.");
        }

        [Test]
        public void BackgroundBand_StaysInsideTheRangeUnityCanRepresent()
        {
            // Renderer.sortingOrder is an int in the API and a SIGNED 16-BIT field in the sorting
            // key Unity actually builds. A band pushed past that range wraps to a LARGE POSITIVE
            // order, which does not throw and does not warn - it silently inverts this whole
            // fixture's relation and draws the floor over everything. Lowering the band is the
            // obvious response to a future catalog going deeper, so this is the guard on the
            // obvious response rather than on today's value.
            foreach (KeyValuePair<string, int> member in new Dictionary<string, int>
                     {
                         { "BackgroundGroundSortingOrder", DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder },
                         { "BackgroundArchitecturalBorderSortingOrder", DoorPrototypeSceneBuilder.BackgroundArchitecturalBorderSortingOrder },
                     })
            {
                Assert.GreaterOrEqual(member.Value, (int)short.MinValue,
                    member.Key + " is below Unity's representable sorting-order range and will wrap.");
                Assert.LessOrEqual(member.Value, (int)short.MaxValue,
                    member.Key + " is above Unity's representable sorting-order range and will wrap.");
            }
        }

        [Test]
        public void CommittedRoomScenes_CarryTheBandRatherThanTheLiteralTheyWereBakedWith()
        {
            // A BUILDER CHANGE IS INVISIBLE UNTIL THE SCENE IS RE-BAKED. RoomSceneComposer OPENS
            // these committed scenes and calls no builder, so the constant above can be correct
            // while every room on disk still carries the value it was baked with. This reads the
            // baked artifact, which is the only thing that can catch that; asserting on the builder
            // would agree with itself.
            //
            // Assets/Scenes/DoorPrototype.unity is deliberately NOT checked here: it is
            // binary-serialized, so there is no text to read. The prototype scene's band is covered
            // by TitleScreenSceneBuilderTests, which builds it in memory.
            int expected = DoorPrototypeSceneBuilder.BackgroundGroundSortingOrder;

            // (?![0-9]) matters: "m_SortingOrder: -100" is a SUBSTRING of "m_SortingOrder: -10000",
            // so a plain search for the old literal matches the new value and this test would pass
            // while asserting nothing.
            var expectedPattern = new Regex(@"m_SortingOrder: " + expected + @"(?![0-9])");
            var stalePattern = new Regex(@"m_SortingOrder: -100(?![0-9])");

            Assert.IsTrue(Directory.Exists(RoomSceneDirectory),
                RoomSceneDirectory + " is missing; the committed room scenes are the artifact under test.");

            foreach (RoomId room in Enum.GetValues(typeof(RoomId)))
            {
                string scenePath = Path.Combine(RoomSceneDirectory, room + ".unity").Replace('\\', '/');
                Assert.IsTrue(File.Exists(scenePath), scenePath + " is missing.");

                string text = File.ReadAllText(scenePath);

                Assert.Greater(expectedPattern.Matches(text).Count, 0,
                    scenePath + " carries no floor tilemap at the background band (" + expected
                    + "). The builder was changed without re-baking this scene, so the room on disk "
                    + "still paints its floor over the dressing.");

                Assert.AreEqual(0, stalePattern.Matches(text).Count,
                    scenePath + " still carries a renderer at the retired -100 band.");
            }
        }

        // ------------------------------------------------------------------ the sweep

        private struct CatalogSweep
        {
            public int CatalogCount;
            public int PlacementCount;
            public int MinimumSortingOrder;
            public string MinimumSource;
        }

        private static CatalogSweep SweepCatalogs()
        {
            Assert.IsTrue(Directory.Exists(CatalogDirectory),
                CatalogDirectory + " is missing; the authored catalogs are the input to this rule.");

            // Globbed rather than listed, so a sixth room's catalog is covered the day it lands
            // instead of the day someone remembers this file.
            string[] catalogs = Directory.GetFiles(CatalogDirectory, "*DressingCatalog.json");
            Array.Sort(catalogs, StringComparer.Ordinal);

            // PROVE THE HAYSTACK. An empty or misdirected sweep produces no minimum to compare
            // against and would otherwise read as a pass. The expectation comes from the RoomId
            // enum rather than from the folder being measured.
            foreach (RoomId room in Enum.GetValues(typeof(RoomId)))
            {
                string expectedCatalog =
                    Path.Combine(CatalogDirectory, room + "DressingCatalog.json").Replace('\\', '/');
                Assert.IsTrue(File.Exists(expectedCatalog),
                    "Room " + room + " declares no dressing catalog at " + expectedCatalog
                    + "; the sweep would silently skip its props.");
            }

            Assert.GreaterOrEqual(catalogs.Length, Enum.GetValues(typeof(RoomId)).Length,
                "Fewer catalogs matched than there are rooms; the glob or the folder has moved.");

            var sweep = new CatalogSweep
            {
                CatalogCount = catalogs.Length,
                PlacementCount = 0,
                MinimumSortingOrder = int.MaxValue,
                MinimumSource = null,
            };
            var distinct = new HashSet<int>();

            foreach (string catalogPath in catalogs)
            {
                string json = File.ReadAllText(catalogPath);
                if (json.Length > 0 && json[0] == '﻿')
                {
                    json = json.Substring(1);
                }

                CatalogFile catalog = JsonUtility.FromJson<CatalogFile>(json);
                Assert.IsNotNull(catalog?.props, catalogPath + " parsed to no placements.");
                Assert.Greater(catalog.props.Length, 0, catalogPath + " declares no placements.");

                foreach (CatalogPlacement placement in catalog.props)
                {
                    sweep.PlacementCount++;
                    distinct.Add(placement.sorting_order);
                    if (placement.sorting_order < sweep.MinimumSortingOrder)
                    {
                        sweep.MinimumSortingOrder = placement.sorting_order;
                        sweep.MinimumSource = Path.GetFileName(catalogPath) + ":" + placement.instance_id;
                    }
                }
            }

            Assert.Greater(sweep.PlacementCount, 0, "The sweep found no placements at all.");

            // THE CONTROL THAT MATTERS, and it is not about the file list. JsonUtility binds by
            // field name and reports nothing when a name does not match: a renamed or restructured
            // sorting_order field yields 0 for every placement, the minimum becomes 0, and a band of
            // -10000 clears it comfortably. The fixture would pass having measured nothing. Real
            // catalogs carry many distinct, mostly negative orders, so requiring that discriminates
            // a successful parse from a silent default.
            Assert.Greater(distinct.Count, 1,
                "Every placement reported the same sorting_order across " + sweep.CatalogCount
                + " catalogs. JsonUtility most likely failed to bind the field rather than the "
                + "catalogs genuinely agreeing; this fixture cannot measure the band from that.");
            Assert.Less(sweep.MinimumSortingOrder, 0,
                "No authored sorting_order is negative, which no real catalog looks like; suspect a "
                + "failed parse rather than a band that has nothing to clear.");

            return sweep;
        }

        [Serializable]
        private sealed class CatalogFile
        {
            public CatalogPlacement[] props;
        }

        [Serializable]
        private sealed class CatalogPlacement
        {
            public string instance_id;
            public int sorting_order;
        }
    }
}
