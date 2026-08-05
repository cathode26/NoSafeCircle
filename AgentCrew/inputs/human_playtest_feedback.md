# Human Playtest Feedback — Door Progress Indicator

## Result

The sealed door opens correctly after holding E for five seconds.

## Defect

The visible progress bar appears, but it does not visually update while the interaction is occurring.

## Expected Behavior

While E is held and the interaction remains uninterrupted, the progress indicator should visibly increase from 0 to 1 over five seconds.

Movement, damage, or releasing E should reset the indicator to 0.

## Required Repair

Inspect the generated UI component, scene-builder configuration, and door progress binding.

Fix the underlying generated implementation rather than relying on a manual Inspector adjustment.

Ensure the scene-builder command produces the correct configuration every time it runs.

Add or update automated coverage where practical.

## Human Retest Requirements

1. Rebuild the prototype scene.
2. Hold E and confirm the bar visibly fills over five seconds.
3. Release E and confirm it resets.
4. Move and confirm it resets.
5. Trigger damage and confirm it resets.
6. Confirm the door still opens after an uninterrupted five seconds.
7. Run the scene-builder twice and confirm the repair persists.
