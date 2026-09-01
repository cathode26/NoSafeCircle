# Software Architect Acceptance Gauntlet

**Status:** Prepared fixture and harness, corrected after an independent audit
returned `REQUEST_CHANGES`. No live proof has been run and no scheduler has been
accepted. Nothing here is committed.

**This is a test fixture, not No Safe Circle game-design canon and not
production task authority.** Nothing here is GDD evidence, a real gameplay
requirement, or completion evidence for any real task. Every task ID it uses is
in the reserved synthetic `NSC-9##` range.

---

## Why this exists

The retired private Orchestrator Gauntlet proved the decentralized Stage-1
through Stage-4 safety primitives: durable Issue authority, resume priority,
human holds, repository binding, a real two-worker claim race with at most one
winner, typed loser retry, no duplicate Issues, and no leaked claim refs. That
proof is complete and stays frozen.

The production architecture has since pivoted. The normal scheduler is now one
supervised polling **software architect** that observes deterministic Stage-2
authority, predicts merge and integration conflicts, WAITs when safe
parallelism cannot be positively established, and launches workers with exact
explicit task IDs. Git CAS claims remain, demoted to defense in depth.

Racing works. It is simply not the cheapest way to get *clean* parallelism. A
won race still produces two branches that must merge, and Unity scenes,
prefabs, and ScriptableObjects are not merge-safe. The expensive failure is not
"two workers claimed the same task"; it is "two workers each edited the same
scene."

This gauntlet is the acceptance environment for the system we actually intend
to use. It is built now so that once the polling architect branch is reviewed
and integrated, the live proof is a small afternoon, not another infrastructure
project.

---

## Design rule: this must be harder to fool than the system under test

An independent audit of the first version reproduced five ways to manufacture a
result that looked like proof. Each is now closed structurally rather than by
adding another check that a future edit could route around.

| Audit finding | What it allowed | What changed |
| --- | --- | --- |
| Caller-controlled adapter identity | A scripted stub that declared every capability and set a public adapter-kind string produced a real `PASS`. | There is no adapter-identity string anywhere. Acceptance lives in a verifier-owned entry point that takes no adapter argument. |
| Live verifier accepted fabricated evidence | A file containing only `{"event":"poll_started"}` exited 0; a launch for `NSC-999` exited 0. | Evidence is now a bound envelope with a closed event schema. A REQUIRED `UNPROVEN` is non-success. |
| Fixture path containment escaped | `require_disposable_directory("/")` succeeded and `SyntheticGame/../../outside.txt` was accepted. | Fixture roots are created, marked, and proven by token plus device/inode before deletion. Declared paths are validated before they are joined and re-checked after symlink resolution. |
| Manifest validation was not strict | Unknown fields were accepted throughout. | Every authority-bearing object has an exact allowed key set and a closed vocabulary. |
| Scenarios prearranged their answers | Resume priority was queue order; G2's disjointness rested on prose. | Resume authority is a separate durable fact; disjointness is recomputed from committed resource tokens. |

Three invariants follow from that table, and each has a test:

1. **A fake, scripted, or otherwise caller-supplied adapter can never produce
   `PASS`.** Not by declaring capabilities, not by returning the expected
   decision string, not by impersonating a class name.
2. **Free-form prose is never authority** for START, conflict disjointness,
   authorization, or acceptance.
3. **Missing evidence is `UNPROVEN` or a failure, never invented.** In
   particular, a launch with no observed worker ID fails; the harness does not
   supply one.

---

## Architecture

