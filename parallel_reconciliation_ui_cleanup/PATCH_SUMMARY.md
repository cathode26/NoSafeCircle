# Parallel Reconciliation Console Cleanup

This patch changes console presentation only.

## Problem

Parallel worker threads were issuing several independent `print()` calls for
each start banner. Those calls could interleave with other workers, producing
output such as:

`Starting worker...Starting worker...`

and merged separator lines.

## Fix

- add a single console lock shared by worker threads;
- print each multi-line banner atomically;
- add explicit start/end separator lines around every worker;
- format worker metadata into aligned lines;
- add clear `[START]` and `[DONE]` markers;
- add a `WORKER PHASE COMPLETE` end block with completed count and wall-clock time;
- flush completed blocks immediately.

Example:

```text
------------------------------------------------------------------------
[START] Player Core Systems
  Routing : player, player-movement, player-health, player-mana
  Model   : sonnet
  Turns   : 16
------------------------------------------------------------------------

------------------------------------------------------------------------
[DONE]  Player Core Systems
  Duration: 258.90 seconds
------------------------------------------------------------------------
```

## Safety

Only `Pipeline/Reconciliation/parallel_reconciliation_agent.py` changes.

No reconciliation semantics, prompts, GDD files, outputs, or Tasks are changed.
