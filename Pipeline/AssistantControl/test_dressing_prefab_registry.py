"""Regression tests for the dressing-prefab builder registry.

Pure function calls only -- no Unity, no git, no network. Covers
``DRESSING_PREFAB_BUILDERS``, ``is_dressing_prefab_location``, and their
effect on ``resolve_generated_builder``, added to
``Pipeline/TaskReviewAgent/door_prototype_materialization.py`` alongside the
five already-approved ``ROOM_SCENE_BUILDERS``. See that module's docstrings
on ``DRESSING_ROOMS``, ``is_dressing_prefab_location`` and
``resolve_generated_builder`` for why a dressing prefab is an EXPLICIT owner
with no absorption, and why an unregistered dressing-shaped path must refuse
BY NAME rather than silently falling through to the default scene builder.

Existing room coverage lives in ``test_unity_materialization.py``
(``ARoomAbsorbsItsOwnGeneratedOutputs`` and neighbours) and in
``test_resolve_generated_builder_characterization.py``. The
``RoomBehaviourIsUnchangedByTheDressingRegistry`` class here is a light
re-check that this new registry did not disturb them -- not a duplicate of
that existing coverage.
"""
from __future__ import annotations

import unittest
from pathlib import PurePosixPath

from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    DOOR_PROTOTYPE_BUILD_METHOD,
    DOOR_PROTOTYPE_BUILDER,
    DOOR_PROTOTYPE_ROOT,
    DOOR_PROTOTYPE_SCENE,
    DRESSING_BUILD_METHOD_NAME,
    DRESSING_PREFAB_BUILDERS,
    DRESSING_PREFAB_DIRECTORY,
    DRESSING_ROOMS,
    ROOM_SCENE_BUILDERS,
    DoorPrototypeMaterializationError,
    DressingPrefabBuilder,
    is_dressing_prefab_location,
    resolve_generated_builder,
)


def _dressing_for(room: str) -> DressingPrefabBuilder:
    """The one DRESSING_PREFAB_BUILDERS entry for ``room``, read from the
    live registry rather than reconstructed by hand.
    """
    (builder,) = (b for b in DRESSING_PREFAB_BUILDERS.values() if b.room == room)
    return builder


def _room_scene_for(room: str) -> str:
    """The one ROOM_SCENE_BUILDERS scene path whose filename stem is
    ``room``, so this file never hardcodes the ``Assets/Scenes/Rooms/``
    prefix itself.
    """
    (scene,) = (
        scene for scene in ROOM_SCENE_BUILDERS if PurePosixPath(scene).stem == room
    )
    return scene


class EveryRegisteredDressingPrefabResolvesToItsOwnBuilder(unittest.TestCase):
    """Case 1: every entry in DRESSING_PREFAB_BUILDERS, alone, resolves to
    exactly its own registered (build_method, builder_source_path).
    Parameterized over the live dict, the same shape as
    ``EveryRegisteredRoomResolvesToItsOwnBuilder`` for rooms.
    """

    def test_each_dressing_prefab_alone_resolves_to_its_own_registered_builder(self):
        """If this breaks for any one room's dressing prefab, that room's
        dressing candidate would materialize through the wrong entry point
        -- or none -- while every other room's dressing kept passing, which
        a hardcoded sample of the registry would miss.
        """
        self.assertTrue(DRESSING_PREFAB_BUILDERS, "registry must not be empty")
        self.assertEqual(5, len(DRESSING_PREFAB_BUILDERS))
        self.assertEqual(len(DRESSING_ROOMS), len(DRESSING_PREFAB_BUILDERS))
        for prefab_path, builder in sorted(DRESSING_PREFAB_BUILDERS.items()):
            with self.subTest(prefab_path=prefab_path):
                method, source = resolve_generated_builder([prefab_path])
                self.assertEqual(builder.build_method, method)
                self.assertEqual(builder.builder_source_path, source)


class EveryDressingDescriptorIsInternallyConsistent(unittest.TestCase):
    """Case 2: each DressingPrefabBuilder's own fields agree with each
    other, independent of resolve_generated_builder.
    """

    def test_each_descriptor_is_internally_consistent(self):
        """If any one of these fields drifts apart from the others, the
        crew's prompt (built from these fields) and Unity's actual compiled
        class would disagree, and the mismatch would only surface as
        Unity's own "method could not be found" -- the exact failure
        ROOM_SCENE_BUILDERS's docstring records for rooms, now possible for
        dressing prefabs too.
        """
        self.assertTrue(DRESSING_PREFAB_BUILDERS, "registry must not be empty")
        for _prefab_path, builder in sorted(DRESSING_PREFAB_BUILDERS.items()):
            with self.subTest(room=builder.room):
                self.assertTrue(
                    builder.builder_source_path.endswith(builder.class_name + ".cs"),
                    f"{builder.builder_source_path!r} does not end with "
                    f"{builder.class_name + '.cs'!r}",
                )
                self.assertEqual(
                    builder.namespace + "." + builder.class_name + "."
                    + DRESSING_BUILD_METHOD_NAME,
                    builder.build_method,
                )
                self.assertEqual(
                    PurePosixPath(builder.catalog_path).parent,
                    PurePosixPath(builder.prefab_path).parent,
                )
                self.assertEqual(
                    builder.room + "Dressing",
                    PurePosixPath(builder.prefab_path).stem,
                )