```text
scenarios.json              declared expectations; test data only
        |
        v
manifest.py                 closed-schema validation of every object,
                            vocabulary, and cross reference
        |
        v
synthetic_repository.py     deterministic Unity-shaped Git fixture,
                            contained writes only
        |
        v
scenario_world.py           builds one world; OBSERVES reservations with Git;
                            computes disjointness from committed data
        |
        +--> verify_acceptance.py  verify_fixtures()   LAYER 1  (runs today)
        |
        +--> scheduler_adapter.py  the one narrow seam
                 |
                 +--> ScriptedAdapter              harness -> HARNESS_PASS/FAIL
                 +--> RealPollingArchitectAdapter  not wired -> PENDING
                 |
                 +--> verify_acceptance.py  run_harness()      LAYER 2H
                 +--> verify_acceptance.py  run_acceptance()   LAYER 2A

verify_live_evidence.py     proves a future live run from a bound scheduler
                            evidence envelope
```

### The three entry points, and why they are separate

**`verify_fixtures()` — layer 1.** Does the built Git fixture actually contain
the integration risk the scenario claims? Reservation surfaces are re-observed
with ordinary `git diff`/`git ls-files` calls, disjointness verdicts are
recomputed from committed exclusive-resource tokens, and both are compared
against the declared facts. This is real evidence today and needs no scheduler.

**`run_harness()` — layer 2H.** Accepts a caller-supplied adapter and exercises
fixture construction, transitions, durable-state snapshots and every check. It
has no code path to `STATUS_PASS`.

**`run_acceptance()` — layer 2A.** Takes **no adapter argument**. It constructs
`RealPollingArchitectAdapter` internally and derives acceptance from the
scheduler's own structured events plus Git state. Today every scenario reports
`PENDING_CAPABILITY`, because the adapter fails closed.

### Result vocabulary

| Status | Meaning |
| --- | --- |
| `FIXTURE_PASS` | The fixture models its declared facts. Nothing is claimed about scheduling. |
| `FIXTURE_FAIL` | The scenario asserts a conflict its own Git fixture does not contain. Always a defect. |
| `HARNESS_PASS` | The harness plumbing ran end to end. **Agreement with the manifest here is tautological.** |
| `HARNESS_FAIL` | The verifier caught a wrong answer, a missing worker ID, or an unauthorized mutation. |
| `PENDING_CAPABILITY` | The capability the scenario needs does not exist yet. Never a pass. |
| `PASS` / `FAIL` | The only architect acceptance claims. Reachable only from `run_acceptance_scenario`, enforced by a static scan. |

---

## Files

| File | Role |
| --- | --- |
| `README.md` | This document: architecture, runbook, and boundaries. |
| `OLD_GAUNTLET_REUSE.md` | What was reused conceptually from the retired Gauntlet, and what was retired. |
| `LIVE_PROOF_CHECKLIST.md` | The future live proof, plus the deferred K/L/M decomposition specifications. |
| `scenarios.json` | Machine-readable scenario manifest. Test-expectation data only. |
| `acceptance_lib.py` | Vocabulary, safety refusals, path containment, fixture-root ownership, deterministic Git identity. |
| `manifest.py` | Closed-schema manifest loader/validator. CLI: `--list`. |
| `synthetic_repository.py` | Deterministic Unity-shaped Git fixture generator. |
| `scenario_world.py` | Builds one scenario world; observes reservations; computes disjointness and durable state. |
| `scheduler_adapter.py` | The adapter protocol, the scripted harness adapter, and the future real adapter. |
| `verify_acceptance.py` | Fixture, harness, and acceptance entry points. CLI: `--mode`, `--scenario`, `--json`. |
| `verify_live_evidence.py` | Strict evidence-envelope verifier for the future live proof. |
| `acceptance_smoke_test.py` | 56 harness tests, including the audit's adversarial regressions. |

---

## Active scenarios

Thirteen scenarios, A through J. There is no target count; this is the smallest
set that covers the first real local architect proof.

