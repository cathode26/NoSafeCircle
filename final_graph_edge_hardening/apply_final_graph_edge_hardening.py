from pathlib import Path

ROOT = Path.cwd()

RECONCILE = ROOT / "Pipeline/Reconciliation/prompts/reconcile.md"
REFINER = ROOT / "Pipeline/Reconciliation/prompts/verification/refiner.md"

RECONCILE_MARKER = "## Final graph-edge and shared-capability closure preflight"
REFINER_MARKER = "## Final graph-edge and shared-capability repair rules"

RECONCILE_BLOCK = r"""

---

## Final graph-edge and shared-capability closure preflight

Apply this preflight after all earlier canonical-coverage and semantic-closure
checks, immediately before returning the final reconciliation candidate.

### Shared file/resource is not a dependency

Do not add or preserve a dependency merely because two work items modify,
integrate with, or are serialized through the same source file, scene, prefab,
or logical runtime surface. That relationship belongs in
`exclusive_resources`.

Current door check:

- `door-close-lock-break-lifecycle` MUST NOT depend on
  `door-open-interaction` merely because both affect `DoorInteractable` or the
  same door scene/prefab.
- Preserve a formal dependency only when the lifecycle work genuinely consumes
  a still-unfinished capability owned by the opening item.
- Shared write/integration collision remains represented through identical
  exclusive-resource locks.

Do not remove the door lifecycle's real dependencies on Player Health,
navigation/passability, or other concrete prerequisites that it actually
consumes.

### Shared doorway-crossing state must be independently representable

The GDD assigns shared doorway-crossing state to Door and Interaction, and both
door close/lock progression and final victory consume it.

Do not bury that shared capability solely inside a broad
close/lock/durability/breach implementation when doing so makes unrelated
consumers depend on the entire lifecycle bundle.

Preserve or create a concrete implementation work item such as
`doorway-crossing-state` when the candidate needs an independently executable
owner for:

- authoritative detection/state that the player has crossed the active
  doorway;
- a stable owner-side interface/event/state consumed by close/lock and victory;
- reset participation for that crossing state as part of full floor restart.

Then:

- `door-close-lock-break-lifecycle` depends on `doorway-crossing-state`;
- `final-escape-victory` depends on `doorway-crossing-state`;
- locked-door enemy attack/durability work continues to depend on the actual
  door lifecycle/durability owner, not on crossing state unless it genuinely
  consumes crossing state.

Do not create duplicate crossing detectors in lock logic and victory logic.

### Victory must wait for the concrete input consumers it disables

`final-escape-victory` promises to stop normal gameplay input before showing the
simple `You Escaped` overlay.

A task cannot truthfully implement or validate disabling a concrete gameplay
input consumer that does not yet exist.

For the current canonical gameplay set, preserve formal dependencies from
`final-escape-victory` to the concrete executable owners whose input it must
disable:

- `player-movement`;
- `door-open-interaction`;
- `fireball`;
- `frost-field`;
- `force-wave`;
- the shared `doorway-crossing-state` owner described above.

If a future graph introduces a different shared input-gating owner that
canonically centralizes these consumers, use that concrete owner instead of
duplicating unnecessary edges. Do not invent such an owner merely to simplify
this bootstrap graph.

### Charged Fireball consumes a Player Movement-owned restriction interface

Charged Fireball restricts player movement while charging. Player Movement owns
movement state and locomotion; Fireball must not directly mutate movement
internals.

Inspect the current Player Movement implementation.

If no supported external movement-restriction/modifier interface exists yet:

- `player-movement` acceptance criteria must require an owner-controlled
  interface that allows another gameplay system to request and later release
  the charged-Fireball movement restriction without taking ownership of
  locomotion;
- `fireball` must formally depend on `player-movement`, because the specific
  interface Fireball needs is unfinished;
- Fireball acceptance criteria must say it consumes that interface while
  charging and releases the restriction when charging ends/cancels/fires as
  required by its own behavior.

If the exact required restriction interface later exists and the remaining
Player Movement work is unrelated, re-evaluate the dependency under the normal
existing-interface rule rather than preserving stale ordering forever.

### Final assertion

Before returning JSON, explicitly verify:

```text
door lifecycle is not ordered behind door opening merely for shared writes
AND shared doorway-crossing state has one executable owner
AND lock progression and victory consume that same crossing owner
AND victory cannot complete before every concrete gameplay-input consumer it disables
AND charged Fireball cannot execute before the Player Movement-owned restriction interface it needs exists
AND all shared write collisions remain represented through exclusive_resources rather than fake dependencies
```

Repair the candidate and re-run dependency-kind/cycle validation after any
change made by this preflight.
"""

REFINER_BLOCK = r"""

---

## Final graph-edge and shared-capability repair rules

When pass-1 findings concern the remaining door/victory/movement relationships,
repair toward these canonical graph semantics.

### Door lifecycle versus door opening

Do not preserve `door-close-lock-break-lifecycle -> door-open-interaction` when
the only reason is that both edit/integrate with the same DoorInteractable,
scene, prefab, or logical door runtime. Use matching `exclusive_resources`
instead.

Keep a formal edge only for a genuinely unfinished capability that the
lifecycle implementation must consume.

### Extract shared doorway-crossing state when needed

Door and Interaction owns one shared doorway-crossing state. Lock progression
and final victory consume it.

If crossing state is hidden inside the broad close/lock/durability item,
extract/preserve an implementation owner such as `doorway-crossing-state` so
consumers do not depend on unrelated durability/breach work.

Preserve these relationships:

- close/lock lifecycle -> shared doorway-crossing owner;
- final victory -> shared doorway-crossing owner;
- no duplicate crossing detector in either consumer;
- crossing-state reset participates in full floor restart.

### Victory dependency closure

The final-victory implementation disables normal gameplay input, so it must not
complete before the concrete input consumers it disables exist.

For the current candidate, require `final-escape-victory` to depend on the
represented executable owners for:

- player movement;
- door interaction/opening;
- Fireball;
- Frost Field;
- Force Wave;
- shared doorway-crossing state.

Do not replace these with a speculative new central input system unless the
current GDD/repository already establishes one.

### Charged Fireball movement restriction ownership

Player Movement owns locomotion. Fireball requests a movement restriction; it
does not mutate Player Movement internals.

If the current repository lacks the required external restriction/modifier
interface:

1. add/preserve acceptance on `player-movement` for the owner-controlled
   request/release interface;
2. add/preserve `fireball -> player-movement`;
3. state in Fireball acceptance that charging consumes that interface and
   releases it when the charge ends.

This is a real dependency while that specific interface is unfinished, even if
other Player Movement behavior already exists.

### Re-run structural closure

After these repairs, re-run:

- dependency target existence/kind checks;
- dependency cycle checks;
- shared-resource lock consistency;
- execution-scope consistency.

Do not change the GDD, invent mechanics, or add ordering edges for mere source
collisions.
"""

def append_once(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"already present: {path}")
        return
    path.write_text(text.rstrip() + "\n" + block.strip("\n") + "\n", encoding="utf-8")
    print(f"updated: {path}")

if not RECONCILE.exists():
    raise RuntimeError(f"Missing expected file: {RECONCILE}")
if not REFINER.exists():
    raise RuntimeError(f"Missing expected file: {REFINER}")

append_once(RECONCILE, RECONCILE_MARKER, RECONCILE_BLOCK)
append_once(REFINER, REFINER_MARKER, REFINER_BLOCK)

print("Done. No GDD files were read, copied, moved, or modified by this script.")