class NoDressingBuildMethodNamesTheSaveOrTestVariant(unittest.TestCase):
    """Case 3: unlike ROOM_SCENE_BUILDERS, where ``Build`` and
    ``BuildAndSave`` are one role under two names, every dressing
    build_method must be exactly the plain entry point -- never the save
    variant some rooms use, and never the in-memory test-only variant.
    """

    def test_build_method_never_ends_in_build_and_save_or_build_in_memory_for_tests(self):
        """If this breaks, a dressing candidate could register the
        in-memory-only test variant (or a save-suffixed name that does not
        exist on the dressing builder class) as its real entry point, and
        materialization would either build nothing durable or fail to find
        the method at all.
        """
        self.assertTrue(DRESSING_PREFAB_BUILDERS, "registry must not be empty")
        for _prefab_path, builder in sorted(DRESSING_PREFAB_BUILDERS.items()):
            with self.subTest(room=builder.room):
                self.assertFalse(builder.build_method.endswith(".BuildAndSave"))
                self.assertFalse(
                    builder.build_method.endswith(".BuildInMemoryForTests")
                )


class TwoDressingPrefabsRefuseAsAmbiguous(unittest.TestCase):
    """Case 4: two different rooms' dressing prefabs in one request refuse,
    the same shape as ``TwoRoomScenesRefuseAsAmbiguous`` for rooms.
    """

    def test_two_dressing_prefabs_together_refuse_and_name_both_methods(self):
        """If this breaks -- either by not raising, or by silently picking
        one room's dressing builder over the other -- a candidate spanning
        two rooms' dressing would materialize through only one of them and
        silently drop the other room's prefab.
        """
        first_path, second_path = sorted(DRESSING_PREFAB_BUILDERS)[:2]
        first = DRESSING_PREFAB_BUILDERS[first_path]
        second = DRESSING_PREFAB_BUILDERS[second_path]
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([first_path, second_path])
        message = str(caught.exception)
        self.assertIn("generated paths require more than one builder method", message)
        self.assertIn(first.build_method, message)
        self.assertIn(second.build_method, message)


class DressingPlusItsOwnRoomSceneRefuses(unittest.TestCase):
    """Case 5: a room's dressing prefab together with that SAME room's own
    scene still refuses. There is no absorption pairing a dressing prefab
    with the scene it dresses -- unlike a room absorbing its own generated
    Unity output (the room-only ``ARoomAbsorbsItsOwnGeneratedOutputs``
    shape), a dressing prefab is never folded into the room's builder.
    """

    def test_dressing_plus_its_own_room_scene_refuses(self):
        """If this breaks by resolving instead of refusing, a candidate
        that both dresses a room and rebuilds that same room's scene would
        materialize through only one of the two builders, silently
        dropping the other -- either the scene or the dressing prefab.
        """
        room = "LowerVault"
        self.assertIn(room, DRESSING_ROOMS)
        dressing = _dressing_for(room)
        scene_path = _room_scene_for(room)
        scene = ROOM_SCENE_BUILDERS[scene_path]
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([dressing.prefab_path, scene_path])
        message = str(caught.exception)
        self.assertIn("generated paths require more than one builder method", message)
        self.assertIn(dressing.build_method, message)
        self.assertIn(scene.build_method, message)


class DressingPlusTheComposedSceneRefuses(unittest.TestCase):
    """Case 6: a dressing prefab together with the composed
    DOOR_PROTOTYPE_SCENE still refuses, the same shape as
    ``ARoomPlusTheComposedSceneRefuses`` for rooms.
    """

    def test_dressing_plus_composed_prototype_scene_refuses(self):
        """If this breaks, a dressing candidate that also touches the
        composed scene would materialize through only one builder,
        silently dropping whichever of the two it is not.
        """
        dressing = _dressing_for("FinalRoom")
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([dressing.prefab_path, DOOR_PROTOTYPE_SCENE])
        message = str(caught.exception)
        self.assertIn("generated paths require more than one builder method", message)
        self.assertIn(dressing.build_method, message)
        self.assertIn(DOOR_PROTOTYPE_BUILD_METHOD, message)


