"""Characterization tests for resolve_generated_builder's builder resolution.

Pure function calls only -- no Unity, no git, no network. These lock in the
CURRENT mapping from a set of generated output paths to exactly one
``(build_method, builder_source_path)``, ahead of a design change to the
materialization pipeline. See
``Pipeline/TaskReviewAgent/door_prototype_materialization.py:410`` for the
docstring recording the NSC-044/NSC-046/NSC-047 incidents each branch here
guards against.

Existing coverage lives in ``test_unity_materialization.py``
(``ARoomAbsorbsItsOwnGeneratedOutputs`` and
``TheRegistryMatchesTheBuilderSource``, around lines 597, 655 and 668). Every
call there that resolves to a single builder combines a room scene with
something else (a generated tile, an unrelated asset) or only exercises
three of the five registered rooms directly. This file adds what was not
exercised directly against ``resolve_generated_builder`` there: a lone room
scene with nothing else in scope, an empty sequence, a standalone
unregistered path with no room in the mix at all, and all five
``ROOM_SCENE_BUILDERS`` entries swept generically from the registry rather
than three hand-picked ones.
"""
from __future__ import annotations

import unittest

from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    DOOR_PROTOTYPE_BUILD_METHOD,
    DOOR_PROTOTYPE_BUILDER,
    DOOR_PROTOTYPE_ROOT,
    DOOR_PROTOTYPE_SCENE,
    DoorPrototypeMaterializationError,
    ROOM_SCENE_BUILDERS,
    resolve_generated_builder,
)

# Room scenes exercised alone or in a two-room combination below. Neither
# appears as an argument to resolve_generated_builder() anywhere in
# test_unity_materialization.py today -- the existing suite's two-room and
# absorption cases use RuinedEntry, ChapelOfAsh and LowerVault.
BONE_ARCHIVE_SCENE = "Assets/Scenes/Rooms/BoneArchive.unity"
FINAL_ROOM_SCENE = "Assets/Scenes/Rooms/FinalRoom.unity"


class ExactlyOneRoomSceneAloneResolvesToItsBuilder(unittest.TestCase):
    """Case 1: a single registered room scene, nothing else in scope."""

    def test_a_lone_room_scene_resolves_to_its_own_builder(self):
        """If this breaks, the plain single-room request -- the common shape
        for a room-only candidate, with no generated companion in scope yet
        -- would stop resolving to that room's own builder.
        """
        expected = ROOM_SCENE_BUILDERS[BONE_ARCHIVE_SCENE]
        method, source = resolve_generated_builder([BONE_ARCHIVE_SCENE])
        self.assertEqual(expected.build_method, method)
        self.assertEqual(expected.builder_source_path, source)


class ARoomAbsorbsGeneratedDoorPrototypeAssets(unittest.TestCase):
    """Case 2: a room scene plus generated output under the DoorPrototype
    root still resolves to that one room's builder (absorption), so a
    room's own generated tiles never make a single-room request look like a
    two-builder one.
    """

    def test_room_scene_plus_generated_asset_still_resolves_to_the_room(self):
        """If this breaks, every candidate that both builds a room AND owns
        a generated asset under the DoorPrototype root -- the exact shape
        that blocked NSC-044, NSC-046 and NSC-047 on 2026-09-22 -- starts
        refusing again as a false two-builder conflict.
        """
        generated_path = DOOR_PROTOTYPE_ROOT + "Generated/BoneArchiveWallTile.asset"
        expected = ROOM_SCENE_BUILDERS[BONE_ARCHIVE_SCENE]
        method, source = resolve_generated_builder(
            [BONE_ARCHIVE_SCENE, generated_path])
        self.assertEqual(expected.build_method, method)
        self.assertEqual(expected.builder_source_path, source)


class TwoRoomScenesRefuseAsAmbiguous(unittest.TestCase):
    """Case 3: two different room scenes in one request refuse outright."""

    def test_two_different_room_scenes_refuse_and_name_both_methods(self):
        """If this breaks -- either by not raising, or by silently picking
        one room's builder over the other -- a candidate spanning two rooms
        would materialize through only one of them and silently drop the
        other room's changes.
        """
        bone_archive = ROOM_SCENE_BUILDERS[BONE_ARCHIVE_SCENE]
        final_room = ROOM_SCENE_BUILDERS[FINAL_ROOM_SCENE]
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([BONE_ARCHIVE_SCENE, FINAL_ROOM_SCENE])
        message = str(caught.exception)
        self.assertIn("more than one builder method", message)
        self.assertIn(bone_archive.build_method, message)
        self.assertIn(final_room.build_method, message)


