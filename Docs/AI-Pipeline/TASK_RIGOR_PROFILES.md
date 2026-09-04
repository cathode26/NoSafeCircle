# Task Rigor Profiles

The Software Architect recommends how much implementation and verification rigor a task
needs. The recommendation is useful judgment, not permission to bypass repository safety.
Deterministic host policy resolves the recommendation against the committed task contract,
the effective predicted-plus-observed change surface, and repository-owned minimums. Actual
paths recovered from a resumable checkout may add obligations; they never remove predicted
ones. The effective rigor may be raised, but never lowered below those minimums.

These rules answer three separate questions:

1. Which agent crew creates and reviews the candidate?
2. Which automated evidence is required for the exact candidate commit?
3. Is human judgment required before integration?

An answer on one axis does not silently answer either of the others. In particular, a lean
crew never means “no tests,” and a passing test never substitutes for visual judgment when
the task changes behavior that must be seen, heard, or felt.

## Architect recommendation

The architect returns one existing capability tier:

| Tier | Use when | Crew profile | Validation profile |
| --- | --- | --- | --- |
| `fast` | Mechanical, exact, isolated work with an established pattern and low uncertainty | `lean` | `targeted` |
| `standard` | Ordinary local implementation needing semantic review | `standard` | `task_specific` |
| `deep` | Cross-system, architectural, decomposition-adjacent, serialized, or high-uncertainty work | `full` | `full_relevant` |

The architect may always choose a stronger tier than the deterministic minimum. Its prose
cannot name models, invent a new profile, remove a completion gate, or waive a human check.

## Deterministic minimums

The host derives a minimum tier from committed facts. The effective tier is the stronger of
the architect recommendation and this minimum.

### Full (`deep`) is mandatory

Use the full profile when any of these apply:

- The task is not concrete single-agent implementation work, including work still needing
  decomposition.
- The predicted surface includes a shared system.
- The task reserves a logical resource, or a `unity-scene:` resource resolves to serialized
  scene content. Non-file resource kinds are never discarded merely because they are not
  spelled `repo-file:`.
- The work changes orchestration, TaskGraph, CI, repository policy, build/deployment,
  packages, project settings, Docker configuration, or agent instructions.
- The work changes Unity serialized or project-wide assets such as `.unity`, `.prefab`,
  `.asset`, `.inputactions`, `.controller`, `.anim`, `.mat`, or `.asmdef` files.
- The work changes any `.meta` file other than a brand-new deterministic C# script
  companion (see below). An orphaned `.meta`, a `.meta` for a non-script asset, and an
  edit to an existing `.meta` all keep the full profile, because rewriting a sidecar
  changes a GUID other assets reference.
- An explicit task contract, canon rule, or committed validation policy requires the full
  profile.
- The architect reports high uncertainty or recommends `deep`.

The full profile uses the independent Contract Locality Auditor, Implementer, Test Author,
and Validator. It runs the exact task-specific gates plus the broadest relevant regression
suite named by committed policy. Human verification remains mandatory for visual, scene,
prefab, input, audio, animation, timing/feel, migration/data-loss, and other judgment-based
acceptance criteria.

### Standard is mandatory

Use at least the standard profile when any of these apply:

- The change surface is expressed only as a path pattern or is otherwise not exact.
- The task affects named symbols/components whose impact is not confined to exact files.
- The exact surface contains more than four paths.
- The surface contains file types outside the small lean allowlist.
- A test must be designed or changed rather than merely executed from committed policy.
- The architect recommends `standard`.

The standard profile keeps independent semantic review and runs every explicit task gate.
Human verification is required unless a narrower committed machine-evidence rule applies.
Its executable crew is Implementer, Test Author, and Validator. The deterministic
minimum rules out decomposition, shared-system, infrastructure, and Unity serialized-asset
work before the Contract Locality Auditor may be omitted. A Validator locality/design
finding still fails closed as `contract_review_required`.

### Fast is permitted

The fast profile is available only when all of these are true:

- The architect recommends `fast`.
- The task is concrete and `single_agent`.
- The complete expected surface is exact, isolated, no more than four paths, and limited to
  lean file types (`.cs`, `.md`, and deterministic `.meta` companions).
- Path aliases are compared case-insensitively before the width bound is applied. A casing
  variant cannot inflate or disguise the exact surface.
- Every `.meta` in the surface is a deterministic C# script import companion: the path is
  exactly `<script>.cs.meta`, it lives under `Assets/`, its exact `<script>.cs` is part of
  the same change, and it does not already exist in the committed source. This is the
  sidecar ExecutionCrew generates for one approved new C# file; it carries only a schema
  version and a generated GUID. Newness must be proven -- when the committed source cannot
  be probed, the sidecar is treated as substantive and the full profile applies.
- There is no shared-system, serialized-asset, project/repository infrastructure, migration,
  security, or design/canon uncertainty.
- Every explicit completion gate remains enforceable.

The lean crew may omit redundant model reviews only after the executable crew path records
the effective profile. Deterministic source identity, write boundaries, clean-tree checks,
patch identity, merge-main-before-test behavior, exact-commit validation, and post-merge
verification are never optional.

The executable lean crew is Implementer plus an independent Validator. It omits the
Contract Locality Auditor and Test Author only because fast eligibility requires an exact,
isolated task surface and an existing committed test path; declaring a new test path raises
the required rigor to standard before any provider runs. `targeted` still runs every exact
completion gate bound by committed task policy. It does not mean “no Unity tests.”

## Human verification policy

`required` is the default. `machine_evidence_permitted` is an explicit exception, not a
synthetic human PASS.

Machine evidence may replace human judgment only when all of these are true:

- The effective tier is `fast`.
- A committed policy binds exact tests to the exact task-contract hash and candidate commit.
- The acceptance criteria contain no visual, audio, input-feel, timing, scene-framing,
  migration, or other subjective judgment.
- The task surface satisfies the fast minimum above.
- The workflow records the transition as automated authoritative evidence, with the policy,
  test manifest, task contract, and commit identities. It must not forge a human actor or a
  `human_result=pass` event.

The private synthetic gauntlet is the intended first allowlisted use after the workflow has
an authoritative automated-evidence transition. Until that transition exists,
`human_verification_policy` remains `required`; synthetic provenance alone cannot waive it.
Its provenance must be exactly
`human_approved_synthetic_gauntlet` with gauntlet ID
`synthetic-architect-gauntlet-v1`, and its committed validation policy must bind the exact
EditMode test filter and task-contract hash. Descendants produced by decomposition need an
equally explicit inherited rule before receiving the exception.

## Gates that no profile may waive

Every profile must preserve:

- TaskGraph eligibility, dependency, reservation, and lease checks.
- Exact source HEAD and task-contract identity.
- Validated write boundaries and rejection of out-of-scope changes.
- Merge of current `main` into the task branch before authoritative testing, with conflicts
  resolved on the branch and the resulting commit revalidated.
- Every explicit completion gate in the task contract.
- Clean-tree and regenerated-artifact cleanup policy.
- Exact-commit evidence, guarded publication, and post-merge verification.
- Fail-closed behavior when policy, evidence, identity, or surface is missing or ambiguous.

## Audit record

Every architect-selected implementation launch records:

- architect-requested tier;
- deterministic minimum tier;
- effective tier;
- crew, validation, and human-verification profiles;
- deterministic reasons for every raised floor or exception; and
- whether the architect's provider preference was honored.

This makes a fast run explainable after the fact and lets the gauntlet compare elapsed time,
provider invocations, and token use without weakening the completion contract.