| Letter | ID | Proves |
| --- | --- | --- |
| A | `SAA-A-parallel-safe-assignments` | Two disjoint tasks both start on successive polls, each with a real observed worker ID. |
| B | `SAA-B-predicted-exact-path-conflict` | Two HUD tasks need `HUD.prefab`; one starts, one waits, a third unrelated candidate still starts. |
| C | `SAA-C-unity-asset-identity-conflict` | `EnemyTuning.asset` and `EnemyTuning.asset.meta` are one asset identity, so disjoint scripts still serialize. |
| D | `SAA-D-human-held-unmerged-reservation` | A `human_action_required` branch reserves `Game.unity` even with no live worker. |
| E | `SAA-E-actual-change-overrides-prediction` | Actual Git evidence beats a stale prediction. |
| F | `SAA-F-wait-becomes-start-after-integration` | A WAIT becomes a START once the conflicting branch is merged. Never a blacklist. |
| G1 | `SAA-G1-unknown-surface-blocks-unprovable-pair` | An unreadable surface is UNKNOWN, not empty, and waits. |
| G2 | `SAA-G2-unknown-surface-provably-disjoint` | Structurally provable disjointness lets a candidate start. No global deadlock. |
| H1 | `SAA-H1-architect-invocation-unavailable` | A failed advisory waits, launches nothing, escalates nothing, and is retried. |
| H2 | `SAA-H2-architect-output-malformed` | A plausible-looking but structurally invalid advisory waits and never escalates. |
| I1 | `SAA-I1-resume-outranks-tempting-fresh-work` | Durable resume authority beats a higher-confidence fresh candidate that heads the queue. |
| I2 | `SAA-I2-resume-waits-and-steals-nothing` | A conflicting resume waits and changes no durable state at all. |
| J | `SAA-J-scheduler-singleton` | Two schedulers contest one checkout-root lock; the loser mutates nothing. |

### Scenario notes

**C — Unity `.meta` companions.** `NSC-907` edits `EnemyTuning.asset`;
`NSC-908` edits `EnemyTuning.asset.meta`. The two paths are not equal, so a
path-string comparison calls them safe, and the two C# files are genuinely
disjoint, so a script-only comparison does too. `unity_asset_identity()`
collapses both onto one asset. The plain same-path collision is covered by B.

**G2 — disjointness is computed, not argued.** An advisory may list
`disjointness_claims`, but the manifest schema has no free-text justification
field. The verdict comes from `ScenarioWorld.compute_disjointness()`, which
reads committed exclusive-resource tokens and contract identities. Silence is
never disjointness: if either side declares no resource, the verdict is
`not_provably_disjoint`.
`test_g2_prose_alone_cannot_establish_disjointness` strips the committed tokens,
leaves the persuasive wording in place, and requires the fixture to fail.

**I1 — resume priority is not queue order.** The resume task does not appear in
`fresh_queue` at all. `world.candidate_queue()` returns fresh ranking only;
`world.resume_candidate()` is a separate durable fact. The fresh ranking is
headed by a genuinely launchable task with *higher* advisory confidence, and
the manifest refuses a resume scenario that does not offer one.

**J — a singleton needs two schedulers.** One `observe_cycle()` response cannot
prove an OS lock, so J declares an `operation`, not `steps`. The scripted
adapter deliberately does not implement `observe_singleton_contest`, so J
reports `PENDING_CAPABILITY` in harness mode rather than agreeing with itself.

---

## Running it

```bash
# Validate the manifest and list scenarios
python3 Gauntlet/SoftwareArchitectAcceptance/manifest.py --list

# Layer 1: prove every fixture models its declared facts
python3 Gauntlet/SoftwareArchitectAcceptance/verify_acceptance.py

# Layer 2H: drive the harness plumbing (HARNESS_* only)
python3 Gauntlet/SoftwareArchitectAcceptance/verify_acceptance.py --mode harness

# Layer 2A: the real scheduler (PENDING until the adapter is wired)
python3 Gauntlet/SoftwareArchitectAcceptance/verify_acceptance.py --mode acceptance

# Harness tests
python3 Gauntlet/SoftwareArchitectAcceptance/acceptance_smoke_test.py

# Byte-compile check
PYTHONPYCACHEPREFIX=/tmp/saa-pycache \
  python3 -m compileall -q Gauntlet/SoftwareArchitectAcceptance
```

