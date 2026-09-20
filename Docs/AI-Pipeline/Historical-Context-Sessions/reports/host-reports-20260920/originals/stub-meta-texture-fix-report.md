P34: crew-staged texture stub metas import as Cube/point-cookie

## Classification
Reproduced from committed evidence: the stub-meta guid scheme and its callers
are on main as written; the NSC-074/075 commit history shows the exact
failure and the workaround commits that patched it by hand after the fact.
Unity's import step itself was not re-run in this session (needs Vincent's
go for a Unity/EditMode check); the fix reproduces the input Unity saw
(GUID-only meta on a new PNG) and the output Unity is known to have produced
for that input from the recorded evidence below.

## Root cause
`Pipeline/ExecutionCrew/run_crew.py` `unity_meta_bytes()` (line 717 on base
`bdf618744`) wrote a 2-line GUID-only meta for every new `Assets/` file,
textures included. In Unity 6000.1.8f1 a PNG with such a stub imports with
the `TextureImporter`'s native defaults: `textureShape: 2` (Cube),
`cookieLightType: 2` (Point), `applyGammaDecoding: 1`; Unity never rewrites
an already-imported stub.

Evidence:
- commit f7cb0f478 staged 96 NSC-074 wizard frames with stub metas whose
  GUIDs equal `unity_meta_bytes`.
