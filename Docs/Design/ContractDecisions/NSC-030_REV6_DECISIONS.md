# NSC-030 revision 6: GER Orchestrator decisions, 2026-09-17

Input: Codex contract check of revision 5, C:/nscrev/codex-jobs/codex-contract-check-NSC-030-rev5-20260917.report.md ("revise"). Decisions 13-20 in NSC-030_DECISIONS.md stay. Both findings are accepted with the ownership below.

## D21. Restart returns encounter enemies to their pre-admission state (blocking finding)

The GDD (restart section, lines 102-104 and 699) says each persistent enemy returns to its authored region in its initial AI state. Before its room trigger fires, that initial state is inactive and not admitted.
- **Owner.** The production encounter activation component owns restoring its configured enemies to that state.
- **Tracking.** The component records every configured enemy it has activated during the current floor run, including one later defeated. It exposes this as a read-only collection, for example ActivatedEnemies, that the restart orchestrator can read.
- **Reset method.** In addition to clearing its own fired and requested state (AC-009 today), the public reset method:
  - sets every configured enemy GameObject inactive, whether or not it was activated;
  - then clears its activated-enemy record.
  It never calls EnemyHealth, EnemyPursuitMovement, ActiveEnemyRegistry or EncounterAdmissionController methods itself.
- **Scope.** NSC-030 still does not edit EnemyPursuitMovement.cs or the Floor Run/Restart Orchestrator.

## D22. Only enemies activated this run get pursuit and health resets (major finding)

EnemyPursuitMovement.Awake captures spawnPosition only when the GameObject first activates. ResetPursuit on a never-activated enemy would move it to the default position (the origin).
- **INT-001** tells NSC-033 the orchestrator order for encounter enemies:
  1. For each enemy in the activation component's activated-enemy record, call EnemyHealth.ResetHealth and EnemyPursuitMovement.ResetPursuit (a defeated or already inactive activated enemy is still reset, because Awake ran).
  2. Call the encounter activation component's reset method: everything configured becomes inactive, and flags and record clear.
  3. Call ActiveEnemyRegistry.ResetRegistry.
  4. Call EncounterAdmissionController.ResetAdmissionState.
- **Never-activated enemies** (pending or cancelled batches) are never reset or moved and keep their authored transforms.

## D23. VAL-006 proves the mixed case

Extend VAL-006 in Play Mode using Assets/Scenes/DoorPrototype.unity, with production components and owner methods only.
- **Setup:** batch A is admitted and active (one of its enemies moved away from its spawn and one defeated); batch B is pending, so still inactive; batch C is cancelled, or never requested where the contract has no cancelled state.
- **Run the D22 order through the owner methods.** Assert:
  - every configured enemy is inactive;
  - batch A enemies are back at their authored initial positions inside their rooms' spawn/reset regions, at full health;
  - batch B and C enemies' transforms are unchanged from their authored values;
  - the registry holds no active enemies;
  - the activation component's record is empty.
- **Then fire the trigger again.** It makes exactly one new admission request, and only enemies admitted through that request become active and registered.
- **Scope.** Integrated zero-health proof stays in NSC-033 VAL-002.

## Stale dependent

NSC-049 lacks INT-006's fixed-squad reconciliation requirement. The GER Orchestrator handles it in a separate NSC-049 follow-up; this revision does not edit NSC-049.

# NSC-030 revision 7 (GER Orchestrator decisions, 2026-09-17)

Input: Codex contract check of revision 6, C:/nscrev/codex-jobs/codex-contract-check-NSC-030-rev6-20260917.report.md ("revise"). D21-D23 stand, except that D23's test setup is replaced by D24 and extended by D25.

## D24. VAL-006 uses two rooms (blocking finding)
One room makes exactly one RequestAdmission call (AC-005), and that call creates one AdmissionBatch, so one room cannot hold admitted, pending and cancelled batches at once. VAL-006 therefore uses two production encounter activation components in Assets/Scenes/DoorPrototype.unity, room X and room Y.
- Registry capacity comes only from production registration, so that room X's request is only partly admitted. Use enemies registered through EnemyHealth.Initialize with the scene registry, or the registry's existing public registration path; never private fields.
- **Room X:** its trigger fires. Part of its batch is admitted and active; one admitted enemy is moved away from its spawn and one is defeated through EnemyHealth.TakeDamage. The rest of the batch stays pending until X's exit door locks (DoorInteractable.Locked), which cancels it through the AC-006 cancellation API.
- **Room Y:** its trigger fires while capacity is full, so its whole batch is pending.
- **Restart:** run the D22 order across both components.
- **Verify:**
  - every configured enemy of X and Y is inactive;
  - X's admitted enemies are back at their authored initial positions, at full health;
  - X's cancelled enemies and Y's pending enemies keep their authored transforms;
  - the registry holds none of them;
  - both ActivatedEnemies records are empty.
