Door breach feedback (NSC-052 Door Breach Feedback: Banging, Shaking, Cracks, and Durability Indicator), integrated but not yet approved:
- **Current state.** The NSC-052 code and rebuilt scene are on main (commit 33e37e512, per the graph-lead journal), and focused Edit Mode and Play Mode tests passed there. There is no delivery record, and Vincent's visible and audible breach-feedback check is still open. Treat the integrated implementation as current state, not as proof of quality.
- **Ground the mechanic in the GDD.** Use the GDD door and pursuit rules and the locked-door enemy attack rules, and cite the chunk or line for each number used, such as durability, hit timing or crack thresholds. A value the GDD does not fix is a tuning hypothesis with a stated range, not a requirement.
- **Check what already exists.** Inspect the delivered door, breach feedback, audio wiring, scene setup and tests in Assets/NoSafeCircle, citing file:line. Name the existing owner class and public method each requirement uses. Distinguish "already implemented" from "required".
- **Judge it as the wizard player, at gameplay-camera scale.** Answer three questions without the player needing to look away from the fight:
  - Can the player tell which door is under attack?
  - Can they tell how close that door is to breaking?
  - Can they tell when it breaks?
  Name concrete Unity feedback (SpriteRenderer, Animator, particles, AudioSource, UI) only where the repository or an approved task provides it.
- **Tests.** A Play Mode test drives the real door through its production damage entry point and asserts an observable outcome. A test that sets internal fields directly proves only that isolated behavior. Vincent's visual and audio review remains a human gate.
- **Gameplay-design candidates.** The revised contract uses only behavior labeled within_current_GDD. A candidate labeled requires_design_approval or conflicts_with_current_GDD becomes an open question for Vincent, never contract text.
- **No-change outcome.** This overrides the instruction to increment contract_revision.
  - If the current contract is already right, and only fresh validation and Vincent's review remain, the author writes NO CONTRACT CHANGE in the proposed-contract section.
  - The author then reproduces the current contract unchanged, with the same contract_revision.
  - The re-auditor may then give the final recommendation release_without_change, naming the gates to revalidate.
