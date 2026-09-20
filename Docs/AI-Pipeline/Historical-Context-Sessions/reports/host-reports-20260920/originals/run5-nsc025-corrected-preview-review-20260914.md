# NSC-025 corrected canonical graph preview — read-only review

**Decision requested:** authorize application of the exact corrected plan `GDP-07fb2284b1c4d47e036b49bed0d824f525b4e9c3626ae5afe1d30a3e3ef77824` to canonical local `main`, subject to the fresh-source and child-ID checks immediately before mutation. This report does not grant application authority.

**Source:** local canonical `main` at `3a565100697010e444e052dc008620509c0c0113`, clean when checked. This graph contains 87 task files and currently ends at NSC-088. The corrected preview allocates NSC-089 and NSC-090 and validates as 89 tasks / 160 dependency edges.

**Run 5 evidence:** the original provider-reviewed candidate `520f30cbfac24339ef127c297d3b4b1ed6e6d8dbbb566c9a8ce9a95868b42c8b` reached `review_ready` in three calls, but no graph changes were applied. Its plan was `GDP-320675f3e272a0e1c41be1c731a77df676a5cad5fd75d4e27e70c0082eca09c3`. The original review authenticates that original candidate only.

## Exact correction

Only two requirement strings in the NavMesh child change:

1. **NSC-089 AC-002** now explicitly names `Assets/NoSafeCircle/DoorPrototype/Tests/Editor/NavMeshAgentConfigurationTests.cs` as a file the child creates. The unchanged AC-002 text retains the runtime `GameplayNavigationSurface.cs` wrapper and only the authorized runtime `.asmdef` reference.
2. **NSC-089 VAL-001** keeps an in-memory test for component and agent configuration, but separately requires validation against the actual five-room scene materialized by the authorized canonical builder. That validation checks removal of the legacy `Floor`, one surviving `GameplayNavigation` owner, a NavMesh based on composed `FloorCollision` and obstacle colliders rather than visual Tilemaps, a complete agent path after scene load or the specified runtime rebuild, and one owner and usable path after a repeated authorized build. Validation-only tests must not save or modify the committed scene.

The second correction is necessary because `DoorSequenceBuilder.BuildCanonical` immediately returns when `targetScene.path` is not `Assets/Scenes/DoorPrototype.unity`. The original proposed `BuildInMemoryForTests()` gate could not exercise the five-room composition or legacy-floor removal that caused the Run 5 round-two defect.

The corrected proposal retains the same parent mapping, child resource partition, NSC-071 Bone Archive proof handoff, four named new paths, and six inbound dependency rewrites from Run 5. NSC-090's door-passability child contract is unchanged.

## Validation and independent review

- The saved corrected candidate differs from the Run 5 result in exactly those two requirement strings.
- `plan_graph_delta` validates the corrected proposal on canonical main and produces `GDP-07fb2284b1c4d47e036b49bed0d824f525b4e9c3626ae5afe1d30a3e3ef77824`, allocating NSC-089/NSC-090.
- A read-only `plan_graph_apply` fresh-source preflight returns `fresh` for the corrected plan. No graph materialization or canonical edit was performed.
- Astra independently reviewed the exact corrected preview, checked the builder-path issue and graph semantics, and **approved the corrected preview for presentation to Vincent**, finding no remaining blocker. Astra's feasibility judgment is that authorized builder materializations occur in the isolated implementation checkout; validation loads each result without saving it. The task worker must specify and prove saved NavMesh data or a real runtime rebuild, not a test-only bake.

## Application boundary

`AGENTS.md` says D1B.2 `review_ready` is `review_only_not_applied` and does not authorize graph application. `apply_graph_delta()` requires independent review and external authorization of the exact immutable plan. If Vincent authorizes this corrected plan, recheck canonical HEAD, task IDs, proposal identity, and fresh-source status, then use the graph-application workflow and validate the materialized graph. Any intervening graph change requires a new plan and decision. Integrate only the proved guidance commits; do not merge the unrelated research branch wholesale. CI/Unity checks and the previously authorized guarded fast-forward push follow only after the combined local main candidate passes.

**Artifacts:**

- Corrected proposal: `C:\nscrev\reports\run5-nsc025-corrected-preview\corrected_decomposition_result.json`
- Corrected immutable plan: `C:\nscrev\reports\run5-nsc025-corrected-preview\corrected_graph_delta.json`
- Artifact SHA-256: proposal `8567161d2825b7deefaaa29854dd2485ca06290a765f6fa4f2e5c718edc78098`; plan `975d1616b7a013513b67abcf33f65358a6873abe8f3fa516f8b74c760b02f2a2`.
- Before/after fields and preflight: `C:\nscrev\reports\run5-nsc025-corrected-preview\correction_summary.json`
- Preparation script: `C:\nscrev\reports\prepare_run5_nsc025_corrected_preview.py`

No provider calls, Unity, Docker, graph application, merge, or push were performed while preparing this preview.