Set `PYTHONDONTWRITEBYTECODE=1` for the ordinary runs. `compileall` writes
bytecode by design and ignores that variable, so redirect its output with
`PYTHONPYCACHEPREFIX`; otherwise it leaves a `__pycache__` directory in the
package, which is a repository artifact this harness is not allowed to create.

---

## Fixture safety

### Fixture roots are created, not accepted

There is deliberately no "destroy this path" primitive. The flow is:

```text
create_disposable_parent()   mkdtemp under the system temp directory
create_fixture_root(parent)  mkdir + write .saa-fixture-root marker
                             with an unpredictable token and device/inode
destroy_fixture_root(root)   prove identity, then remove
```

`destroy_fixture_root` refuses unless the target is a strict descendant of the
parent it recorded, that parent is itself inside the system temp directory, the
path is not a symlink, the marker is a regular file, and the token, recorded
path and device/inode all match. `/`, a drive root, the temp parent itself, a
parent directory, and a foreign temp directory carrying a forged marker are all
refused, each with a test.

### Declared paths are validated before they are joined

`validate_repository_relative_path` rejects absolute paths, Windows drive and
UNC forms, backslashes, `.`, `..`, empty components, colons, and control
characters, and requires the path to start with `SyntheticGame/`. Every write
then goes through `resolve_within`, which re-checks containment against the
fully symlink-resolved path, so a link planted inside the fixture cannot
redirect a write outward.

---

## Synthetic repository fixture

`synthetic_repository.py` creates a real local Git repository containing a
small Unity-shaped surface:

```text
SyntheticGame/Scripts/Core/GameManager.cs        central manager (shared system)
SyntheticGame/Scripts/Enemy/*.cs                 isolated behaviors
SyntheticGame/Scripts/UI/*.cs                    HUD behaviors
SyntheticGame/Scripts/Audio/AudioRouter.cs       isolated behavior
SyntheticGame/Prefabs/HUD.prefab   (+ .meta)     the canonical collision surface
SyntheticGame/Scenes/Game.unity    (+ .meta)     human-hold reservation surface
SyntheticGame/Scenes/Chapel.unity  (+ .meta)     proves scene conflict is per-asset
SyntheticGame/Data/EnemyTuning.asset  (+ .meta)  the asset-identity collision surface
SyntheticGame/Data/AudioCatalog.asset (+ .meta)
```

The files are **not valid Unity assets**. They are deterministic text whose
paths and suffixes carry the whole meaning.

### What determinism is actually claimed

**Claimed:** on one host with one Git version, building the fixture twice
produces identical HEAD, tree, branch SHAs, branch diffs, tracked file lists,
porcelain status, and working-tree observations, and an inherited Git
configuration cannot change any of them.

**Not claimed:** identical SHAs across Git versions or across platforms. That
has not been measured, so it is not asserted.

The environment is scrubbed rather than merely extended: every inherited `GIT_*`
variable is dropped, which covers the `GIT_CONFIG_COUNT` /
`GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n` command-scope form,
`GIT_CONFIG_PARAMETERS`, `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` and
`GIT_TEMPLATE_DIR`. On top of that the harness pins identity, per-commit
timestamps from a frozen epoch, `TZ=UTC`, `LC_ALL=C`, `GIT_CONFIG_NOSYSTEM`,
`core.autocrlf=false`, `core.eol=lf`, `core.filemode=false`, `core.symlinks=false`,
`commit.gpgsign=false`, `tag.gpgsign=false`, `gc.auto=0`, and an explicitly empty
hooks directory used both as `--template` and as `core.hooksPath`.

`test_inherited_git_configuration_cannot_change_a_fixture` sets a hostile
environment and requires a byte-identical signature.

### Construction versus observation

The manifest declares how to *construct* a reservation. `scenario_world.py`
then *observes* the result with ordinary Git commands. Actual changed paths are
therefore evidence, not a restated expectation.

