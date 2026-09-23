#!/usr/bin/env python3
"""The crew is told the ONE entry point the materializer will invoke.

A crew that guesses a method name produces a candidate that passes semantic
review and then fails in Unity with "method could not be found" and no compiler
error -- after the spend.  These checks assert the exact full method reaches all
three roles, that an ordinary task is unaffected, and that an ambiguous request
says nothing rather than guessing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.prompts import (  # noqa: E402
    _dressing_guidance,
    implementer_prompt,
    test_author_prompt,
    validator_prompt,
)
from Pipeline.TaskReviewAgent.door_prototype_materialization import (  # noqa: E402
    DRESSING_PREFAB_BUILDERS,
    DRESSING_ROOMS,
)

ROOM_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/RuinedEntrySceneBuilder.cs"
ROOM_SCENE = "Assets/Scenes/Rooms/RuinedEntry.unity"


def _builder(room: str):
    for candidate in DRESSING_PREFAB_BUILDERS.values():
        if candidate.room == room:
            return candidate
    raise AssertionError(f"no registered dressing builder for {room}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_all_five_rooms_reach_the_implementer() -> None:
    """Every registered room, not just the one somebody tried by hand."""
    for room in DRESSING_ROOMS:
        builder = _builder(room)
        prompt = implementer_prompt(
            task_id="NSC-082", title="dress the room", task_contract="{}",
            implementation_paths=(),
            new_implementation_paths=(
                builder.prefab_path, builder.builder_source_path, builder.catalog_path,
            ),
        )
        _require(
            builder.build_method in prompt,
            f"{room}: implementer prompt omitted the exact full method",
        )
        _require(
            f"public static class {builder.class_name}" in prompt,
            f"{room}: implementer prompt omitted the expected class declaration",
        )
        _require(
            f"namespace {builder.namespace}" in prompt,
            f"{room}: implementer prompt omitted the expected namespace",
        )
        _require(
            builder.catalog_path in prompt and "JSON SOURCE file" in prompt,
            f"{room}: implementer prompt did not state the catalog is a source file",
        )
        _require(
            "never BuildAndSave" in prompt and "BuildInMemoryForTests" in prompt,
            f"{room}: implementer prompt did not rule out the room-builder methods",
        )
        _require(
            ".unity scene" in prompt,
            f"{room}: implementer prompt did not forbid scene edits",
        )


def _check_test_author_and_validator_reach_it() -> None:
    """Both later roles judge the same candidate and need the same fact."""
    builder = _builder("LowerVault")
    authored = test_author_prompt(
        task_id="NSC-082", title="dress the room", task_contract="{}", policy="{}",
        implementation_patch="", implementation_paths=(builder.builder_source_path,),
        implementation_actual_paths=(builder.builder_source_path, builder.catalog_path),
        test_paths=(),
    )
    _require(builder.build_method in authored, "test author prompt omitted the method")
    validated = validator_prompt(
        task_id="NSC-082", title="dress the room", task_contract="{}",
        candidate_patch="",
        changed_paths=(builder.builder_source_path, builder.catalog_path),
        implementer_output={}, test_author_output={},
    )
    _require(builder.build_method in validated, "validator prompt omitted the method")
    _require(
        builder.prefab_path in validated,
        "validator prompt omitted the prefab the builder must produce",
    )


def _check_the_validator_sees_it_from_the_builder_alone() -> None:
    """The crew never writes the prefab, so the validator's changed paths lack it.

    Resolving from the BUILDER SOURCE as well as the prefab is what makes the
    guidance reach the one role whose path list can never contain the output.
    """
    builder = _builder("ChapelOfAsh")
    prompt = validator_prompt(
        task_id="NSC-080", title="dress the room", task_contract="{}",
        candidate_patch="", changed_paths=(builder.builder_source_path,),
        implementer_output={}, test_author_output={},
    )
    _require(builder.build_method in prompt, "validator prompt missed a builder-only payload")


def _check_an_ordinary_task_is_untouched() -> None:
    """No dressing path, no dressing text. This must not leak into room work."""
    prompt = implementer_prompt(
        task_id="NSC-044", title="fix a sorting layer", task_contract="{}",
        implementation_paths=(ROOM_BUILDER,), new_implementation_paths=(),
    )
    _require(
        "ROOM DRESSING PREFAB" not in prompt,
        "an ordinary room task was given dressing guidance",
    )
    _require(_dressing_guidance((ROOM_BUILDER, ROOM_SCENE)) == "", "room paths resolved a builder")
    _require(_dressing_guidance(()) == "", "an empty payload resolved a builder")


def _check_an_ambiguous_request_says_nothing() -> None:
    """Two families in one payload: say nothing rather than name the wrong one.

    The materializer refuses this outright.  A prompt that picked one of the two
    would hand the crew a confident wrong instruction for the other.
    """
    first, second = _builder("LowerVault"), _builder("FinalRoom")
    _require(
        _dressing_guidance((first.builder_source_path, second.builder_source_path)) == "",
        "two dressing families produced guidance for one of them",
    )
    _require(
        _dressing_guidance((first.prefab_path, second.prefab_path)) == "",
        "two dressing prefabs produced guidance for one of them",
    )


def _check_the_registry_is_not_duplicated() -> None:
    """The guidance is DERIVED. A second copy of the registry rots separately."""
    source = (ROOT / "Pipeline" / "ExecutionCrew" / "prompts.py").read_text(encoding="utf-8")
    for room in DRESSING_ROOMS:
        builder = _builder(room)
        for literal in (builder.prefab_path, builder.builder_source_path,
                        builder.catalog_path, builder.build_method):
            _require(
                literal not in source,
                f"prompts.py hard-codes {literal}; derive it from the registry instead",
            )


def _check_no_path_authority_is_widened() -> None:
    """Guidance names only paths the role was already granted."""
    builder = _builder("BoneArchive")
    granted = (builder.prefab_path, builder.builder_source_path, builder.catalog_path)
    text = _dressing_guidance(granted)
    _require(text != "", "a registered payload produced no guidance")
    for line in text.splitlines():
        for token in line.split():
            if token.startswith("Assets/"):
                _require(
                    token.rstrip(".,") in granted,
                    f"guidance named an ungranted path: {token}",
                )


def main() -> int:
    checks = (
        _check_all_five_rooms_reach_the_implementer,
        _check_test_author_and_validator_reach_it,
        _check_the_validator_sees_it_from_the_builder_alone,
        _check_an_ordinary_task_is_untouched,
        _check_an_ambiguous_request_says_nothing,
        _check_the_registry_is_not_duplicated,
        _check_no_path_authority_is_widened,
    )
    for check in checks:
        check()
        print(f"ok {check.__name__}")
    print(f"dressing prompt delivery: {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