- NSC-075's builder then threw `InvalidDataException: Wizard source did not
  import as a Sprite` (`C:\nscrev\reports\nsc075\builder-run1.log:645`).
- workaround commits `0d28b0bf5` / `bf97d116c` force `textureShape=Texture2D`
  and reset cookie/gamma by hand; `664de19c2` then committed full metas with
  `textureShape: 1`.
- every non-stub image meta on main (344) has `textureShape: 1`; 119 are
  Unity's untouched new-texture default for this project (96 NSC-093 enemy
  walk metas, commit `981002959`, and 23 door source metas), byte-identical
  once the guid line is masked except for trailing spaces that commit
  `12d317b58` stripped from the door metas.

## Fix
Clone: `C:\nscrev\stub-meta-texture-fix`, branch `fix/stub-meta-texture`,
base `bdf618744c5f286d9d4e78e2fe05e244e0366e5f`.

- `8c8155365` — P34: failing test for texture stub metas
  (`Pipeline/ExecutionCrew/tests/unity_meta_bytes_test.py`, new file).
- `75fde39d0` — P34: write default TextureImporter metas for crew-staged
  textures. Changes:
  - `Pipeline/ExecutionCrew/run_crew.py`: extracted `unity_meta_guid(path)`
    from `unity_meta_bytes`; added `_TEXTURE_EXTENSIONS` (png/jpg/jpeg/tga
    /psd/gif/bmp/tif/tiff, case-insensitive) and `_TEXTURE_META_TEMPLATE`
    (the full Unity 6000.1.8f1 default `TextureImporter` meta, captured
    verbatim from `door_bonestone_broken_S_000.png.meta` @ `bdf618744`,
    whitespace-normalized per `12d317b58`, with a `{guid}` placeholder filled
    by plain string replace so the literal `{}`/`{x: ...}` YAML in the body
    are untouched). `unity_meta_bytes` now returns the template for texture
    extensions and the unchanged 2-line stub for everything else.
  - `Pipeline/AssistantControl/gauntlet_replay.py` `_meta_guid` (line 56):
    now calls `unity_meta_guid` instead of parsing `unity_meta_bytes(...)`
    text, since that parse (`split("guid: ",1)[1].strip()`) breaks once the
    meta has content after the guid line.
  - `Pipeline/ExecutionCrew/README.md` "Exact approved new files": documents
    that texture sidecars (the same extension list) get the Unity default
    `TextureImporter` meta with the same deterministic guid; other files
    keep the two-line form.

- `6bf1ac033`: P34 test tightening by the Pipeline Maintainer Agent. The test now imports the `run_crew` module and derives the expected guid from the documented formula. Before this, the test failed on base only with an ImportError; now it fails the texture assertions themselves. **Head: `6bf1ac033`.**

Verified `unity_meta_bytes` for
`Assets/NoSafeCircle/DoorPrototype/Art/Doors/Source/door_bonestone_broken_S_000.png`
is byte-identical to the committed door meta with only the guid line masked.
The Maintainer independently re-checked this. The template is also byte-identical to the NSC-093 enemy walk meta that Unity generated (`enemy_melee_e_walk_00.png.meta`) once Unity's trailing spaces are stripped: 2969 bytes, LF, no CR.

## Re-grep for other `unity_meta_bytes(`/`"guid: "` consumers
All remaining call sites only ever pass `.cs` paths (unaffected 2-line stub
form), so no other production code needed changes:
- `Pipeline/AssistantControl/gauntlet_replay.py:240` (test `.cs` sidecar) — unchanged, fine.
- `Pipeline/AssistantControl/test_gauntlet_replay.py:117,119,126` — test file, `.cs` sources only.
- `Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py:405,406,414` — test file, non-texture fixture paths.
- `Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:157,283` — test file, `.cs` sources only.

## Tests
TEMP/TMP set to `C:\nscrev\tmp\stub-meta-texture` for every command.

| Command | Failing-before | Passing-after |
| --- | --- | --- |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.unity_meta_bytes_test` (head test file run against base code: `git worktree add bdf618744`, copy the current test in, run, remove worktree) | **6 run: 3 FAIL** (`test_new_texture_meta_is_a_default_texture_importer_meta`, `test_extension_matching_is_case_insensitive_for_ldr_textures`, `test_texture_meta_bytes_are_pinned`) **+ 1 ERROR** (`unity_meta_guid` absent on base, raised by `test_unity_meta_guid_matches_the_guid_line_for_both_kinds`) **+ 2 pass** (`test_non_texture_paths_are_unchanged_stub_metas`, `test_wizard_frame_guid_is_stable`) — corrected 2026-09-16, see FIX_FIRST section below; the table previously understated this at 5 run/2 FAIL from before `test_texture_meta_bytes_are_pinned` was added | 6 run, 0 failures |
| `python -B Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py` | 1 AssertionError (pre-existing, see below) | same AssertionError, pre-existing |
| `python -B -m unittest Pipeline.AssistantControl.test_gauntlet_replay` | not run before fix (new code path) | 5 run, 0 failures |
| `python -B -m Pipeline.TaskReviewAgent.tests.prepare_synthetic_gauntlet_smoke_test` (PYTHONPATH=clone) | not run before fix | 8 run, 0 failures |
| `python -B -m compileall -q Pipeline/ExecutionCrew Pipeline/AssistantControl` | n/a | exit 0 |
| `git diff --check bdf618744` | n/a | exit 0 (no whitespace errors) |

### Pre-existing failure (not caused by this fix)
`python -B Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py` fails
with `AssertionError` at line 335 (`default_full_state.calls` role-order
check) both at base `bdf618744` (`git switch --detach`) and on
`fix/stub-meta-texture`. Not fixed here; out of scope for P34.
The smoke test stops at line 335, so its sidecar-write assertions (about lines 405-414) are never reached. The crew's sidecar write path (`run_crew.py`, about lines 2508 and 2551, unchanged by this fix) has no passing end-to-end test today. The new unit test covers the bytes that path writes.

### assistant/restored-meta-companion-fix (807bd7b86) — read-only check
`git switch --detach 807bd7b86`; `python -B -m unittest
Pipeline.AssistantControl.test_assistant_restored_candidate`: 8 run, 0
failures. Not merged or cherry-picked; branch left untouched.

## Risks / follow-ups
- HDR formats (`.exr`/`.hdr`) and other importer types (audio, models) still
  get the GUID-only stub; theoretical until confirmed against a real Unity
  import, since evidence here only covers LDR textures.
- No Unity EditMode import was actually re-run in this session; Vincent's go
  needed before relying on this for a live crew run. **Agreed plan:** during merge verification the Game Agent runs a Unity 6000.1.8f1 batchmode check in `C:\nscrev\branch-verify`. Using a scratch PNG plus a `unity_meta_bytes` meta, the check confirms:
  1. the meta bytes are unchanged after import;
  2. the importer is a `TextureImporter` with `textureShape == Texture2D`, and `LoadAssetAtPath<Texture2D>` is non-null;
  3. after `textureType = Sprite` and `SaveAndReimport`, a Sprite loads.

  If Unity rewrites the whitespace-normalized template, switch to Unity's exact trailing-space form, which the committed NSC-093 metas show.
- Supporting evidence, not proof: the canonical checkout has 0 dirty metas in either the door (stripped) or the NSC-093 (trailing-space) group.
- GUID-only texture metas on main `bdf618744`: none (0 of 347 image metas). The 288 that remain are only on the three superseded NSC-074 review branches.
- **Maintainer's view on `807bd7b86`:**
  - It is compatible. It compares a restored candidate's `.meta` with `unity_meta_bytes(path)` at runtime, so after P34 it expects the texture template.
  - It shares no files with this fix, and its own test is 8/8 at its commit.
  - It relaxes a refusal rather than adding a gate: before it, every `.meta` outside the path scope was refused. After it, only a companion that isn't deterministic is refused, for example an old texture stub or one a builder rewrote.
  - Merge it after P34 or together with it. It still needs the Game Agent's trial merge on current main, because its base is old.
- If `assistant/restored-meta-companion-fix` (807bd7b86) lands later,
  restored candidates staged under the old texture-stub scheme will no
  longer byte-match `unity_meta_bytes` for texture paths; that branch's own
  restore logic should be checked against the new template before merge.

## Independent review (2026-09-16)

**VERDICT: APPROVE** from a fresh `pipeline-reviewer` on `bdf618744..6bf1ac033`. No blocking or major findings.

What the reviewer checked:
- **Consumers.** It checked every consumer of sidecars and `unity_meta_bytes`, including retry seeding, `local_candidate_commit`, `execution_routing`, `graph_controller`, materialization, synthetic validation, the migration JSON and the Unity `WizardCardinalSourceAuditTests`. None assumes the two-line form for textures.
- **Crew code.** The immutable crew manifest doesn't pin a hash of `run_crew.py`, and no PSD importer package is installed.
- **Template fidelity.** It confirmed byte-exact matches against the door meta and the NSC-093 meta.
- **Failing-before.** It reproduced 2 FAIL and 1 ERROR against base code.
- **Tests at head.** `unity_meta_bytes_test` 5/5, `test_gauntlet_replay` 5/5 and `prepare_synthetic_gauntlet_smoke_test` 8/8 pass. `execution_crew_smoke_test` stops at line 335 on both base and head, which is pre-existing.

Follow-ups:
- **Fixed in `11dead09f`** (head):
  - the test pins the texture meta's sha256 (`6031dc76…a9dc7fa`), so an accidental template edit fails;
  - the `run_crew.py` comment now points at the README, and the README names the HDR stub exception.
- **Left as is:** `Pipeline/ExecutionCrew/prompts.py:222` still calls sidecars "minimal".
- **Unity import check PASSED** (Game Agent, 2026-09-16). It ran on trial merge `090e7372e` of this branch onto main `95492e43d` in `C:\nscrev\branch-verify`, with Unity 6000.1.8f1 batchmode. Result file: `C:\nscrev\reports\p34-import-check\result.txt`.
  - A meta written by `unity_meta_bytes` (3000 bytes) stayed byte-identical after `ImportAsset(ForceUpdate)`.
  - The importer was a TextureImporter with `textureShape=Texture2D` and `textureType=Default`, and `LoadAssetAtPath<Texture2D>` returned non-null.
  - After switching to Sprite (Single) and calling `SaveAndReimport`, the Sprite loads.
  - Unity exited 0, and no tracked file changed. The whitespace-normalized template needs no change.

## Codex FIX_FIRST follow-ups (2026-09-16)

Two findings from a Codex review on `bdf618744..11dead09f`, both addressed in `a777952d8` (new head). Clone, branch and TEMP/TMP unchanged.

**Finding 1 [major], reproduced.** `seed_retry_candidate`'s `preimage_comparison.returncode == 0` "applied" branch (`run_crew.py`, was lines 1257-1296) reapplied a prior `candidate.patch`, including its pipeline-owned `.meta` sidecars (`retry.candidate_sidecars`), without checking them against `unity_meta_bytes`. The role writers (about lines 2655, 2698) only generate a sidecar when its source file was absent from the pre-role snapshot, so a human-review retry of a candidate staged before this fix kept and re-delivered the old GUID-only PNG stub.

Fix: in that branch, after the existing regular-file checks and before `return "applied"`, for each path in `retry.candidate_sidecars`, compute `expected = unity_meta_bytes(sidecar[:-len(".meta")])` and overwrite the seeded file only if its bytes differ. The other branch (prior candidate committed exactly) is untouched — tracked metas are never regenerated. Confirmed `retry_seed_snapshot = snapshot(clone)` (call site, `run_crew.py` about lines 2616-2621) is taken *after* `seed_retry_candidate` returns, so this refresh lands in that snapshot and is not misread as a model correction.

New test: `Pipeline/ExecutionCrew/tests/retry_sidecar_refresh_test.py` (new file), one test building a throwaway git repo, seeding a reconstructed prior candidate with a stale GUID-only PNG stub plus an already-correct `.cs` sidecar, and asserting `seed_retry_candidate` returns `"applied"` with the PNG sidecar refreshed to `unity_meta_bytes(png_path)` and the `.cs` sidecar left byte-identical.

Failing-before/passing-after (`git stash push --keep-index -- Pipeline/ExecutionCrew/run_crew.py` to revert only the fix, test file untouched; then `git stash pop`):

| Command | Failing-before | Passing-after |
| --- | --- | --- |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test` | 1 run, 1 FAIL on the sidecar-bytes assertion (`AssertionError` comparing the seeded stub to `unity_meta_bytes`), not a setup error | 1 run, 0 failures |

**Finding 2 [minor], fixed.** The report's failing-before table for `unity_meta_bytes_test` was stale from before `test_texture_meta_bytes_are_pinned` was added. Re-verified against base `bdf618744` (`git worktree add`, current test file copied in): **6 run, 3 FAIL + 1 ERROR + 2 pass**. At head `a777952d8`: **6 run, 0 failures**. The table above is corrected accordingly.

Commit: `a777952d8` on `fix/stub-meta-texture` (base `bdf618744`, prior head `11dead09f`).

Verification at the new head (all under `TEMP=TMP=C:\nscrev\tmp\stub-meta-retry`):
- `unity_meta_bytes_test`: 6/6.
- `retry_sidecar_refresh_test`: 1/1.
- `Pipeline.AssistantControl.test_gauntlet_replay`: 5/5 (unaffected).
- `python -B -m compileall -q Pipeline/ExecutionCrew`: exit 0.
- `git diff --check bdf618744`: exit 0.
- `git ls-files --eol` on both changed files: blobs `i/lf`.
- Clone ends clean after commit.

No providers, Docker or Unity were run for this pass.

- **Final:** head `2e20a2953`. `a777952d8` refreshes pipeline-owned sidecars when a retry seeds a prior candidate. `2e20a2953` makes the retry test set autocrlf=false like the crew clone and adds CREATE_NO_WINDOW. The same reviewer re-checked both commits and approved. Template bytes are unchanged since the Unity import check (sha256 pin `6031dc76...`).

## Codex FIX_FIRST round 2 (2026-09-17)

**Finding [major], reproduced.** `seed_retry_candidate`'s *other* branch — `preimage_comparison.returncode == 1`, "prior candidate committed exactly" (`run_crew.py`, was lines 1304-1337) — only compared the committed candidate-owned paths against the reconstructed prior candidate post-image's sha256, then returned `"already_present"` without ever checking those tracked sidecars against `unity_meta_bytes`. `a777952d8` had only fixed the sibling `"applied"` branch. Scenario: a pre-P34 candidate, including a GUID-only PNG `.meta`, was committed exactly (not just seeded into a disposable clone) and is retried after P34; the stale stub survives because it is tracked and byte-equal to the reconstructed prior post-image, so `equivalent` is true and the function returns early. Codex probe: `C:\nscrev\codex-jobs\codex-review-p34-stub-meta-merge2-20260917-0001\codex-tmp\probes\already_present_probe.py`; verdict `CODEX_VERDICT.json` in the same folder.

**Choice: (A) Refresh**, matching the applied branch. Proof it is accepted by the boundary checks, not merely made to pass:

- `retry.candidate_sidecars ⊆ retry.candidate_paths` is enforced when `RetryContext` is built (`run_crew.py:499`, `if set(candidate_sidecars) - set(candidate_paths): raise CrewBlocked(...)`), so every sidecar we might refresh is already one of `expected_paths` (`run_crew.py:1260`) and is proven `kind == "regular"` and tracked by the `equivalent` check just above the fix point (`run_crew.py:1328-1334`) — safe to read/overwrite.
- The refresh runs *after* `if snapshot(clone) != baseline: raise CrewBlocked(...)` (`run_crew.py:1323-1324`), so it cannot trip that "verification changed the clone" guard; it is a deliberate post-verification mutation, not a leak from the `prior_clone` reconstruction.
- Call site (`run_crew.py:2624-2631`, was 2616-2627): `retry_seed_snapshot = snapshot(clone)` is taken *after* `seed_retry_candidate` returns, so any bytes this branch rewrites land in that snapshot, exactly like the applied branch already relied on.
- Final candidate boundary check `allowed = set(implementation_paths) | set(test_paths) | pipeline_generated` (`run_crew.py:2803`, now ~2811) accepts a refreshed sidecar only if it is added to `pipeline_generated`. The pre-existing call site only did that `if retry_seed_mode == "applied"` (old `run_crew.py:2625-2626`) — a plain `already_present` branch on top of my sidecar-write would leave the boundary check exercising the same allow path as `applied` does today (already proven to pass by `a777952d8`'s review), **except** for one asymmetry I had to close: unlike `applied` (where every `candidate_sidecars` entry is a brand-new file, so it is unconditionally part of the diff), an `already_present` sidecar that already matched the contract is *not* rewritten and stays byte-identical to `identity.head` — it must **not** join `pipeline_generated`, or `expected_diff_paths` (`run_crew.py:2822-2826`, built from `present_new`, which only checks "is a regular file", not "did it change") would gain a phantom path that `final_paths` (an actual `changed_paths` diff) does not have, tripping "final Git diff paths differ from deterministic changed paths" (`run_crew.py:2827`) — this is exactly the guard scenario the task specifies. I fixed this by having the call site diff `baseline_clone` against the post-seed `retry_seed_snapshot` (`changed_paths`, `run_crew.py:686-687` `def changed_paths`) and intersect with `retry_context.candidate_sidecars`, so only sidecars whose bytes actually moved (in either seed mode) are added to `pipeline_generated`. This subsumes the old `applied`-only branch (verified: for `applied`, every candidate sidecar is a fresh `EntryState` vs. `baseline_clone`'s `None`, so the intersection is unchanged from the old unconditional `.update(...)`) and correctly yields an empty set for a fully-conformant `already_present` retry.
- `full_patch`/`diagnostic` (`run_crew.py:2843`, now ~2851) and `new_surface` (`run_crew.py:2730`, now ~2738) both fold in `pipeline_generated`, so a genuinely refreshed sidecar is captured in `candidate.patch`/`workspace_diagnostic.patch` the same way an `applied`-branch refresh already is.

Fix (`run_crew.py`):
- In the `already_present` branch, after the `equivalent` check and before `return "already_present"`: for each `sidecar` in `retry.candidate_sidecars`, compute `expected = unity_meta_bytes(sidecar[:-len(".meta")])` and overwrite `(clone / sidecar)` only if its current bytes differ.
- At the call site, replaced `if retry_seed_mode == "applied": pipeline_generated.update(retry_context.candidate_sidecars)` with `pipeline_generated.update(set(retry_context.candidate_sidecars) & set(changed_paths(baseline_clone, retry_seed_snapshot)))`, computed after `retry_seed_snapshot = snapshot(clone)`.

New tests in `Pipeline/ExecutionCrew/tests/retry_sidecar_refresh_test.py`:
- `test_stale_texture_sidecar_committed_pre_p34_is_refreshed_on_already_present_retry`: builds the prior candidate (PNG + GUID-only stub `.meta`, plus an already-conformant `.cs`/`.cs.meta` pair), builds `candidate_bytes` with `paths_patch`, **commits** those files exactly on top of the base commit (so `prior_source_head` is the pre-commit base and the current clone `HEAD` contains them, forcing the `already_present` branch), then asserts `seed_retry_candidate` returns `"already_present"`, the PNG `.meta` now equals `unity_meta_bytes(png)` with the same `guid:` line, the `.cs` sidecar is untouched, and `git status --porcelain` shows only the one refreshed path as a working-tree change.
- `test_already_conformant_committed_sidecar_is_unchanged_on_already_present_retry` (guard): a committed `.cs`/`.cs.meta` pair whose sidecar already matches the contract; asserts `"already_present"`, a byte-identical sidecar, an empty `git status --porcelain`, and `snapshot(clone) == baseline` (nothing touched).

Failing-before/passing-after (`git stash push --keep-index -- Pipeline/ExecutionCrew/run_crew.py` to revert only the fix, test file untouched; `TEMP=TMP=C:\nscrev\tmp\stub-meta-v3`):

| Command | Failing-before | Passing-after |
| --- | --- | --- |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test` | 3 run, 1 FAIL on the assertion comparing the refreshed `.meta` to `unity_meta_bytes` (`AssertionError`, not a setup error); the other 2 (pre-existing `applied` test and the new conformant-guard test) pass unmodified | 3 run, 0 failures |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test Pipeline.ExecutionCrew.tests.unity_meta_bytes_test` | n/a | 9 run, 0 failures |
| `python -B -m unittest Pipeline.AssistantControl.test_gauntlet_replay` | n/a | 5 run, 0 failures |
| `python -B -m compileall -q Pipeline/ExecutionCrew` | n/a | exit 0 |
| `git diff --check bdf618744` | n/a | exit 0 |

Verification:
- `git ls-files --eol` on both changed files: blobs `i/lf` (unchanged convention); working copy of `run_crew.py` stays consistently CRLF, `retry_sidecar_refresh_test.py` stays consistently LF, matching each file's pre-existing on-disk state (checked byte-by-byte, no mixed EOL introduced).
- Template pin re-verified: sha256 of `unity_meta_bytes("Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north/frame_000.png")` is still `6031dc76c36047e05245900edeeada72f64159037c70d4a8cd15e4092a9dc7fa`.
- Clone ends clean after commit (`git status --short` empty).

Commit: `ff85f4dd6` on `fix/stub-meta-texture` (base `bdf618744`, prior head `2e20a2953`).

No providers, Docker or Unity were run for this pass. Not sent for review yet in this pass — pending the next `pipeline-reviewer` round.

## Round 3 fix (2026-09-17)

**Blocking finding, reproduced (fresh `pipeline-reviewer` on `ff85f4dd6`).** The round-2 fix made the `already_present` branch of `seed_retry_candidate` (`run_crew.py`, was lines 1343-1347) rewrite committed (tracked) candidate sidecars in place to the current `unity_meta_bytes`, and changed the call site (was lines 2641-2643) to `pipeline_generated = candidate_sidecars ∩ changed_paths(baseline_clone, retry_seed_snapshot)`. Two downstream readers define pipeline-generated paths as companions of *new* files only, and neither can ever see this rewrite:
- `Pipeline/TaskReviewAgent/local_candidate_commit.py:272-280` `_verified_pipeline_generated_paths` raises `CandidateIntegrationError` in already_present mode, because the png is existing authority and `new_implementation_paths` is empty — a refreshed candidate could never be committed.
- `run_crew.py:489-500` `load_retry_context` then fails a further retry: recorded `pipeline_generated_paths` (empty, from the committed run) no longer equals `candidate_sidecars`.

**Fix: fail closed instead of rewriting.** In the `already_present` branch, removed the rewrite loop. Before returning `"already_present"`, compute `stale = [sidecar for sidecar in retry.candidate_sidecars if (clone / sidecar).read_bytes() != unity_meta_bytes(sidecar[:-len(".meta")])]`; if non-empty, raise `CrewBlocked` naming every stale path ("committed Unity .meta sidecar(s) predate the current pipeline meta contract (P34); commit unity_meta_bytes for it (same GUID) in the source, then retry: ..."). Nothing is written to the clone in this branch any more. Restored the call site to exactly its pre-round-2 form: `if retry_seed_mode == "applied": pipeline_generated.update(retry_context.candidate_sidecars)` — the reviewer confirmed this is equivalent to the diff-based form in the one branch (`applied`) that still refreshes sidecars, and `already_present` no longer refreshes anything so it needs no entry in `pipeline_generated`. The `applied`-branch refresh (`a777952d8`) is unchanged. Added one sentence to `Pipeline/ExecutionCrew/README.md`'s "Exact approved new files" paragraph documenting the stop-and-name behavior.

Test changes in `Pipeline/ExecutionCrew/tests/retry_sidecar_refresh_test.py`:
- Renamed/rewrote `test_stale_texture_sidecar_committed_pre_p34_is_refreshed_on_already_present_retry` to `..._blocks_already_present_retry`: same setup (stale committed PNG stub + conformant `.cs` sidecar), now asserts `CrewBlocked` is raised, the message contains `PNG_META` and not `CS_META`, the committed `.meta` bytes are byte-identical to before the call, `git status --porcelain` is empty, and `snapshot(clone) == baseline`.
- Kept `test_already_conformant_committed_sidecar_is_unchanged_on_already_present_retry` unchanged (guard: nothing stale → still returns `"already_present"`, untouched).
- Kept `test_stale_texture_sidecar_is_refreshed_to_current_contract_on_seed` unchanged (the `applied` branch still refreshes).
- Did not add a separate unit test for "an already_present retry with no stale sidecars leaves `pipeline_generated` unpopulated from `candidate_sidecars`": that is a property of the restored call site (`if retry_seed_mode == "applied": ...`), one level above `seed_retry_candidate` itself, and per the brief I'm stating it here instead of writing a test that would just re-assert the literal call-site code. It was already covered end-to-end at `a777952d8`'s review (the pre-round-2 form was reviewed and approved), and this round restores that exact form.

Failing-before/passing-after (`TEMP=TMP=C:\nscrev\tmp\stub-meta-v31`; failing-before shown via `git stash push --keep-index -- Pipeline/ExecutionCrew/run_crew.py`, which reverts only the production fix while keeping the new test):

| Command | Failing-before | Passing-after |
| --- | --- | --- |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test` | 3 run, 1 FAIL: `AssertionError: CrewBlocked not raised` (at ff85f4dd6's `run_crew.py`, the already_present branch silently rewrites instead of blocking) | 3 run, 0 failures |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test Pipeline.ExecutionCrew.tests.unity_meta_bytes_test` | n/a | 9 run, 0 failures |
| `python -B -m unittest Pipeline.AssistantControl.test_gauntlet_replay Pipeline.AssistantControl.test_revision_feedback_integration Pipeline.AssistantControl.test_revision_completion` | n/a | 8 run, 0 failures |
| `python -B -m compileall -q Pipeline/ExecutionCrew` | n/a | exit 0 |
| `git diff --check bdf618744` | n/a | exit 0 |

Verification:
- `git ls-files --eol` on all three changed files: blobs `i/lf`. Working-copy conventions unchanged from round 2 (`run_crew.py`/`README.md` CRLF, `retry_sidecar_refresh_test.py` LF — each file's pre-existing on-disk state, confirmed byte-by-byte; no mixed EOL introduced).
- Template pin re-verified: sha256 of `unity_meta_bytes("Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Source/PixelLab/feminine-dark/selected/walk/north/frame_000.png")` is still `6031dc76c36047e05245900edeeada72f64159037c70d4a8cd15e4092a9dc7fa`.
- Clone ends clean after commit.

Commit: `5a603085e` on `fix/stub-meta-texture` (base `bdf618744`, prior head `ff85f4dd6`). New head: `5a603085e`.

No providers, Docker or Unity were run for this pass. Next: a fresh `pipeline-reviewer` round on `bdf618744..5a603085e` before handoff to the Game Agent.

## Codex round 3 fix (2026-09-17)

Branch rebased onto local `main` `32c6223d3` in between rounds; head before this
pass was `7b8784e00` (round 3's `5a603085e` content, rehashed by the rebase).
Verdict: `C:\nscrev\codex-jobs\codex-review-p34-stub-meta-v3-20260917\CODEX_VERDICT.json`
(`FIX_FIRST`).

**Finding [major], reproduced.** The round-3 fail-closed remediation is a dead end.
`seed_retry_candidate`'s `already_present` branch (`run_crew.py`, was around line
1336) raises `CrewBlocked` naming the stale sidecar and tells the operator to
commit the current `unity_meta_bytes(owner)` for it and retry. But that branch's
equivalence check (was lines ~1327-1334, run *before* the stale-sidecar check)
compares every `expected_paths` entry, sidecars included, only against the
reconstructed prior-candidate post-image's sha256. After the operator commits the
corrected meta, its bytes now differ from the old reconstructed stub, so
`equivalent` is false and the function raises `"prior candidate.patch neither
applies cleanly nor is already present at the current source HEAD"` before the
stale-sidecar check ever runs — the same human-review retry can never resume.
Codex reproduced this with its own probe (`.review-support/probe_retry_remediation.py`
in the review job clone).

**Fix (`run_crew.py`, in the `already_present` branch's equivalence computation):**
for a path in `retry.candidate_sidecars` only, accept the current committed bytes
if they equal *either* the reconstructed prior-candidate bytes *or* the current
`unity_meta_bytes(sidecar[:-len(".meta")])`; every other path keeps the exact
comparison unchanged. A committed sidecar that equals neither is still refused by
the same equivalence failure (message unchanged, still names the exact stale
path via the existing `stale` check below it, which is otherwise untouched).
This lets a conformant-after-correction sidecar pass equivalence, so the stale
check below it finds nothing, the retry returns `"already_present"` and writes
nothing — `pipeline_generated` is unaffected (already_present adds no sidecars,
per round 3), so `local_candidate_commit._verified_pipeline_generated_paths` and
`load_retry_context` see the same semantics already approved for a conformant
already_present retry. Added a two-line comment above the check.

Test (`Pipeline/ExecutionCrew/tests/retry_sidecar_refresh_test.py`), extending
`test_stale_texture_sidecar_committed_pre_p34_blocks_already_present_retry`:
1. unchanged step — the stale committed stub still raises `CrewBlocked` naming
   `PNG_META`, not `CS_META`, clone untouched.
2. new step — commit `unity_meta_bytes("Assets/X/a.png")` to `Assets/X/a.png.meta`
   in the test repo, exactly as the message instructs; take a fresh baseline.
3. new step — call `seed_retry_candidate` again with the same `RetryContext`; it
   now returns `"already_present"` with the clone unchanged (`git status
   --porcelain` empty, `snapshot(clone) == corrected_baseline`).
4. new guard step — committing some other, non-conformant meta over that still
   raises `CrewBlocked`, and the clone is unchanged.

Failing-before shown via `git stash push --keep-index -- Pipeline/ExecutionCrew/run_crew.py`
(reverts only the production fix, keeps the new test steps), then `git stash pop`.
`TEMP`/`TMP` = `C:\nscrev\tmp\stub-meta-v32` for every command below.

| Command | Failing-before | Passing-after |
| --- | --- | --- |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test` | 3 run, 1 ERROR: `CrewBlocked: prior candidate.patch neither applies cleanly nor is already present at the current source HEAD` raised at step 3 (`run_crew.py:1336`), instead of returning `"already_present"` | 3 run, 0 failures |
| `python -B -m unittest Pipeline.ExecutionCrew.tests.retry_sidecar_refresh_test Pipeline.ExecutionCrew.tests.unity_meta_bytes_test` | n/a | 9 run, 0 failures |
| `python -B -m unittest Pipeline.AssistantControl.test_gauntlet_replay` | n/a | 5 run, 0 failures |
| `python -B -m unittest Pipeline.AssistantControl.test_revision_feedback_integration Pipeline.AssistantControl.test_revision_completion` | n/a | 3 run, 0 failures |
| `python -B -m compileall -q Pipeline/ExecutionCrew` | n/a | exit 0 |
| `git diff --check 32c6223d3` | n/a | exit 0 |

Verification:
- `git ls-files --eol` on both changed files: blobs `i/lf` (unchanged convention).
- Template pin re-verified via `test_texture_meta_bytes_are_pinned` (head test
  suite, passing): sha256 of `unity_meta_bytes(WIZARD_FRAME_PATH)` is still
  `6031dc76c36047e05245900edeeada72f64159037c70d4a8cd15e4092a9dc7fa`.
- Clone ends clean after commit.

Commit: `459875cef` on `fix/stub-meta-texture` (base `32c6223d3`, prior head `7b8784e00`). New head: `459875cef`.

No providers, Docker or Unity were run for this pass.

## Final handoff state (2026-09-17)

- **Tip:** `412e5f4b4` on `fix/stub-meta-texture`, rebased onto local main `15d304390`. No overlap with main, and branch content is identical to the reviewed commits.
- **Codex reviews:**
  - v3, job `codex-review-p34-stub-meta-v3-20260917`, found the dead-end remediation. Fixed in 459875cef.
  - v4 (`a6c345faa`), job `codex-review-p34-stub-meta-v4-20260917`: FIX_FIRST with a single **minor** finding; the three substantive retry gaps are confirmed closed. The finding was that the already-present refusal didn't name a diverging sidecar. It is fixed in `a8a17a98b` (rebased into the tip), and a Fable reviewer confirmed the accept/refuse logic is unchanged and only the message grew. Failing-before was shown.
- **Fable reviewer:** APPROVE on every round (a777952d8, 2e20a2953, 5a603085e, 459875cef, a8a17a98b).
- **Tests at tip:** retry_sidecar_refresh_test, unity_meta_bytes_test and test_gauntlet_replay, 14/14. `git diff --check` is clean.
- **Unity:** the import check passed on the template (Game Agent); template bytes unchanged (sha256 `6031dc76…`).
