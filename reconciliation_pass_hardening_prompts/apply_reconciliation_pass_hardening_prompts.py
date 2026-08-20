from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

PATCHES = {
    "Pipeline/Reconciliation/prompts/reconcile.md": r'''

---

# Verification-pass hardening: current approved configuration and evidence rules

This section reflects the current GDD and supersedes older retry-hardening
language where they conflict.

## Approved Unity packages are no longer unresolved design

The current GDD explicitly approves:

- Unity 2D Tilemap Editor: `com.unity.2d.tilemap`
- Unity AI Navigation: `com.unity.ai.navigation`

Do not preserve navigation technology as an unresolved human architecture
question. If an approved package is absent from `Packages/manifest.json`, that
is a concrete missing project-configuration prerequisite. Represent the
required configuration work rather than silently treating the package as
installed or treating the approved technology as undecided.

The gameplay navigation/locomotion foundation consumes Unity AI Navigation and
locomotion-dependent enemy work depends on that foundation.

## Delivery requirement versus actionable configuration work

A required Windows build remains a `delivery_requirement`, but a concrete
repository configuration gap needed to satisfy that delivery obligation may
also require an open implementation/configuration work item.

Example: if `ProjectSettings/EditorBuildSettings.asset` contains no registered
gameplay scene, do not describe the entire Windows-build requirement as merely
`not_assessable`. The active local build target may be unassessable, but zero
registered scenes is a known incomplete configuration fact. Preserve the
Windows delivery requirement AND represent the actionable build-configuration
work needed to register the canonical gameplay scene / Windows Standalone
configuration.

## Dependencies must be structural, not hidden in notes

If a feature or deferred-content node states that it consumes an existing
implementation/foundation, preserve that prerequisite in `depends_on` when the
target must exist first. `notes` is not a substitute for a dependency edge.
Feature nodes may depend on concrete implementation/artifact prerequisites even
though the feature itself is not dispatchable.

Current examples include:

- five-room content consumes the reusable Tilemap/SpriteRenderer foundation;
- encounter placement/content consumes the authored room spaces and encounter
  admission/cap foundation;
- enemy status-effect/displacement consumes the pursuit/search state contract
  for restoring the appropriate movement state.

## Staged restart validation

The GDD requires zero health to reset all run-persistent gameplay state. When
all five rooms do not yet exist, a restart implementation may still be a
bounded first-stage task if its acceptance criteria are phrased as resetting
all run-carrying state that currently exists and remaining extensible to newly
added persistent systems without redesign. Do not claim a missing five-room
scenario can already be fully validated.

Represent dependencies on persistent-state owners when their interfaces must
exist to implement/reset them, and keep later full-floor validation as a
validation requirement when appropriate.

## Writer inventory for exclusive resources

Before returning the candidate, perform a writer inventory for each known
non-merge-safe resource. Every otherwise-concurrent task expected to modify the
same resource must carry the identical exclusive-resource key.

Pay particular attention to:

- shared future enemy locomotion/behavior surfaces: use one canonical
  `logical:` lock across pursuit/search, status/displacement, melee, ranged,
  and locked-door attack work when they can overlap;
- the shared prototype scene and `DoorPrototypeSceneBuilder.cs` for tasks that
  wire new scene-resident runtime components;
- `Assets/InputSystem_Actions.inputactions` when movement/interaction work will
  consume or modify the shared Input System actions asset;
- a shared asmdef when package-dependent implementation will modify it;
- `Packages/manifest.json` and relevant `ProjectSettings/` files for approved
  package/build configuration work.

Do not add locks merely for reads. Do not replace true prerequisites with
locks.

## Evidence discipline for negative and complete claims

Before saying a capability exists "nowhere in the project", inspect relevant
asset/configuration types as well as `.cs` files. For cursor input specifically,
inspect `.inputactions` assets if present. Existing mouse bindings are not the
same thing as an implemented cursor-world-target gameplay interface, but they
must not be erased by an overbroad negative claim.

For scene-integrated work marked complete, prefer evidence from the actual
serialized scene/prefab/current ProjectSettings in addition to builder code or
tests when the requirement depends on integration state. A builder's ability to
create state is not proof that the current serialized state contains it.

## Required feedback and character presentation

The current GDD explicitly requires continuous player-facing health feedback.
Represent that as an acceptance criterion/responsibility of the player-health
system unless a separate UI responsibility is clearly warranted.

The current GDD explicitly places the wizard and enemies in the reusable
world-space SpriteRenderer visual foundation. Preserve character
SpriteRenderer/isometric-sorting requirements as acceptance/validation criteria
of that visual foundation rather than leaving them ambiguous.
''',

    "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md": r'''

---

# Verification-pass hardening: explicit representation decisions

Use the current GDD's clarified ownership before classifying a required
statement as `ambiguous`.

- Continuous player-facing health visibility belongs to the Player Health
  responsibility as an acceptance criterion unless the candidate deliberately
  represents a separate health-UI implementation owner.
- Wizard/enemy world-space SpriteRenderer presentation and isometric sorting
  belong to the reusable Tilemap/SpriteRenderer visual-world foundation as
  acceptance/validation requirements, not as an unowned rendering requirement.
- The Windows build remains a `delivery_requirement`; however, concrete missing
  repository configuration needed to deliver it (for example no registered
  gameplay scene in EditorBuildSettings) may also require an open
  implementation/configuration work item. Do not treat the presence of a
  delivery record as proof that actionable configuration work is represented.
- Approved package requirements (`com.unity.2d.tilemap` and
  `com.unity.ai.navigation`) are required technical configuration, not deferred
  design. If missing, their required configuration must be represented.

Only use `ambiguous` after checking whether the current GDD now assigns the
requirement to an existing owner, acceptance criterion, validation requirement,
delivery requirement, or concrete configuration prerequisite.
''',

    "Pipeline/Reconciliation/prompts/verification/evidence_auditor.md": r'''

---

# Verification-pass hardening: repository evidence completeness

Apply these additional evidence checks.

## Negative-claim search breadth

Before accepting statements such as "no mouse input exists anywhere" or "no
configuration exists", verify relevant non-C# assets/configuration too. For
cursor/mouse input, inspect `.inputactions` assets when present. Distinguish:

- bindings/configuration exist but are not consumed by gameplay code; from
- the required gameplay interface actually exists.

Do not turn an unconsumed Input System asset into proof of completed cursor
world targeting, but do not erase it from repository truth.

## Serialized integration evidence

When a work item is marked complete and the requirement depends on scene/prefab
integration, look for current serialized scene/prefab evidence rather than
relying only on builder code, tests, or historical README claims. Builder
capability is not current integrated state.

If a completed camera/visual claim has only been tested against primitive
geometry while its remaining SpriteRenderer/isometric-sorting validation is
owned by a separate open visual-foundation item, require the candidate to name
that future validation owner explicitly rather than silently treating the
integration check as already complete.

## Package and build configuration evidence

Read `Packages/manifest.json` exactly when approved package availability is
relevant. Distinguish built-in modules such as `com.unity.modules.tilemap` or
`com.unity.modules.ai` from the GDD-approved packages
`com.unity.2d.tilemap` and `com.unity.ai.navigation`.

When Windows delivery is assessed, inspect committed
`ProjectSettings/EditorBuildSettings.asset` when available. Zero registered
scenes is a known incomplete configuration fact even if the developer's local
active build target remains unassessable.
''',

    "Pipeline/Reconciliation/prompts/verification/structure_auditor.md": r'''

---

# Verification-pass hardening: structural closure checks

The current GDD now resolves the navigation-technology decision: Unity AI
Navigation (`com.unity.ai.navigation`) is approved. Do not preserve an obsolete
"human must choose navigation technology" blocker. Instead verify that missing
approved package/configuration work and the shared navigation/locomotion
foundation are represented as concrete prerequisites.

## Notes are not dependency edges

Flag a prerequisite that appears only in `notes` when the owner genuinely
cannot be implemented/decomposed meaningfully before that prerequisite.
Deferred feature nodes may still carry dependencies on concrete
implementation/artifact foundations.

Current expected relationships include, when represented as separate nodes:

- five-room content -> Tilemap/SpriteRenderer visual foundation;
- encounter content/placement -> five-room content and encounter admission/cap
  foundation;
- status-effect/displacement -> pursuit/search state contract;
- locomotion-dependent enemy work -> shared navigation/locomotion foundation.

## State hand-back contract

The GDD says status-effect/displacement restores the appropriate pursuit/search
movement state and consumes the pursuit/search contract. If the candidate
represents pursuit/search and status/displacement as separate work items, do
not allow status/displacement to become ready before a stable pursuit/search
contract exists unless an explicit forward-declared interface contract is
represented and sufficient for implementation/validation.

## Full-run restart closure

Check that death/restart represents reset of run-persistent state, including
persistent enemy/registry state and door lifecycle/crossing state as those
systems come into existence. Do not force the first implementation to depend on
unwritten five-room content solely to reload a scene; instead verify that its
acceptance criteria are staged truthfully and that concrete persistent-state
owners are dependencies when their interfaces must be reset.

## Exclusive-resource writer inventory

For every logical/file/scene/prefab lock, identify all candidate work items that
may write the same integration surface during overlapping readiness windows.
Flag uneven lock coverage, not just pairwise collisions already named by the
candidate.

In particular, when a shared future enemy locomotion surface is represented by
`logical:enemy-locomotion-runtime`, verify that pursuit/search,
status/displacement, melee, ranged, and locked-door attack work all use the same
lock if their implementation boundaries can touch that surface concurrently.
Likewise verify shared scene-builder/scene, Input System actions, asmdef,
package-manifest, and build-settings writers when supported by repository/GDD
evidence.
''',

    "Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md": r'''

---

# Verification-pass hardening: approved navigation and staged validation

This section supersedes the earlier "Human-approved navigation decision"
retry-hardening language. The current GDD has made the decision:

- enemy navigation uses Unity AI Navigation (`com.unity.ai.navigation`);
- Isometric Tilemap authoring uses Unity 2D Tilemap Editor
  (`com.unity.2d.tilemap`).

If an approved package is missing, treat package/configuration as a concrete
prerequisite. Do not classify the navigation foundation as
`human_integration_required` merely because the technology is undecided; it is
no longer undecided. Human inspection before merge is a validation/integration
constraint, not automatically the execution scope of the whole task.

For death/restart, allow a bounded first-stage `single_agent` item when it can
reset all persistent run state that currently exists and is explicitly designed
to absorb later persistent systems without redesign. Flag the item only if its
acceptance criteria falsely claim full five-room validation that cannot yet run,
or if it omits already-existing persistent-state owners it must reset.

For required build/package configuration, a small bounded configuration task
may be `single_agent` even though the developer must inspect ProjectSettings or
package changes before merge. Reserve `human_integration_required` for cases
where the next meaningful step itself cannot be performed without human Unity
judgment.
''',

    "Pipeline/Reconciliation/prompts/verification/refiner.md": r'''

---

# Verification-pass hardening: canonical repairs after current GDD clarification

This section supersedes older retry-hardening instructions where they conflict
with the current GDD.

## Approved package/navigation repair

The current GDD explicitly approves:

- `com.unity.2d.tilemap` for Isometric Tilemap authoring;
- `com.unity.ai.navigation` for NavMesh-based enemy navigation.

Do not preserve navigation technology as an unresolved human-design question
and do not silently choose a different package. If the approved package is
missing from `Packages/manifest.json`, preserve/add concrete configuration work
and make dependent foundations consume it as appropriate.

## Windows delivery/configuration repair

Keep the Windows build itself represented as a `delivery_requirement`, but if
committed Build Settings show zero registered gameplay scenes, treat scene/build
configuration as confirmed missing implementation/configuration work rather
than collapsing the whole obligation into `not_assessable`. The developer's
current local active build target may remain unknown separately.

## Dependency closure from prose and hand-back contracts

Promote real prerequisites out of notes and into `depends_on` when the target
must exist first. In particular, preserve the GDD's now-explicit dependency
semantics for:

- status-effect/displacement consuming pursuit/search state hand-back;
- five-room content consuming the reusable visual-world foundation;
- encounter placement/content consuming authored room spaces and encounter
  admission/cap behavior;
- locomotion-dependent enemy work consuming the shared navigation foundation.

Do not manufacture dependencies for mere file collisions; those remain
exclusive-resource locks.

## Restart repair

The GDD requires full run-persistent reset. If five-room content is not yet
implemented, refine restart acceptance so the first task resets all currently
existing run-carrying state and remains extensible to later persistent systems
without redesign. Add dependencies on concrete persistent-state owners when
needed to implement their reset contract, and preserve later full-floor
validation as a validation requirement rather than making the first task
untruthfully claim it can validate absent content.

## Exclusive-resource normalization

Before returning the refined candidate, inventory all writers of each shared
resource and normalize locks across all tasks that can be concurrently ready.
Do not stop after correcting only the pair named in a finding.

Special checks:

- one canonical `logical:enemy-locomotion-runtime` lock across pursuit/search,
  status/displacement, melee, ranged, and locked-door attack when they share the
  future locomotion/behavior surface;
- shared prototype scene and scene-builder locks for tasks that wire new
  scene-resident components;
- Input System actions lock if movement/interaction work edits
  `Assets/InputSystem_Actions.inputactions`;
- asmdef/package-manifest/build-settings locks for package/configuration work
  when supported.

## Evidence repair

Do not preserve overbroad negative evidence after discovering a relevant asset.
If `.inputactions` mouse bindings exist but gameplay does not consume them,
state exactly that distinction.

For completed scene-integrated claims, preserve current serialized scene/prefab
or ProjectSettings evidence when available; do not substitute builder
capability alone.

## Clarified required representations

The current GDD explicitly requires:

- continuous player-facing health feedback: map it to the Player Health owner as
  an acceptance criterion/responsibility unless a separate UI task is clearly
  justified;
- wizard/enemy world-space SpriteRenderer presentation and isometric sorting:
  map it to the reusable visual-world foundation as acceptance/validation
  requirements.

These statements should not remain `ambiguous` after refinement.
''',
}


def append_once(path: Path, block: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Expected prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")
    marker = block.strip().splitlines()[2] if len(block.strip().splitlines()) > 2 else block.strip().splitlines()[0]
    # Use the first heading after --- as the durable idempotency marker.
    heading = next((line for line in block.splitlines() if line.startswith('# ')), None)
    if heading and heading in text:
        print(f"already patched: {path}")
        return
    path.write_text(text.rstrip() + block + "\n", encoding="utf-8")
    print(f"patched: {path}")


def main() -> int:
    for rel, block in PATCHES.items():
        append_once(ROOT / rel, block)
    print("\nPrompt hardening applied. No GDD files were copied or moved.")
    print("Run: docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