class DressingHasNoAbsorptionUnlikeARoom(unittest.TestCase):
    """Case 7: a dressing prefab plus an unassigned generated DoorPrototype
    asset still refuses. A room in the same shape ABSORBS the asset
    (``ARoomAbsorbsItsOwnGeneratedOutputs``); dressing deliberately does
    not, per the module docstring on resolve_generated_builder.
    """

    def test_dressing_plus_an_unassigned_generated_asset_refuses(self):
        """If this breaks into silently absorbing, a dressing candidate
        that also owns an unrelated generated DoorPrototype asset would
        stop refusing, and the asset's real owner (the default builder)
        would go unbuilt without anyone deciding that was fine.
        """
        dressing = _dressing_for("RuinedEntry")
        generated_path = DOOR_PROTOTYPE_ROOT + "Generated/DressingRegressionTile.asset"
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([dressing.prefab_path, generated_path])
        message = str(caught.exception)
        self.assertIn("generated paths require more than one builder method", message)
        self.assertIn(dressing.build_method, message)
        self.assertIn(DOOR_PROTOTYPE_BUILD_METHOD, message)


class UnregisteredDressingShapedPathsRefuseByName(unittest.TestCase):
    """Case 8: a path shaped like a dressing prefab -- under the
    RoomDressing directory, ending in ``.prefab`` -- that is not one of the
    five exact registered keys refuses BY NAME instead of silently falling
    through to the default scene builder, per is_dressing_prefab_location's
    own docstring. The nested cases are the important ones:
    is_dressing_prefab_location matches ANY DEPTH, so it is the exact-key
    registry lookup that must be what refuses, not the location check.
    """

    def test_a_flat_unknown_room_name_refuses(self):
        """If this breaks, an unregistered room's dressing prefab at the
        top of the directory would fall through to the default builder,
        which never produces a prefab -- a silent wrong-builder invocation.
        """
        self.assertNotIn("NotARealRoom", DRESSING_ROOMS)
        path = DRESSING_PREFAB_DIRECTORY + "NotARealRoomDressing.prefab"
        self.assertNotIn(path, DRESSING_PREFAB_BUILDERS)
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([path])
        self.assertEqual(
            f"dressing_prefab_not_registered: {path}", str(caught.exception)
        )

    def test_a_nested_path_under_an_otherwise_valid_room_name_refuses(self):
        """The important case: LowerVault IS a real registered room, but
        nesting its dressing prefab one directory deeper is not the exact
        registered key. If this breaks by resolving instead of refusing,
        the exact-key registry becomes a prefix match in practice, and a
        crew-authored path one directory off from the real one would
        silently route to LowerVault's builder instead of failing loudly.
        """
        self.assertIn("LowerVault", DRESSING_ROOMS)
        path = DRESSING_PREFAB_DIRECTORY + "sub/LowerVaultDressing.prefab"
        self.assertNotIn(path, DRESSING_PREFAB_BUILDERS)
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([path])
        self.assertEqual(
            f"dressing_prefab_not_registered: {path}", str(caught.exception)
        )

    def test_a_deeply_nested_path_refuses(self):
        """Same case, several directories deep, so the refusal is proven to
        hold at depth rather than only immediately below the registered
        directory.
        """
        self.assertIn("FinalRoom", DRESSING_ROOMS)
        path = DRESSING_PREFAB_DIRECTORY + "a/b/c/FinalRoomDressing.prefab"
        self.assertNotIn(path, DRESSING_PREFAB_BUILDERS)
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([path])
        self.assertEqual(
            f"dressing_prefab_not_registered: {path}", str(caught.exception)
        )


class TheCatalogJsonIsNotADressingLocation(unittest.TestCase):
    """Case 9: the catalog .json living in the same directory as the
    prefabs is not itself a dressing prefab location --
    is_dressing_prefab_location checks the ``.prefab`` suffix, not just the
    directory.
    """

    def test_the_catalog_json_is_not_a_dressing_prefab_location(self):
        """If this breaks (the suffix check is dropped or loosened), every
        catalog .json would be treated as an unregistered dressing prefab
        and refuse resolve_generated_builder outright, when it should be an
        ordinary DoorPrototype-owned asset instead.
        """
        catalog_path = _dressing_for("BoneArchive").catalog_path
        self.assertTrue(catalog_path.endswith(".json"))
        self.assertFalse(is_dressing_prefab_location(catalog_path))

    def test_the_catalog_json_alone_uses_the_default_builder(self):
        """The practical consequence of the case above: since the catalog
        is not a dressing location, it is not an explicit owner either, and
        falls to the same default builder as any other DoorPrototype-owned
        generated asset rather than refusing.
        """
        catalog_path = _dressing_for("BoneArchive").catalog_path
        method, source = resolve_generated_builder([catalog_path])
        self.assertEqual(DOOR_PROTOTYPE_BUILD_METHOD, method)
        self.assertEqual(DOOR_PROTOTYPE_BUILDER, source)


