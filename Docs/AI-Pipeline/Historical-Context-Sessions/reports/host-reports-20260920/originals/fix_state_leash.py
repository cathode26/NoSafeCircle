"""Record that the leash fix is held as a reference implementation, not merged."""
import io

path = r'C:\NSC\agent-state\game-agent.md'
lines = io.open(path, encoding='utf-8', newline='').read().split('\n')

start = next(i for i, line in enumerate(lines) if 'Leash/spawn fix' in line)
end = next(i for i in range(start, len(lines))
           if lines[i].startswith('- **Three reviewed pipeline branches**'))

replacement = [
    '- **Leash/spawn fix: DO NOT MERGE. Held as a reference implementation.**',
    '  `fix/melee-leash-and-spawns-20260917` @ `68cd3aeee` in branch-verify, verified Edit Mode 63/63',
    '  and Play Mode 8/8 including `SavedSceneMeleeEnemy_PursuesRetreatingWizardWithoutTheOldDemoLeash`.',
    '  It fixes the melee enemy walking toward the player and away, which Vincent reported by eye.',
    '  **It is going to an NSC-015 child instead**, decided 2026-09-17 with the GER Agent, because it',
    '  is not a small patch: it removes the leash wiring (`EnemyPursuitLeashDistance`, the',
    '  `SetMaximumPursuitDistanceFromStart` call) **and** moves three authored spawn positions',
    '  (Bone Archive melee (-6,0,10)->(-3,0,10), Lower Vault melee (-7,0,53)->(-2,0,53), Chapel wraith',
    '  (-9,0,27)->(-9,0,31)) in `DoorPrototypeGlobalSceneBuilder.cs`, a file **11 tasks claim**.',
    '  The two halves are one unit: the spawn moves exist because unleashed pursuit needs clear',
    '  starting ground, and the test fails until the wiring is gone.',
    '  NSC-015 reopens anyway - its AC-001 said "unless Vincent approves a later locomotion-owner',
    '  revision" and AC-006 said body collision "remain[s] pending Vincent\'s decisions", and he',
    '  answered all of them tonight (enemies block each other, rooted wind-up, gory corpse variants,',
    '  no corpse collision). Hand the branch over as reference; do not merge it as maintenance.',
    '  Identity leak on two commits was rewritten; pre-rewrite tip archived at',
    '  `refs/archive/fix-melee-leash-and-spawns-20260917-pre-identity-rewrite`.',
    '  **Visible cost while it waits:** the melee enemy keeps its back-and-forth. Vincent has been',
    '  told and can override by asking for the merge.',
    '- **NSC-092 evidence does NOT wait for the leash fix.** I advised that it should, then reversed:',
    '  holding 8 tasks behind an unwritten contract to avoid a `delivery_recheck_suggested` flag is a',
    '  bad trade, and that flag means coverage grew rather than that the record lied. A record binds',
    '  the commit it was measured at and stays true.',
]

io.open(path, 'w', encoding='utf-8', newline='').write('\n'.join(lines[:start] + replacement + lines[end:]))
print('state file updated: leash fix marked DO NOT MERGE with its reasoning')
