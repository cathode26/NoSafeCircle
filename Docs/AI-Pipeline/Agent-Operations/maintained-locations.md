# Where authored work starts

**Status: active.** Owner: Documentation Agent. Established 2026-09-20 from Vincent's brief
*"Make future authored work start in its maintained repository location."*

**This is a prevention rule for new work.** It is not a historical import, not a cleanup project,
and it does not authorize deleting anything. Existing loose files stay where they are.

---

## The rule, in one sentence

**Authored material starts in the owned checkout and is retained by Git; host locations are
deployments and exports, never the only useful copy.**

## The table

| Material | Maintained location and rule |
|---|---|
| Current role guides and launch instructions | `Docs/AI-Pipeline/Agent-Operations/Guides/` in the owned checkout — **unless an existing maintained document already owns the subject, in which case link to it rather than create a second copy.** |
| Reusable host tools and prompt templates | `Tools/Host/<family>/` source. **Edit the source first**; host copies are deliberate deployments, not masters. |
| Durable authored reports and their selected attachments | `Docs/AI-Pipeline/Reports/<WorkId>/<RunId>/` — **unless a current authoritative evidence workflow already owns the location.** Declare the destination **before writing the report.** |
| Formal task/delivery evidence | Keep existing pipeline-owned paths, manifests and hash relationships. **Do not introduce a competing report authority.** |
| Runtime logs, temporary results, live state, credentials, raw sessions | Keep existing external runtime locations. **Select final evidence deliberately; never blanket-stage these directories.** |
| Human-facing transfer copies | `Downloads` remains the export/handoff location. **A copy of a durable repository document names its source path and revision.** One-off transfer prompts may stay external. |

## Four things this gets wrong if stated loosely

**1. A file copied into a checkout is not preserved.** Only a commit is, and only a pushed commit
survives the machine. Say which of these you mean: uncommitted, committed on a branch, integrated,
verified on the remote. "It is in the repo" is not one of them.

**2. Preserved is not current.** A commit that snapshots a host file records that file *at that
moment*. On 2026-09-20 two GER committers were tracked at a revision older than their live copies —
the tracked ones still hardcoded `C:\nscrev\ger-tools` while the live ones had gained a preference
block — so the loose folder still held the newest fixes. They were reconciled in `9c8f91fa8` within
hours, which is the point: **the drift appeared between a morning commit and an afternoon one.** It
reappears whenever someone edits a deployed copy instead of the source. **A snapshot does not retire
its source. Reconcile first, then retire.**

**3. "Durable" is a decision, not a property of a folder.** Runtime output that happens to be useful
once does not become a durable report by being copied. It becomes one when someone declares a
destination for it under row 3 of the table.

**4. Two editable masters is the failure this exists to prevent.** When a document's maintained copy
moves here, the loose copy becomes a deployment that names its source and revision — not a second
place to edit. If you find yourself editing both, one of them is wrong and it is usually the loose one.

## Required runtime locations (recorded, not accidents)

The audit's choice was: change the callers, **or** explicitly retain the old paths as required
runtime locations. **These are recorded as required.** They must keep existing, they are not
cleanup targets, and the tracked copy is still the source of record for editing.

| Path | Why it is required | Source of record |
|---|---|---|
| `C:/nscrev/codex-jobs/` | The closure-review runners resolve job clones, prompts and logs beneath it, and `make_closure_prompt.py` writes beside itself — so the tracked generator and runner would disagree about where the prompt goes if run from the repo | `Tools/Host/codex-jobs/` |
| `C:/nscrev/ger-tools/` (junction) | `validate_in_memory.py` still resolves helpers through it | `Tools/Host/ger-contract-revisions-20260916/` |
| `C:/NSC/tools/<family>/` | Every deployed host tool runs from here; six junctions under `C:/nscrev` point into it | `Tools/Host/<family>/` |

**Recording a path as required is not approval to keep editing it.** Edit the tracked source, then
deploy. A deployed copy that has drifted from its source is a defect, not a second master — and
these two were hash-identical when recorded on 2026-09-20, which is the state to keep.

## Checking for drift, until there is a tool for it

A generated source-to-deployment map is designed and owned by the Pipeline Maintainer. **Until it
exists, this is the manual check** — compare each tracked file against its deployed copy by hash,
ignoring line endings:

```bash
R=C:/NSC/NSC/NoSafeCircle; fam=astra; dep=C:/NSC/tools/astra
while IFS= read -r p; do
  live="$dep/${p#Tools/Host/$fam/}"
  [ -f "$live" ] || { echo "no deployed copy: $p"; continue; }
  t=$(git -C "$R" show "main:$p" | tr -d '\r' | sha256sum | cut -c1-16)
  l=$(tr -d '\r' < "$live" | sha256sum | cut -c1-16)
  [ "$t" = "$l" ] || echo "DRIFT $p  tracked=$t deployed=$l"
done < <(git -C "$R" ls-tree -r --name-only main -- "Tools/Host/$fam")
```

**Take the deployed root from the table in `Tools/Host/README.md`, not from the family name.**
`jobs/templates/` deploys to `C:/nscrev/claude-jobs/templates/`, not under `C:/NSC/tools/jobs/`;
pointing the check at the wrong root reported six false drifts on 2026-09-20 before the table was
consulted.

**Three outcomes, and conflating them is what makes a drift check noisy:**

| Outcome | Meaning | Action |
|---|---|---|
| Hashes differ | **Real drift.** Someone edited one side only | Reconcile, then edit the tracked source from now on |
| No deployed copy | Either **authored in the repo** (a README with no deployment) or a **deliberately retired** deployment, e.g. `main_write.py.removed-20260920` | Usually nothing. Confirm which before acting |
| Hashes match | In step | Nothing |

**Found by this check on the day it was written:** `Tools/Host/astra/README.md` was tracked as
*"the live smoke test has not been run"* while its deployed copy recorded the round trip passing on
2026-09-20. **The source of record was the stale one.** Reconciled in the same commit — which is the
whole point: drift is silent, cheap to find, and it always looks like nobody's fault.

## What is a receipt and what is an index

`Tools/Host/source-map.json` is a **receipt of one import run**, not a living source/deployment map:
its `destination_root` names a single dated staging folder and every record carries that run's
sha256 pair. **Do not hand-edit it to add newly tracked families** — that would falsify a receipt.
A family is indexed for readers in `Tools/Host/README.md`; a *living* source-to-deployment map,
if one is wanted, is a separate artifact and needs its own generator.

## Scope

- **Applies to:** work authored from 2026-09-20 onward.
- **Does not apply to:** `originals/` and other imported history, which are immutable and are not
  the maintained guides to edit. **Old instructions do not become current because they were copied.**
- **Grants nothing.** No deletion, no retirement, no publication authority. Retiring any loose
  location still requires its own inventory and disposition, and recursive deletes at depth 1 or 2
  from `C:\` are Vincent's to execute (`nsc-pipeline-runbook.md` rule 26).

## Entry points that point here

`nsc-pipeline-runbook.md` ("Agent tools" row), `Docs/AI-Pipeline/Agent-Operations/README.md`,
`Tools/Host/README.md`, and the `doc-sync` and `pipeline-maintainer` agent definitions.
