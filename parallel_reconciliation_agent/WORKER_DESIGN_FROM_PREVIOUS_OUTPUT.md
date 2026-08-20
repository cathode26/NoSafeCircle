# Worker Design Derived From the Previous Reconciliation

Source analyzed:

- reconciliation run `20260820T203258Z-3b04bcc8`
- refined by verification run `20260820T205841Z-71029338`
- 37 total work items

The previous graph already exposed the correct natural ownership boundaries.
Rather than guessing worker sizes from GDD page counts, v2 routes the exact
previous graph responsibilities into nine non-overlapping domains.

| Worker | Previous graph responsibilities |
|---|---|
| Player Core | `player`, `player-movement`, `player-health`, `player-mana` |
| Wizard Combat | `combat`, `fireball`, `frost-field`, `force-wave` |
| Enemy State | `enemies`, `active-enemy-registry`, `enemy-health-damage-defeat`, `enemy-status-effect-displacement` |
| Enemy Behavior | `enemy-pursuit-search-foundation`, `melee-enemy`, `ranged-enemy`, `locked-door-enemy-attack` |
| Doors | `doors`, `door-open-interaction`, `doorway-crossing-state`, `door-close-lock-break-lifecycle` |
| World Foundations | `world`, `fixed-isometric-camera`, `tilemap-navigation-package-configuration`, `gameplay-navigation-locomotion`, `world-visual-foundation` |
| Content + Encounters | `five-room-content-authoring`, `encounters`, `encounter-admission-cap-enforcement`, `dungeon-encounter-content-authoring` |
| Run Lifecycle | `floor-run-restart`, `floor-run-restart-bootstrap`, `floor-run-restart-persistent-closure`, `win-loss-conditions`, `final-escape-victory` |
| Global Pipeline | `no-safe-circle`, `delivery-and-build`, `windows-build-scene-registration`, plus non-code/deferred/global validation |

## Why Enemy was split

The previous graph had seven executable enemy responsibilities. It naturally
separated into:

- shared state/persistence/effects; and
- pursuit/archetype/attack behavior.

This also matches the cross-system interfaces that verification repeatedly
audited.

## Why Run Lifecycle is its own worker

The previous verification's largest cluster of real errors involved restart
closure crossing Player Movement, Player Health, spells, enemy state, registry,
doors, and encounter state.

Restart therefore should not be hidden inside a generic "global" worker. It gets
a dedicated worker that reads the whole GDD specifically to assemble the
cross-domain lifecycle contract.

## Why there is no LLM closure pass in v2

The previous graph gives us stable ownership/key routing. Workers may keep those
keys when current truth still supports the same responsibility.

That lets Python deterministically union the domains and use the existing
semantic validator. A global worker can attach GDD-backed validation overlays
without recreating another owner's node.

This removes the second large synthesis call from the earlier five-worker draft.

## Important safety rule

The previous reconciliation is used only to ROUTE work.

It is not evidence.

Every worker is explicitly told to re-derive current truth from the current GDD
and current repository, to omit stale routed concepts, and to add newly required
same-domain work when needed.