class ARoomPlusTheComposedSceneRefuses(unittest.TestCase):
    """Case 4: a room scene plus the composed ``DoorPrototype.unity`` scene
    refuses, because that composed scene is the DEFAULT builder's own
    output rather than a room's, even though a room alone would absorb a
    generated asset (case 2).
    """

    def test_room_scene_plus_composed_prototype_scene_refuses(self):
        """If this breaks, a request naming a room's scene alongside the
        composed prototype scene would materialize through only one
        builder, silently dropping whichever of the two it is not.
        """
        final_room = ROOM_SCENE_BUILDERS[FINAL_ROOM_SCENE]
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([FINAL_ROOM_SCENE, DOOR_PROTOTYPE_SCENE])
        message = str(caught.exception)
        self.assertIn("more than one builder method", message)
        self.assertIn(final_room.build_method, message)
        self.assertIn(DOOR_PROTOTYPE_BUILD_METHOD, message)


class GeneratedPathsWithNoRoomUseTheDefaultBuilder(unittest.TestCase):
    """Case 5: generated DoorPrototype paths with no room scene in scope
    resolve to the module default builder.
    """

    def test_generated_paths_with_no_room_resolve_to_the_default_builder(self):
        """If this breaks, a candidate that only touches generated
        DoorPrototype output -- no room scene at all -- would stop
        resolving to the shared DoorPrototypeSceneBuilder.Build entry
        point, which is the builder every non-room task depends on.
        """
        generated_path = DOOR_PROTOTYPE_ROOT + "Generated/SomeCharacterizationTile.asset"
        method, source = resolve_generated_builder([generated_path])
        self.assertEqual(DOOR_PROTOTYPE_BUILD_METHOD, method)
        self.assertEqual(DOOR_PROTOTYPE_BUILDER, source)

    def test_the_composed_prototype_scene_alone_also_uses_the_default(self):
        """Companion to case 4: the composed scene is the default builder's
        own output, so it is only a SECOND builder when a room is also in
        scope (case 4). Alone, it resolves like any other DoorPrototype
        output. If this breaks, that boundary moved without anyone
        deciding it should.
        """
        method, source = resolve_generated_builder([DOOR_PROTOTYPE_SCENE])
        self.assertEqual(DOOR_PROTOTYPE_BUILD_METHOD, method)
        self.assertEqual(DOOR_PROTOTYPE_BUILDER, source)


class AnUnregisteredPathStandaloneRefuses(unittest.TestCase):
    """Case 6: a path outside the DoorPrototype root, and not a registered
    room, refuses -- with no room in the request at all, unlike the
    existing combined-with-a-room refusal test in
    test_unity_materialization.py.
    """

    def test_an_unregistered_path_alone_refuses_by_name(self):
        """If this breaks, an out-of-scope path would either be silently
        accepted (routing Unity to build something nobody asked for) or
        refused with a message that no longer names the offending path,
        making the failure unreadable.
        """
        path = "Assets/Something/Else.asset"
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([path])
        message = str(caught.exception)
        self.assertIn("not a registered Unity builder output", message)
        self.assertIn(path, message)

    def test_a_near_miss_prefix_is_not_wildcard_absorbed(self):
        """The registry match on DOOR_PROTOTYPE_ROOT is an exact path
        prefix, not a substring or wildcard match. If this breaks into a
        looser match, an unrelated folder that merely starts with similar
        characters would be silently absorbed into the DoorPrototype
        builder's scope instead of being refused.
        """
        near_miss = DOOR_PROTOTYPE_ROOT.rstrip("/") + "Extra/File.asset"
        self.assertFalse(near_miss.startswith(DOOR_PROTOTYPE_ROOT))
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([near_miss])
        self.assertIn("not a registered Unity builder output", str(caught.exception))


class AnEmptySequenceRefuses(unittest.TestCase):
    """Case 7: no paths at all refuses -- there is nothing to resolve a
    builder from.
    """

    def test_an_empty_sequence_refuses(self):
        """If this breaks -- for instance by returning some default builder
        instead of raising -- a request that materializes nothing would
        silently launch Unity anyway.
        """
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([])
        self.assertIn(
            "no generated paths were given to resolve a Unity builder",
            str(caught.exception))


class EveryRegisteredRoomResolvesToItsOwnBuilder(unittest.TestCase):
    """Case 8: every entry in ROOM_SCENE_BUILDERS, alone, resolves to
    exactly its own registered (build_method, builder_source_path).
    Parameterized over the live dict so a sixth room added later is covered
    automatically, and so this does not silently stop checking a room that
    is renamed or removed.
    """

    def test_each_room_scene_alone_resolves_to_its_own_registered_builder(self):
        """If this breaks for any one room, that room's candidates would
        materialize through the wrong entry point -- or none -- while every
        other room kept passing, which is exactly the kind of single-room
        regression a hardcoded sample of the registry would miss.
        """
        self.assertTrue(ROOM_SCENE_BUILDERS, "registry must not be empty")
        for scene, room in sorted(ROOM_SCENE_BUILDERS.items()):
            with self.subTest(scene=scene):
                method, source = resolve_generated_builder([scene])
                self.assertEqual(room.build_method, method)
                self.assertEqual(room.builder_source_path, source)


if __name__ == "__main__":
    unittest.main()
