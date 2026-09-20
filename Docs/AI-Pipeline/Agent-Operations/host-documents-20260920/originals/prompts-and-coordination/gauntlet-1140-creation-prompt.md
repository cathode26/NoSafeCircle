# Claude prompt: create a fresh NSC-1140 Gauntlet

Use **Claude Sonnet, high effort**.

Work only in a new disposable Git worktree or clone. Use `C:\NSC\GauntletFresh1130-20260912-1` as the reference implementation, but create the new project at `C:\NSC\GauntletFresh1140-20260912-1`. Do not alter or run the 1130 project, the live 1130 run, `NoSafeCircle/main`, Docker, providers, GitHub Issues, or any existing checkout.

Create a fresh, unprocessed replay of the same eight-node Gauntlet graph using these exact identity mappings:

- `NSC-1130 -> NSC-1140`: decomposition parent, no dependencies
- `NSC-1131 -> NSC-1141`: isolated-value implementation, no dependencies
- `NSC-1132 -> NSC-1142`: isolated-value implementation, no dependencies
- `NSC-1133 -> NSC-1143`: isolated-value implementation, no dependencies
- `NSC-1134 -> NSC-1144`: isolated-value implementation, no dependencies
- `NSC-1135 -> NSC-1145`: decomposition parent, depends on `NSC-1141`
- `NSC-1136 -> NSC-1146`: decomposition parent, depends on `NSC-1145`
- `NSC-1137 -> NSC-1147`: isolated-value implementation, depends on `NSC-1146`

Preserve the behavior and graph shape of the current 1130-1137 contracts, including the strengthened complete/injective decomposition-obligation mappings. Rename every task identity, title, reconciliation key, class, test, file path, expected value, dependency, completion-gate filter, provenance field, and policy entry consistently to 1140-1147.

Do **not** pre-create decomposition children. The allocator must assign child IDs at runtime. In particular, do not create `NSC-1148` or later contracts. The fresh source must contain only the eight initial contracts.

Create the matching Unity EditMode fixture files for:

- `GauntletReplay1140AlphaTests` and `BetaTests`
- `GauntletReplay1141Tests`
- `GauntletReplay1142Tests`
- `GauntletReplay1143Tests`
- `GauntletReplay1144Tests`
- `GauntletReplay1145AlphaTests` and `BetaTests`
- `GauntletReplay1146AlphaTests` and `BetaTests`
- `GauntletReplay1147Tests`

Do not create any implementation outputs such as `Gauntlet114x.cs` or their `.meta` files. Those are the work the crews must perform. Generate all required `.meta` GUIDs from the new paths using the repository's canonical deterministic helper/rule; do not copy the 1130 GUIDs.

Update `Pipeline/TaskGraph/WORK_ID_MAP.json` and `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`, including each new decomposition parent's authoritative child template, validation variants, complete obligation mapping, and correctly recomputed `parent_task_contract_sha256`. Preserve formatting and line endings. Remove all 1130-1139 Gauntlet contracts, test fixtures, map/policy entries, generated children, task outputs, and run-derived state from the new disposable copy only, so they cannot appear beside the 1140 graph.

Do not copy `.task-review-agent`, AssistantControl state, controller journals, checkouts, worker receipts, crew output, local acceptance commits, or run artifacts. The new graph must begin with all eight initial tasks genuinely unstarted.

Validate before committing:

1. `python Pipeline/TaskGraph/taskcontrol.py validate` passes.
2. The graph is acyclic and has exactly the dependency edges listed above.
3. Exactly `NSC-1140` through `NSC-1147` are the initial Gauntlet contracts; no generated child exists yet.
4. No `Gauntlet114x` implementation output exists.
5. No 1130-1139 identity remains in the new Gauntlet contracts, tests, map, or policy.
6. Decomposition policy audit passes for 1140, 1145, and 1146.
7. `git diff --check` passes.

Commit the setup as one commit. Do not launch the controller or any crew. Report the new path, branch, commit SHA, exact files changed, validation results, and any uncertainty.
