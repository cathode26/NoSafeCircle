# NSC-077 Unity verification plan (Game Agent), contract rev 9

This plan uses the `unity-runner` helper (Sonnet), which never commits, stashes or cleans. The Game Agent handles checkout, comparison and commits.

## Rev 9 VAL-007 in short
- Build twice.
- After the second build, every generated file is byte-identical to the first build's output, except `Assets/Scenes/DoorPrototype.unity`, whose fileIDs regenerate on every save.
- Commit the builder output with the scene saved by Build 2.
- The saved-scene content is proven by EnemyArtIntegrationTests (VAL-003) in the Edit Mode filter, run against that committed scene.
- Base: local main at or after `74207b22f`. The whole DoorPrototypeSceneBuilderTests fixture must pass.
- Record the candidate's exact base commit.

## Step 0 (Game Agent)
1. Check that no Unity.exe is running and that `git -C C:/nscrev/branch-verify status --porcelain` prints nothing.
2. In the Codex clone, rebase the candidate onto current main: `git fetch origin main`, then `git rebase origin/main`. Record the base.
3. `git -C C:/NSC/NSC/NoSafeCircle fetch C:/nscrev/nsc077-codex +codex/nsc077-moving-enemy-art-20260917:refs/heads/codex/nsc077-moving-enemy-art-20260917`
4. `git -C C:/nscrev/branch-verify checkout --detach <TIP>`

## Build 1 (unity-runner, builder once, log builder-run1.log)
After its EOL-only cleanup, the runner lists the remaining changed, added and deleted paths. The Game Agent then:
1. saves `git status --porcelain --untracked-files=all` as status-build1.txt;
2. saves a SHA-256 manifest of every listed file except the scene as hashes-build1.txt (`sha256sum`; deleted paths recorded as DELETED).

## Build 2 (Game Agent runs Unity directly; `-quit`; log builder-run2.log)
1. Restore EOL-only churn: `git diff --ignore-cr-at-eol --quiet -- <path>`, then `git checkout -- <path>`.
2. Save the status and a new hash manifest.
3. They must equal Build 1's, except for the scene. Any difference fails VAL-007: list it and stop.

## Game Agent commit
1. Write exact paths to C:\nscrev\reports\nsc077\unity\materialize-paths.txt (groups a-d; group e must be empty or explained).
2. `git -C C:/nscrev/branch-verify add --pathspec-from-file=...`
3. Commit with `-c user.name="No Safe Circle Branch Recovery" -c user.email="branch-recovery@nosafecircle.invalid"` and `-F C:/nscrev/reports/nsc077/materialize-message.txt`.
4. Check that the tree is clean.

## Tests (unity-runner on the materialize commit)
Use the filter strings byte for byte (authoritative_validation_policy.json).
- EditMode: `NoSafeCircle.DoorPrototype.Tests.Editor.EnemyArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.WizardArtIntegrationTests;NoSafeCircle.DoorPrototype.Tests.Editor.DoorPrototypeSceneBuilderTests`
- PlayMode: `NoSafeCircle.DoorPrototype.Tests.EnemyAnimationPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLanternWispCasterPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyPursuitDoorCrossingPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyTargetKnowledgePlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyHealthPlayModeTests;NoSafeCircle.DoorPrototype.Tests.ActiveEnemyRegistryPlayModeTests;NoSafeCircle.DoorPrototype.Tests.EnemyLockedDoorAttackPlayModeTests;NoSafeCircle.DoorPrototype.Tests.DoorEnemyPassabilityPlayModeTests;NoSafeCircle.DoorPrototype.Tests.WizardAnimationPlayModeTests`
- Report per-fixture counts, and flag any fixture with 0 tests. Every test must pass.

## Optional extra evidence
`C:\nscrev\reports\nsc077\evidence-tools\` holds NscSceneSnapshot.cs, run_snapshot.sh and cleanup_snapshot.sh: a fileID-free scene snapshot, dry-run verified on 74207b22f. Rev 9 does not require it.
