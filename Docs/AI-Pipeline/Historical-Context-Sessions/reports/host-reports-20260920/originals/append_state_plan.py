"""Append tomorrow's ready-to-run evidence plan to the Game Agent state file."""
import io

path = r'C:\NSC\agent-state\game-agent.md'
data = io.open(path, encoding='utf-8', newline='').read()

anchor = "## Rooms (what Vincent has been waiting for all evening)"

block = """## TOMORROW: start here. Two evidence passes, no Vincent time, 17 tasks unblocked

From the Viewer Agent's evidence-debt audit (`C:\\nscrev\\reports\\viewer-agent\\evidence-debt-audit-20260918.md`):
of 95 tasks, 16 conformant and 51 not_delivered, and much of that 51 is built-and-merged work with
no record. **The evidence debt, not design or art, is the binding constraint on this graph.**

**Run these two first.** Both have one gate, neither needs Vincent, policy entries are on main:

| task | unblocks | policy entry | platform | filter | tests |
|---|---|---|---|---|---|
| NSC-089 NavMesh surface + agent config | **9** | `497f0d662` | EditMode | `...Tests.Editor.NavMeshAgentConfigurationTests` | 2 |
| NSC-091 enemy target detection | **8** | `8b0f82933` | PlayMode | `...Tests.EnemyTargetKnowledgePlayModeTests` | 22 |

- Both fixtures verified by **declaration**, not filename, and neither is `partial`. The GER Agent
  also **counted the tests** - a filter resolving to a real but empty fixture passes vacuously,
  which is the same failure as selecting zero tests in better disguise. Count them on every future
  gate.
- **Bind the record at whatever main is when Unity runs**, not at the historical integration commit.
  `record_delivery` requires `HEAD == validated_commit`. NSC-089's real integration was `4047a4335`
  (EditMode 2/2, builder regression 57/57) and its assistant-control record still says
  `materialization_failed` from a superseded 2026-09-14 run - put both in the record's notes as
  provenance, and say plainly that the stale record was not the validated state.
- Method is the NSC-069 one, which works end to end: `run_unity_tests_clean.ps1` for the bound
  manifest, then `generate_delivery_spec.py draft` -> fill review -> `finalize` ->
  `record_delivery.py` -> stage exactly what it prints -> `validate_draft_evidence.py` ->
  commit in branch-verify -> Vincent fast-forwards main.
- Gotchas already hit: the review schema has **no `result` field** on gates (finalize fails with
  "gate fields differ"); select only the task's own `exclusive_resources` as surfaces, or a distant
  base commit offers thousands; stage the record JSON as well as the two artifacts.

**Then the wizard chain** (Vincent's explicit choice): NSC-073, NSC-074, NSC-062, NSC-070, NSC-068.
Five records, five human gates - VAL-002, VAL-002, VAL-005, VAL-005, VAL-005 - collected in **one**
20-30 minute sitting at one commit, not five interruptions. Unblocks NSC-075, the stretched wizard
(`Player/Visual` scale `(1,2,1)`, identity rotation; AC-006 wants `Vector2.one` and
`Quaternion.Euler(IsometricCameraEulerAngles)`). NSC-068's entry is `f06ed3815`.

**NSC-061 is not in this queue.** Its gates name no Unity fixture at all, so there is nothing to
bind; the GER Agent is deciding between a contract revision and the untested `SyntheticSource`
path. Not paperwork - a contract question.

"""

if anchor in data and 'TOMORROW: start here' not in data:
    io.open(path, 'w', encoding='utf-8', newline='').write(data.replace(anchor, block + anchor, 1))
    print('plan appended')
else:
    print('anchor missing or plan already present')