- **Second run:** each trigger fires again and makes exactly one new RequestAdmission call, and only enemies admitted through those new requests become active and registered.

## D25. Later admissions are recorded (major finding)
- **ActivatedEnemies** is a component-owned record for the current floor run. It holds every configured enemy that has appeared in that component's own AdmissionBatch.AdmittedEnemies, whether admitted during the initial RequestAdmission or later by EncounterAdmissionController.ProcessPendingAdmissions.
  - Each enemy appears once.
  - An enemy stays in the record after defeat, or after leaving the batch's lists, until the component's reset clears the record.
  - The component may read its batch through the existing public AdmissionBatches/AdmittedEnemies members.
  - It never edits EncounterAdmissionController.cs; child 1B keeps sole ownership of that file for the cancellation API.
- **VAL-006 adds a later-admission case,** before the restart step:
  1. With room Y's batch pending and the registry at capacity, free capacity by defeating an admitted enemy through EnemyHealth.TakeDamage. AC-006's retry admits one of Y's pending enemies.
  2. Assert that enemy appears exactly once in Y's ActivatedEnemies.
  3. Defeat it too, and assert it is still in the record.
  4. The D22 restart then gives it ResetHealth and ResetPursuit like any activated enemy, returns it to its authored position, and leaves it inactive.
  5. Update the D24 expectations to match: Y then has one activated enemy and the rest still pending.

## Stale dependents (not edited in this revision)
- NSC-033: the ActivatedEnemies-restricted, ordered restart integration and its dependency.
- NSC-049: INT-006 fixed-squad reconciliation.
The GER Orchestrator handles both in separate follow-ups.

# NSC-030 revision 8 (GER Orchestrator decisions, 2026-09-17)

Input: Codex contract check of revision 7, C:/nscrev/codex-jobs/codex-contract-check-NSC-030-rev7-20260917.report.md ("revise": 2 blocking, 2 major). All four findings are accepted. D26 changes only the construction of VAL-006 and one AC-009 sentence; D21-D25 behavior stands.

## D26a. No cascading second admission
Drop the step that defeats room Y's newly admitted enemy.
- **Defeated enemies stay in the record.** Prove this with room X instead: the X enemy defeated to free capacity stays in X's ActivatedEnemies until reset.
- **Only one Y enemy is admitted.** That one defeat frees one slot, so exactly one Y pending enemy is admitted. The test asserts it appears once in Y's ActivatedEnemies.
- **No further defeats before restart.** After restart, Y has exactly one activated enemy. Its other configured enemies (AC-002 guarantees at least two more) are still pending.

## D26b. AC-009's prohibition names the right owner
Replace "this contract never edits EncounterAdmissionController.cs" with: "the encounter activation component and the child that implements it never edit EncounterAdmissionController.cs; child 1B remains the only child permitted to edit it (AC-006)."

## D26c. Registration wording
- EnemyHealth.Initialize only wires the registry reference.
- EncounterAdmissionController.RequestAdmission registers the enemies it admits in ActiveEnemyRegistry.
- Step 1 must say both, and must never imply that Initialize registers or raises ActiveCount.

## D26d. Filler enemies are test scaffolding, cleaned up before the second run
The capacity fillers belong to no room encounter.
- **Setup.** The test creates MeleeEnemy instances, wires each with EnemyHealth.Initialize(scene registry), and admits them with one test-made RequestAdmission call before room X's trigger fires. Use enough fillers that at least one, but fewer than all, of room X's configured enemies fit under the fifteen-enemy cap. This call is not a room trigger, so AC-005's one-request-per-room rule is unaffected.
- **Restart order:**
  1. Enemy-owned resets for X's and Y's ActivatedEnemies.
  2. Each activation component's reset method.
  3. The test destroys every filler GameObject and waits one frame.
  4. ActiveEnemyRegistry.ResetRegistry().
  5. EncounterAdmissionController.ResetAdmissionState().
- **The second run** starts with no filler enemies: both triggers fire again, each makes exactly one new RequestAdmission, and only enemies admitted through those requests become active and registered.

## D27. VAL-007 lists Force Wave's balance checks (NSC-009 revision 4 check, stale dependent)
NSC-030 VAL-007's play review explicitly judges seven Force Wave checks, which discharge NSC-009 INT-004:
1. escaping a melee surround;
2. clearing enemies from a door approach;
3. staying a weak answer to distant ranged pressure;
4. not stopping projectiles;
5. preserving distance-based pursuit and search after displacement;
6. about one meaningful use per encounter space;
7. the choice between spending it mid-room and saving it for the five-second door attempt.
