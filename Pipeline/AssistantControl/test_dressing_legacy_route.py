"""The legacy integration route refuses a dressing request before it mutates.

`CandidateIntegrator` detects only the default scene builder and calls the Unity
runner with no narrowed scope, so a registered dressing prefab either runs the
wrong builder or runs none -- and on that route it would find out only AFTER
applying the candidate and pushing. The refusal has to land at admission.

These call the guard directly with a duck-typed scope rather than constructing a
CandidateIntegrator: its __init__ calls refuse_production_operation(), so a real
instance cannot be built outside production. That is a deliberate limitation of
this file and it is stated here rather than implied -- it proves the GUARD, not a
full integration run.
"""

from __future__ import annotations

import unittest

from Pipeline.TaskReviewAgent.candidate_integration import (
    CandidateIntegrationError,
    CandidateIntegrator,
)
from Pipeline.TaskReviewAgent.contracts import ExecutionScopePlan
from Pipeline.TaskReviewAgent.door_prototype_materialization import (
    DRESSING_PREFAB_BUILDERS,
    DRESSING_ROOMS,
)

ROOM_SCENE = "Assets/Scenes/Rooms/LowerVault.unity"
ROOM_BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/Rooms/LowerVaultSceneBuilder.cs"


class _Accepted:
    def __init__(self, plan: ExecutionScopePlan) -> None:
        self.plan = plan


class _Scope:
    def __init__(self, accepted: _Accepted | None) -> None:
        self.accepted = accepted


TEST_PATH = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/LowerVaultSceneTests.cs"


def _plan(existing=(), new=()) -> ExecutionScopePlan:
    # ExecutionScopePlan refuses a plan with no implementation path and one with
    # no test path, so every fixture carries both. An "empty plan" case cannot
    # be built at all, which is the schema doing its job.
    existing = tuple(existing) or (ROOM_BUILDER,)
    return ExecutionScopePlan(
        existing_implementation_paths=existing,
        new_implementation_paths=tuple(new),
        existing_test_paths=(TEST_PATH,),
        new_test_paths=(),
    )


def _integrator(plan: ExecutionScopePlan | None) -> object:
    accepted = None if plan is None else _Accepted(plan)
    return type("Stub", (), {"scope": _Scope(accepted)})()


def _builder(room: str):
    for candidate in DRESSING_PREFAB_BUILDERS.values():
        if candidate.room == room:
            return candidate
    raise AssertionError(f"no registered dressing builder for {room}")


class LegacyRouteRefusesEveryRegisteredDressingPrefab(unittest.TestCase):
    def test_each_of_the_five_refuses_by_name(self) -> None:
        for room in DRESSING_ROOMS:
            builder = _builder(room)
            with self.subTest(room=room):
                with self.assertRaises(CandidateIntegrationError) as caught:
                    CandidateIntegrator._refuse_unsupported_dressing_route(
                        _integrator(_plan(new=(builder.prefab_path,)))
                    )
                message = str(caught.exception)
                self.assertIn(
                    "dressing_materialization_requires_assistant_control", message
                )
                self.assertIn(builder.prefab_path, message)

    def test_it_refuses_from_the_existing_paths_too_not_only_new(self) -> None:
        builder = _builder("FinalRoom")
        with self.assertRaises(CandidateIntegrationError) as caught:
            CandidateIntegrator._refuse_unsupported_dressing_route(
                _integrator(_plan(existing=(builder.prefab_path,)))
            )
        self.assertIn(
            "dressing_materialization_requires_assistant_control", str(caught.exception)
        )


class LegacyRouteLeavesEveryOtherRequestAlone(unittest.TestCase):
    """A refusal that fires on ordinary work would close the route entirely."""

    def test_an_ordinary_room_request_passes_the_guard(self) -> None:
        self.assertIsNone(
            CandidateIntegrator._refuse_unsupported_dressing_route(
                _integrator(_plan(existing=(ROOM_BUILDER,), new=(ROOM_SCENE,)))
            )
        )

    def test_an_unaccepted_scope_passes_the_guard(self) -> None:
        """Nothing is admitted yet, so there is nothing to refuse on."""
        self.assertIsNone(
            CandidateIntegrator._refuse_unsupported_dressing_route(_integrator(None))
        )

    def test_a_dressing_builder_source_alone_does_not_trip_it(self) -> None:
        """Only the registered PREFAB is the key, not its builder or catalog.

        The legacy route can carry a .cs edit perfectly well; what it cannot do
        is produce the prefab. Refusing on the source would block ordinary code
        work that this route still handles.
        """
        builder = _builder("BoneArchive")
        self.assertIsNone(
            CandidateIntegrator._refuse_unsupported_dressing_route(
                _integrator(_plan(new=(builder.builder_source_path,
                                       builder.catalog_path)))
            )
        )


class TheGuardIsCalledBeforeAnythingMutates(unittest.TestCase):
    def test_both_entry_points_call_it_first(self) -> None:
        """Source-level witness: the call is the FIRST statement in each body.

        A guard placed after `self.execution.require(...)` still refuses, but it
        refuses later than it claims to. The whole point is that nothing has been
        applied or pushed yet, so the position is the property under test.
        """
        import ast
        import inspect
        import textwrap

        for method in (CandidateIntegrator.stage_candidate,
                       CandidateIntegrator.integrate):
            with self.subTest(method=method.__name__):
                tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
                body = list(tree.body[0].body)
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    body.pop(0)  # docstring
                statement = body[0]
                self.assertIsInstance(
                    statement, ast.Expr,
                    f"{method.__name__} does something before it refuses",
                )
                self.assertEqual(
                    "self._refuse_unsupported_dressing_route()",
                    ast.unparse(statement.value),
                    f"{method.__name__} does not refuse before it does anything else",
                )


if __name__ == "__main__":
    unittest.main()
