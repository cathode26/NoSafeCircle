Encounter authoring feature (NSC-030):
- NSC-030 is a feature contract with decomposition_state needs_future_decomposition. The GDD fixes the composition rules:
  - three to eight enemies per encounter;
  - no Ranged Enemy without Melee support;
  - the Ranged Enemy first appears in Chapel of Ash;
  - mixed Melee and Ranged compositions in Chapel of Ash and the Final Room;
  - the fifteen-active-enemy registry ceiling.
  It leaves exact placements, triggers, per-door durability values and Final Room pressure to later authoring and playtesting.
- Do not invent exact enemy positions, per-room counts, trigger volumes or durability numbers. When the GDD or an approved decision fixes a value, cite it. Otherwise, either express the requirement as an authoring rule plus a validation that enforces it, or list the missing value as a decision for Vincent.
- Check what is actually delivered in Tasks/ and Assets/NoSafeCircle for:
  - the Active Enemy Registry and encounter admission;
  - the enemy prefabs;
  - door durability ownership.
  Also check whether the room contracts, NSC-044 to NSC-048, now define encounter or spawn regions this feature consumes.
- Gameplay-design candidates: the revised contract uses only behavior labeled within_current_GDD. A candidate labeled requires_design_approval or conflicts_with_current_GDD becomes an open question for Vincent, never contract text.
- Say whether the feature is ready for D1B.2 decomposition, which child responsibilities it would produce, and which of them need Vincent's placement decisions first.
