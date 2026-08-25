#!/usr/bin/env python3
"""Deterministic prompt-policy regression for cross-role/integration blocker handling."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.ExecutionCrew.prompts import implementer_prompt, test_author_prompt, validator_prompt


def main() -> int:
    common = {
        "task_id": "NSC-999",
        "title": "Prompt Policy Fixture",
        "task_contract": '{"id":"NSC-999"}',
        "gdd": "# GDD\nApproved behavior.\n",
    }

    implementer = implementer_prompt(
        **common,
        implementation_paths=("Assets/Scripts/Thing.cs", "Assets/Editor/ThingBuilder.cs"),
        new_implementation_paths=("Assets/Scripts/NewThing.cs",),
        pipeline_sidecars=("Assets/Scripts/NewThing.cs.meta",),
        other_role_paths=("Assets/Tests/NewThingTests.cs",),
    )
    assert "Test Author-owned work is not an Implementer blocker" in implementer
    assert "Do not modify test files" in implementer
    assert "generated or serialized integration artifact outside your implementation paths is not an Implementer blocker" in implementer
    assert "required regeneration/human-integration step" in implementer
    assert "Do not report blockers merely because Test Author work or a later deterministic human integration step remains" in implementer
    for required in ("EXISTING TRACKED FILES YOU MAY EDIT", "APPROVED EXACT NEW FILES YOU MAY CREATE", "PIPELINE-OWNED SIDECARS YOU MUST NOT CREATE OR EDIT", "do not treat that absence as a blocker"):
        assert required in implementer

    test_author = test_author_prompt(
        **common,
        policy="# Policy\n",
        implementation_patch="diff --git a/old b/new\n",
        implementation_paths=("Assets/Scripts/Thing.cs",),
        implementation_actual_paths=("Assets/Scripts/Thing.cs",),
        test_paths=("Assets/Tests/ThingTests.cs",),
        new_test_paths=("Assets/Tests/NewThingTests.cs",),
        pipeline_sidecars=("Assets/Tests/NewThingTests.cs.meta",),
    )
    assert "existing test inside your approved test paths" in test_author
    assert "explicitly supersedes" in test_author
    assert "updating that stale assertion is your responsibility rather than an Implementer blocker" in test_author
    assert "APPROVED EXACT NEW FILES YOU MAY CREATE" in test_author and "Do not create directories, helper/sibling files, or .meta files" in test_author

    validator = validator_prompt(
        **common,
        candidate_patch="diff --git a/old b/new\n",
        changed_paths=("Assets/Editor/ThingBuilder.cs",),
        implementer_output={"summary": "implemented", "blockers": []},
        test_author_output={"summary": "tests", "blockers": []},
    )
    assert "not-yet-regenerated artifact is a later human integration/runtime-evidence step" in validator
    assert "not by itself a source-level failure" in validator
    assert "Keep Unity/runtime gates not_proven" in validator
    assert "pipeline-generated asset identity" in validator

    print("ExecutionCrew prompt blocker-policy smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
