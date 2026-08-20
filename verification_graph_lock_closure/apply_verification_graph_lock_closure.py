from pathlib import Path

ROOT = Path.cwd()

STRUCTURE = ROOT / "Pipeline/Reconciliation/prompts/verification/structure_auditor.md"
REFINER = ROOT / "Pipeline/Reconciliation/prompts/verification/refiner.md"

STRUCTURE_MARKER = "## Final false-positive closure: deferred feature prerequisites and evidence-based writer locks"
REFINER_MARKER = "## Final refinement closure: deferred feature prerequisites and evidence-based writer locks"

def read_required(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Missing expected file: {path}")
    return path.read_text(encoding="utf-8")

def replace_once(text: str, old: str, new: str, path: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one occurrence in {path}, found {count}:\n{old}"
        )
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------
# Dependency / Decomposition Auditor
# ---------------------------------------------------------------------
structure = read_required(STRUCTURE)

if STRUCTURE_MARKER not in structure:
    old_expected = """Current expected relationships include, when represented as separate nodes:

- five-room content -> Tilemap/SpriteRenderer visual foundation;
- encounter content/placement -> five-room content and encounter admission/cap
  foundation;
- status-effect/displacement -> pursuit/search state contract;
- locomotion-dependent enemy work -> shared navigation/locomotion foundation.
"""

    new_expected = """Current expected relationships include, when represented as separate nodes:

- five-room content -> Tilemap/SpriteRenderer visual foundation, because the
  target is a concrete implementation;
- encounter content/placement -> encounter admission/cap foundation when that
  target is a concrete implementation;
- the conceptual authored-room -> encounter-content prerequisite remains
  decomposition/authoring context while the authored-room node itself is
  `kind: feature`; do NOT require or recommend a feature-target dependency;
- status-effect/displacement -> pursuit/search state contract;
- locomotion-dependent enemy work -> shared navigation/locomotion foundation.

If Progressive Decomposition later creates a concrete authored-room
implementation/artifact, a concrete encounter-placement descendant may depend
on that concrete target. Until then, absence of a direct
`dungeon-encounter-content-authoring -> five-room-content-authoring` edge is not
a structural error.
"""
    structure = replace_once(structure, old_expected, new_expected, STRUCTURE)

    structure_block = r"""

---

## Final false-positive closure: deferred feature prerequisites and evidence-based writer locks

This section supersedes any earlier wording that could be read as requiring a
dependency whose target is a `feature`.

### Deferred feature prerequisite representation

A GDD prerequisite relationship does not automatically authorize a current
`depends_on` edge.

Before reporting a missing dependency:

1. resolve the proposed dependency target to an actual candidate work item;
2. inspect its `kind`;
3. if the target is `feature`, do **not** recommend the edge;
4. preserve the relationship as decomposition/authoring context until a
   concrete `implementation` or `artifact` descendant exists;
5. only then may the concrete downstream implementation/artifact depend on the
   concrete prerequisite.

For the current bootstrap graph:

```text
five-room-content-authoring
    kind: feature

dungeon-encounter-content-authoring
    kind: feature
```

Therefore this is invalid and MUST NOT be requested as a repair:

```text
dungeon-encounter-content-authoring
    -> five-room-content-authoring
```

This does not erase the GDD's authored-room-before-encounter relationship. It
defers the executable edge until concrete authored-room and encounter-placement
descendants exist.

A feature may still depend on a concrete implementation/artifact prerequisite,
for example a visual-world foundation or encounter-admission/cap implementation.

### Writer-lock findings require positive write evidence

Do not infer an `exclusive_resources` lock merely because a runtime system will
eventually exist in the same Unity scene or because another task already locks
that scene/builder.

Before reporting a missing file/scene/builder lock, establish positive evidence
that the audited work item is expected to **modify, regenerate, configure, or
integrate through** that exact resource during its own implementation.

Distinguish:

```text
reads/consumes a runtime capability
    != writes the scene/builder

eventually appears in the scene
    != this task edits the scene/builder

shares a subsystem
    != shares a non-merge-safe writer resource
```

Do not propagate scene/builder locks from `world-visual-foundation` to
`active-enemy-registry`, `enemy-health-damage-defeat`,
`enemy-pursuit-search-foundation`, `enemy-status-effect-displacement`,
`encounter-admission-cap-enforcement`, or similar code/foundation work solely
because those systems may later be scene-resident.

### High-confidence navigation/world integration check

The shared gameplay navigation/locomotion foundation is different: when current
repository/candidate evidence shows that implementing its NavMesh/navigation
surface requires modifying the same prototype scene and scene builder used by
the visual-world foundation, verify that both writer tasks carry identical
locks for the actual shared resources, including when applicable:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
```

Do not add those locks if the navigation task can be completed without writing
those resources. The lock decision must follow repository/write-surface
evidence, not task category.

### Final assertion

Before returning a material dependency/resource finding, verify:

```text
proposed dependency target is implementation/artifact
AND
every proposed exclusive-resource lock has positive write/integration evidence
```

If either assertion fails, do not report that repair as required.
"""
    structure = structure.rstrip() + "\n" + structure_block.strip("\n") + "\n"
    STRUCTURE.write_text(structure, encoding="utf-8")
    print(f"updated: {STRUCTURE}")
else:
    print(f"already patched: {STRUCTURE}")

# ---------------------------------------------------------------------
# Refiner
# ---------------------------------------------------------------------
refiner = read_required(REFINER)

if REFINER_MARKER not in refiner:
    old_dependency_block = """- status-effect/displacement consuming pursuit/search state hand-back;
- five-room content consuming the reusable visual-world foundation;
- encounter placement/content consuming authored room spaces and encounter
  admission/cap behavior;
- locomotion-dependent enemy work consuming the shared navigation foundation.
"""

    new_dependency_block = """- status-effect/displacement consuming pursuit/search state hand-back;
- five-room content consuming the reusable visual-world foundation;
- encounter placement/content consuming concrete encounter-admission/cap
  implementation and, only after decomposition creates one, a concrete
  authored-room implementation/artifact;
- the conceptual authored-room -> encounter-content relationship remains
  decomposition/authoring context while the authored-room target is still a
  `feature`; never repair it with a feature-target dependency;
- locomotion-dependent enemy work consuming the shared navigation foundation.
"""
    refiner = replace_once(refiner, old_dependency_block, new_dependency_block, REFINER)

    refiner_block = r"""

---

## Final refinement closure: deferred feature prerequisites and evidence-based writer locks

Apply this after all earlier repair rules. This section supersedes any earlier
instruction that could be read as authorizing a feature-target dependency or a
blanket scene/builder lock.

### Reject feature-target repairs before mutating the candidate

For every proposed dependency repair:

1. resolve the target work item;
2. require target `kind` to be `implementation` or `artifact`;
3. if the target is `feature`, reject the edge even when the GDD describes a
   conceptual prerequisite;
4. preserve that prerequisite in decomposition/authoring context until concrete
   descendants exist.

Specifically, do not add:

```text
dungeon-encounter-content-authoring
    -> five-room-content-authoring
```

while `five-room-content-authoring` is a feature.

If later decomposition produces concrete authored-room and encounter-placement
work, place the executable edge between those concrete descendants.

### Repair writer locks only from actual write surfaces

Do not normalize a scene/builder lock across every task in a subsystem.

A task receives an exclusive resource only when repository/candidate evidence
supports that the task itself will modify, regenerate, configure, or integrate
through the exact resource.

Do not add prototype-scene/builder locks to code/foundation work merely because
the resulting component will eventually be present in the scene.

In particular, do not automatically add those locks to:

- `active-enemy-registry`;
- `enemy-health-damage-defeat`;
- `enemy-pursuit-search-foundation`;
- `enemy-status-effect-displacement`;
- `encounter-admission-cap-enforcement`;

unless current evidence identifies the exact shared scene/builder as part of
that task's own write surface.

### Navigation/world scene-builder collision

When current evidence shows that `gameplay-navigation-locomotion` must configure
the NavMesh/navigation surface through the same prototype scene and scene
builder that `world-visual-foundation` modifies, normalize the matching
exclusive-resource locks across those two writer tasks.

Use the exact resource identities already established by repository evidence,
including when applicable:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
```

This is a concurrency repair, not a dependency edge.

If evidence instead shows navigation can be implemented without modifying those
resources, do not invent the locks.

### Remove overbroad read-only locks

If a work item only consumes/reads a shared runtime surface and does not write
it, remove an exclusive-resource lock that was added only by association.

Examples include a locked-door attack that merely consumes walkability and code
owners that consume locomotion/registry interfaces without modifying their
implementation surfaces.

### Re-run closure

After these repairs, verify:

- no dependency target is a feature;
- no dependency cycle was introduced;
- every exclusive resource corresponds to a supported write/integration
  surface;
- known shared writers use identical keys;
- read-only consumers are not unnecessarily serialized.
"""
    refiner = refiner.rstrip() + "\n" + refiner_block.strip("\n") + "\n"
    REFINER.write_text(refiner, encoding="utf-8")
    print(f"updated: {REFINER}")
else:
    print(f"already patched: {REFINER}")

print("Done.")
print("Patched verification prompts only.")
print("reconcile.md was not modified.")
print("No GDD file was read, copied, moved, installed, replaced, or modified.")
print("Tasks/*.yaml was not modified.")
