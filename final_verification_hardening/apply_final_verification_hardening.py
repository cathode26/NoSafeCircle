from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

PATCHES: dict[Path, tuple[str, str]] = {
    ROOT / 'Pipeline/Reconciliation/prompts/reconcile.md': (
        '## Final verification closure rules: restart, door passability, victory, and minimal context',
        r'''
## Final verification closure rules: restart, door passability, victory, and minimal context

The current GDD resolves four requirements that previously produced verifier ambiguity. Treat these as canonical requirements, not optional interpretations.

### 1. Floor-run restart has a durable closure owner

The GDD now defines a shared **Floor Run/Restart Orchestrator**. It owns coordination of a fresh floor attempt, while each run-persistent system owns a reset entry point for its own state.

Required reset participants, once represented by concrete runtime work, include:

- Player Health;
- Player Mana/cooldowns;
- player position/movement state;
- enemy health/defeat state;
- enemy pursuit/search state;
- Active Enemy Registry bookkeeping;
- door lifecycle/crossing/durability state;
- encounter activation/admission state.

An early restart implementation that resets only systems already present in the repository is a valid **stage**, but it MUST NOT become the graph's only terminal restart work. The graph must retain durable required work for full persistent-systems restart closure until every implemented persistent-state owner participates.

Acceptable representations include:

- a bootstrap/current-systems restart implementation plus a later concrete persistent-systems-closure implementation; or
- a decomposable orchestrator item whose concrete descendants include both the current bootstrap and final closure.

Whichever representation is used, the graph must make it impossible for restart to be declared fully complete while implemented persistent state exists that does not expose/participate in reset.

Add a symmetric acceptance responsibility to concrete persistent-state owners: each must expose a reset entry point consumed by the Floor Run/Restart Orchestrator. Do not make the early bootstrap depend on deferred room-content feature nodes merely to achieve this.

### 2. Door semantic state and navigation passability are separate owned halves of one contract

The GDD now defines a shared **door-passability contract**:

- Door and Interaction owns semantic state: `sealed`, `open`, `locked`, `broken`.
- The shared gameplay navigation/locomotion layer owns translating that state into enemy walkability.
- sealed/locked blocks enemy traversal;
- open/broken permits forward enemy traversal;
- enemy pursuit/attack behavior consumes the navigation result and does not independently manipulate NavMesh or doorway passability.

Represent the navigation-side passability interface as acceptance responsibility of the shared navigation/locomotion implementation (or a genuinely separate concrete shared implementation only if needed by the existing architecture). Door lifecycle work consumes/publishes semantic state through that interface.

Use `logical:gameplay-walkability-surface` as a shared exclusive resource on concrete navigation and door-lifecycle/durability work that can write/toggle that shared passability surface.

Do NOT solve integrated locked-door validation by making the entire pursuit/search foundation depend on a door feature. If the pursuit implementation can be built before lock state exists, stage the locked-door traversal check as a validation requirement that becomes executable when the door lifecycle exists.

### 3. Final victory presentation is specified

The final escape is not ambiguous. When shared doorway-crossing state confirms forward-side crossing of the final door:

- victory is triggered;
- normal gameplay input stops;
- a simple player-facing `You Escaped` overlay is displayed;
- no additional post-victory progression/menu/meta-progression is required.

Map this to the final-escape/victory implementation's acceptance criteria and validation. Do not preserve an unresolved question asking what victory feedback should be.

### 4. Minimal-context dispatch is a required pipeline constraint

The GDD explicitly requires that each agent receive only:

- the approved feature brief;
- its acceptance criteria;
- relevant GDD rules;
- files and scene/prefab information required for the active task.

Unrelated repository/project context is withheld unless the active task genuinely requires it.

This MUST appear as a typed `pipeline_constraint` in `non_code_requirements`. Do not leave it implicit in task scoping or omit it because it is not gameplay code.
'''
    ),
    ROOT / 'Pipeline/Reconciliation/prompts/verification/coverage_auditor.md': (
        '## Final coverage mapping: restart closure, victory feedback, passability, minimal context',
        r'''
## Final coverage mapping: restart closure, victory feedback, passability, minimal context

Apply these canonical representation semantics from the current GDD during requirement inventory.

1. **Victory feedback is no longer ambiguous.** The final escape requirement includes stopping normal gameplay input and showing a simple `You Escaped` overlay. Map that behavior to the final-escape/victory implementation as acceptance/validation responsibility. Do not classify post-victory flow as ambiguous merely because no larger menu/progression system is specified; the GDD explicitly says none is required.

2. **Minimal-context dispatch is required process scope.** The rule limiting an agent to the approved brief, acceptance criteria, relevant GDD rules, and task-required files/scene/prefab context must map to a typed `pipeline_constraint` in `non_code_requirements`. If that durable record is absent, report it as unrepresented.

3. **Full run restart needs durable implementation ownership.** A staged current-repository reset is not sufficient coverage for the GDD's full Floor Run/Restart Orchestrator contract. Coverage is complete only if the graph retains required work that closes reset participation across every concrete run-persistent system once those systems exist, and those owners expose reset entry points.

4. **Door-state-to-walkability is implementation responsibility, not vague integration.** Door and Interaction owns semantic door state; shared navigation/locomotion owns translation into enemy walkability. Verify both halves have durable representation. Integrated pursuit behavior may carry a later validation requirement without forcing pursuit to depend on door content prematurely.
'''
    ),
    ROOT / 'Pipeline/Reconciliation/prompts/verification/structure_auditor.md': (
        '## Final structure checks: restart closure and door passability ownership',
        r'''
## Final structure checks: restart closure and door passability ownership

Before returning findings, explicitly audit these two cross-system contracts from the current GDD.

### Floor Run/Restart Orchestrator

A graph is structurally incomplete if an early `death-restart`/restart-bootstrap item can close after resetting only today's prototype state while no later concrete work owns full persistent-systems closure.

Require durable closure across all concrete persistent owners: player resources/position, enemy health/defeat, enemy pursuit/search, Active Enemy Registry, door lifecycle/crossing/durability, and encounter activation/admission. Each persistent owner should expose a reset entry point consumed by the orchestrator. It is valid to stage early reset implementation separately so it is not blocked by unwritten room content.

Do not treat 'the interface is extensible' as equivalent to implementing the future reset closure.

### Door passability ownership

The shared navigation/locomotion foundation owns the navigation-side representation of door passability. Door lifecycle owns semantic state and drives that interface. Pursuit consumes it.

A graph is structurally incomplete if 'open/broken traversable, sealed/locked blocked' appears only as an acceptance criterion on pursuit or doors with no owner for translating state into navigation walkability.

Prefer a navigation-foundation acceptance responsibility plus door-side consumption rather than adding a broad pursuit -> door dependency. Use `logical:gameplay-walkability-surface` as a shared exclusive resource where concrete work can write/toggle the passability representation.
'''
    ),
    ROOT / 'Pipeline/Reconciliation/prompts/verification/refiner.md': (
        '## Final refiner closure rules: restart, passability, victory, minimal context',
        r'''
## Final refiner closure rules: restart, passability, victory, minimal context

When pass-1 findings touch the following requirements, refine according to the current GDD rather than preserving old ambiguity.

### Restart

Preserve an early/current-systems restart stage when useful, but also preserve/create durable required work for the Floor Run/Restart Orchestrator's full persistent-systems closure. Do not allow the refined graph to reach a state where the bootstrap restart can complete and no later item owns resetting concrete enemy, registry, pursuit/search, door, or encounter state. Persistent-state implementations should expose reset entry points consumed by the orchestrator.

### Door passability

Refine toward the explicit ownership contract:

- Door and Interaction = semantic sealed/open/locked/broken state.
- Shared navigation/locomotion = translation into enemy walkability.
- Pursuit/attacks = consumers, not NavMesh/passability owners.

Prefer adding the passability-interface responsibility to the shared navigation foundation and the consumption/update responsibility to door lifecycle work. Add `logical:gameplay-walkability-surface` to concrete writer/toggler resource locks as supported. Do not create a broad pursuit -> door dependency solely to validate locked-door blocking.

### Victory

Do not preserve an unresolved victory-presentation question. The GDD specifies: shared crossing state triggers victory, normal gameplay input stops, and a simple `You Escaped` overlay appears; no further post-victory progression/menu flow is required. Represent this on the final-escape/victory implementation.

### Minimal-context dispatch

Ensure `non_code_requirements` contains a typed `pipeline_constraint` requiring agents to receive only the approved brief, acceptance criteria, relevant GDD rules, and task-required files/scene/prefab context. This is a durable process requirement, not implicit prose.

After making these repairs, rerun the normal dependency-kind preflight and all existing structural invariants before returning the refined candidate.
'''
    ),
}


def main() -> int:
    changed = 0
    for path, (marker, block) in PATCHES.items():
        if not path.exists():
            raise FileNotFoundError(f'Expected prompt not found: {path}')
        text = path.read_text(encoding='utf-8-sig')
        if marker in text:
            print(f'Already hardened: {path}')
            continue
        path.write_text(text.rstrip() + '\n\n---\n\n' + block.strip() + '\n', encoding='utf-8')
        print(f'Patched: {path}')
        changed += 1

    print()
    print(f'Patched {changed} prompt file(s).')
    print('No validator/schema code and no Tasks/*.yaml files were changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