class IsDressingPrefabLocationIsFalseOutsideTheDirectory(unittest.TestCase):
    """Case 10: is_dressing_prefab_location is False for paths that are
    genuinely not under the dressing directory, including a near-miss that
    merely shares the directory's characters as a prefix.
    """

    def test_an_unrelated_path_is_false(self):
        """If this breaks true, a completely unrelated path would start
        refusing as an unregistered dressing prefab instead of following
        whatever its own normal rule is.
        """
        self.assertFalse(is_dressing_prefab_location("Assets/Something/Else.prefab"))

    def test_a_prefab_elsewhere_under_doorprototype_is_false(self):
        """A .prefab under the DoorPrototype root but outside RoomDressing
        must not be swept into the dressing rule -- that would refuse an
        ordinary prefab that was never meant to be a dressing prefab.
        """
        path = DOOR_PROTOTYPE_ROOT + "Prefabs/SomeUnrelated.prefab"
        self.assertFalse(path.startswith(DRESSING_PREFAB_DIRECTORY))
        self.assertFalse(is_dressing_prefab_location(path))

    def test_a_near_miss_directory_prefix_is_not_treated_as_inside(self):
        """The directory match is an exact path-segment prefix, not a
        substring. If this breaks into a looser match, a sibling directory
        that merely starts with the same characters (e.g.
        ``RoomDressingExtra``) would be wrongly treated as being inside the
        dressing directory.
        """
        near_miss = DRESSING_PREFAB_DIRECTORY.rstrip("/") + "Extra/File.prefab"
        self.assertFalse(near_miss.startswith(DRESSING_PREFAB_DIRECTORY))
        self.assertFalse(is_dressing_prefab_location(near_miss))


class RoomBehaviourIsUnchangedByTheDressingRegistry(unittest.TestCase):
    """Case 11: a light re-check that adding the dressing registry did not
    disturb room resolution. Not a duplicate of the fuller existing
    coverage in ``test_unity_materialization.py``
    (``ARoomAbsorbsItsOwnGeneratedOutputs``) and
    ``test_resolve_generated_builder_characterization.py`` -- just enough
    to prove the two registries do not interfere with each other.
    """

    def test_one_room_alone_resolves_to_its_own_builder(self):
        """If this breaks, adding the dressing registry would have changed
        the plain single-room resolution path that predates it.
        """
        scene_path = sorted(ROOM_SCENE_BUILDERS)[0]
        expected = ROOM_SCENE_BUILDERS[scene_path]
        method, source = resolve_generated_builder([scene_path])
        self.assertEqual(expected.build_method, method)
        self.assertEqual(expected.builder_source_path, source)

    def test_one_room_absorbs_its_own_generated_asset(self):
        """If this breaks, adding the dressing registry would have
        reopened the NSC-044/046/047 absorption defect for rooms, even
        though dressing itself never absorbs.
        """
        scene_path = sorted(ROOM_SCENE_BUILDERS)[0]
        expected = ROOM_SCENE_BUILDERS[scene_path]
        generated_path = (
            DOOR_PROTOTYPE_ROOT + "Generated/DressingRegressionRoomTile.asset"
        )
        method, source = resolve_generated_builder([scene_path, generated_path])
        self.assertEqual(expected.build_method, method)
        self.assertEqual(expected.builder_source_path, source)

    def test_two_rooms_still_refuse(self):
        """If this breaks, two genuinely different rooms in one request
        would stop being refused as ambiguous.
        """
        first_scene, second_scene = sorted(ROOM_SCENE_BUILDERS)[:2]
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([first_scene, second_scene])
        self.assertIn("more than one builder method", str(caught.exception))

    def test_room_plus_composed_scene_still_refuses(self):
        """If this breaks, a room scene plus the composed DoorPrototype
        scene would stop being refused as a second, real builder.
        """
        scene_path = sorted(ROOM_SCENE_BUILDERS)[0]
        with self.assertRaises(DoorPrototypeMaterializationError) as caught:
            resolve_generated_builder([scene_path, DOOR_PROTOTYPE_SCENE])
        self.assertIn("more than one builder method", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
