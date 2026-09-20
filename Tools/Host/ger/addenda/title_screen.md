Title screen presentation redesign (NSC-066 Title Screen and Start Game Flow):
- NSC-066's implementation is on local main, but TaskGraph derives not_delivered: no committed delivery record exists, and Vincent has not passed its visual gate (VAL-003). Code presence is not visual proof.
- The GER runbook records Vincent's request for "Space-Invaders-lobby-like moving background characters". Treat it as an original No Safe Circle presentation proposal with a visual gate at the canonical game resolution.
  - "Space Invaders" may refer to Vincent's own earlier SpaceInvaders project, which is not in this snapshot.
  - If the intended look is not documented in the repository, list the exact questions about it for Vincent rather than guessing.
  - Never copy another game's assets or layout.
- Inspect on main:
  - the current TitleScreenController;
  - the title-screen setup in DoorPrototypeSceneBuilder;
  - the existing title-screen tests;
  - the approved wizard art.

  Say which existing art can move on the title screen now, and which characters need art that no task has delivered.
- Keep the contract's guarantees:
  - gameplay input stays inactive before Start Game;
  - one Start Game activation makes exactly one wizard-selection request;
  - DoorPrototypeSceneBuilder.Build stays idempotent.
- The visual gate must name exactly what Vincent reviews in Play Mode and what a failing review looks like.
- Keep the scope to the title screen. The wizard-selection step belongs to NSC-067.