An unreadable surface is recorded as `surface_unknown`, never as "no paths".
Reporting empty would be the single most dangerous silent failure in the
design, so the fixture generator raises rather than let a reservation claim an
observable-but-empty surface.

---

## Adapter boundary

The harness asks a scheduler exactly one question:

```python
class SchedulerAdapter(Protocol):
    def capabilities(self) -> frozenset[str]: ...
    def observe_cycle(self, world: ScenarioWorld) -> CycleObservation: ...
```

There is no `adapter_kind`, no self-description, and no way for an adapter to
say what its own answer means. `capabilities()` can make a scenario *skip*; it
can never make one *pass*.

The real adapter is a translation shim over injection points the polling
orchestrator already exposes:

```text
ScenarioWorld.source_root         -> source=
ScenarioWorld.checkout_root       -> checkout_root=
ScenarioWorld.candidate_queue()   -> plan_builder=        (fresh Stage-2 rank)
ScenarioWorld.resume_candidate()  -> resume_source=       (durable resume claim)
ScenarioWorld.task(...)           -> task_loader=
ScenarioWorld.reservation_dicts() -> reservation_observer=
ScenarioWorld.advisory(...)       -> architect_runner=    (injected advisory,
                                     no provider call, no network)
launch capture                    -> process_factory=     (records argv only)
scheduler events                  -> event_emitter=
```

Three rules for whoever writes that shim:

1. It must not reimplement any scheduling decision. If the shim ever contains a
   `wait` branch of its own, the acceptance result is measuring the shim.
2. `process_factory` records argv and never starts a process.
3. It must populate `CycleObservation.events` from the scheduler's own emitter.
   `_verify_real_evidence` re-derives every launch claim from those records.

There is deliberately **no reference policy adapter**. An earlier draft carried
one, and the audit was right that a second implementation of the WAIT rule is a
liability: it grades the scheduler against the harness author's opinion rather
than against the manifest. `ScriptedAdapter` replays declarative inputs instead.

---

## Live-proof evidence

`verify_live_evidence.py` consumes a **bound envelope**: a `run_metadata`
record followed by contiguous, closed-schema events.

```text
run_metadata   schema_version, run_id, scenario_id, manifest_sha256,
               repository, source_head, source_tree, scheduler_id,
               run_started_at
events         event, sequence, run_id, scenario_id, plus a closed field set
               per event type
```

Fails closed on: an unknown event type, an unknown or missing field, a task ID
that is not in the selected scenario, a manifest hash that does not match, a
mismatched run or scenario ID, a non-contiguous sequence, a
production-looking repository, or a wait that carries a prose reason instead of
structured conflicting identities and overlapping tokens.

Each scenario declares its `required_checks` from a closed vocabulary, so the
caller cannot choose a lenient subset at the command line. **Exit 0 means every
required check was `PROVEN`.** A required `UNPROVEN` is non-success.

A check is optional only because a scenario listed it in `optional_checks`;
optional status is never inferred from a check being absent from
`required_checks` or from whether it happened to pass. A check in neither list
is not applicable to that scenario and is not evaluated at all, so an
inapplicable result can never be misread as a finding.

`--source` inspects one local checkout. Local refs prove nothing about a frozen
remote or a private repository's authority, so those results are reported as
diagnostics and never gate the exit code.

Decomposition, graph-delta application, and the independent-authorization
boundary are **not** implemented here. A `decomposition_proposed` event is
rejected as an unknown event type. Their specifications are deferred to
`LIVE_PROOF_CHECKLIST.md` §7.

---

## Boundaries

- No network. Socket creation is blocked during the smoke tests, and a static
  scan asserts the package starts no subprocess other than `git`.
- No GitHub, no Issues, no claims, no provider invocation.
- No writes outside a fixture root this package created and marked.
- Production repository and checkout names are refused with no override flag,
  reused unchanged in spirit from the retired Gauntlet.
- Synthetic task IDs only, enforced by regex at every entry point. `NSC-999` is
  reserved as a never-declared ID so evidence naming it is provably fabricated.
