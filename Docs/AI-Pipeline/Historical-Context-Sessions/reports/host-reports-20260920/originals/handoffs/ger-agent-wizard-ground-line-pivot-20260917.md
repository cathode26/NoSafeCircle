# Handoff: wizard pivot should sit on the feet, not the canvas bottom (NSC-075, NSC-095, NSC-096)

From: Art Director Agent. To: GER Agent. Board row H-20260917-24. 2026-09-17.

Not urgent during the pause. It matters before NSC-095 and NSC-096 are committed and before any NSC-075 crew runs.

## Finding

- **The pivot sits at the canvas bottom.** `ImportWizardSprite` on main sets a custom pivot of (0.5, 0) (`DoorPrototypeGlobalSceneBuilder.cs` lines 594-595). `WIZARD_128_DECISIONS.md` line 91 keeps (0.5, 0) for the 128 px switch.
- **The approved 180 px wizards don't stand on the canvas bottom.** Measured on main for all 4 variants × 8 facings:
  - standing feet end 14-27 px above the bottom edge;
  - masculine-light 20-25, masculine-dark 22-27, feminine-light 20-24, feminine-dark 14-18.
  - Data: `C:\nscrev\reports\art-director\wizard-ground-line-20260917\wizard180_feet_rows.json`.
- **The 128 px trial frames have the same gap:** 10-19 px (`density-trial-20260916\pixellab\3b_rotations_final`, `3c_walk_se_128`).

## Effect in NSC-075's camera-facing 2x2 box

- **The feet float above the floor contact.** A gap of g px at 90 PPU draws the feet g/90 world units above the floor-contact point along camera-up. At 1080p that is 10-20 screen px, so the wizard reads 0.3-0.6 world units deeper on the floor than where it stands. The effect is the same at 128/64 PPU.
- **The height changes between facings and variants.** Within one variant the gap varies by up to 5 px between facings; between variants it ranges from 14 to 27 px. Turning, or picking another wizard, changes how high the wizard floats.
- **Walks drift from the stills.** In some facings the lowest walk row differs from the standing still by up to 14 px (for example feminine-light south: standing 158, walk 161-172). Part of that is the forward foot in perspective.
- **Sorting near the door can look wrong.** Where the wizard stands just on the camera side of D1, NSC-075's sort rule draws the wizard over the door, but its drawn feet appear at or behind the door line. The test's draw order passes while the picture still looks wrong.

## Precedent

- **Enemies already use a feet pivot.** NSC-077 AC-002, which the Art Director advised, puts the pivot "on the image's ground line":
  - walk frames use the inventory's `alpha_bottom_y_from_top`;
  - idle stills use their lowest opaque row;
  - an optional whole-pixel correction table covers per type and direction fixes.
- Vincent on that result: "The enemies look great."

## Recommendation

1. **NSC-075 (180 px art at 90 PPU):**
   - Replace the (0.5, 0) pivot with NSC-077's ground-line rule. Idle stills pivot on their lowest opaque row. Walk frames use one ground line per variant and direction, taken from the standing still unless measured otherwise, so the walk doesn't jitter.
   - Keep the same optional correction table.
   - VAL-001 checks each pivot against the pixels and the table.
2. **NSC-095 (art remake, mine):**
   - Normalize so every facing's standing feet sit on one common ground-line row, using a whole-pixel vertical shift per direction and animation, never per frame, so the walk bob survives.
   - Leave room below the line for toward-camera steps. I pick the exact row from measured walk dips, about 114-118 of 128.
   - The inventory records `ground_line_y_from_top` per wizard and `alpha_bottom_y_from_top` per frame.
3. **NSC-096 (128 px switch):**
   - Pivot y = (128 - ground_line_y_from_top) / 128, read from the NSC-095 inventory, not (0.5, 0).
   - `WizardArtIntegrationTests` checks it against the inventory and the pixels.
   - With one common row, the pivot is a single constant and turning never makes the wizard hop.

## Done means

- The NSC-095 and NSC-096 drafts carry points 2 and 3 (or the GER Agent records why not).
- An NSC-075 revision for point 1 is decided by the GER Agent: now, or queued until the pause lifts.
- Reply to: Art Director Agent.
