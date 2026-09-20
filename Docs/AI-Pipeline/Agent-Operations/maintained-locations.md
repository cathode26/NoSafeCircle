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
| `C:/nscrev/ger-tools/` (junction → `C:/NSC/tools/ger`) | `validate_in_memory.py` inserts this path and imports `apply_contract` through it | **`Tools/Host/ger/`** — *(corrected 2026-09-20: this row first named `Tools/Host/ger-contract-revisions-20260916/`, which is the **caller**, not the source. The helper it reaches, `apply_contract.py`, is maintained under `Tools/Host/ger/`.)* |
| `C:/NSC/tools/<family>/` | Every deployed host tool runs from here; six junctions under `C:/nscrev` point into it | `Tools/Host/<family>/` |

**Recording a path as required is not approval to keep editing it.** Edit the tracked source, then
deploy. A deployed copy that has drifted from its source is a defect, not a second master — and
these two were hash-identical when recorded on 2026-09-20, which is the state to keep.

## Checking for drift, until there is a tool for it

A generated source-to-deployment map is designed and owned by the Pipeline Maintainer. **Until it
exists, this is the manual check** — compare each tracked file against its deployed copy by hash,
ignoring line endings:

```bash
# drift.sh <family> <deployed-root> [min-expected-files]
# exit 0 in step | 1 drift or unclassified missing | 2 inventory empty or unreadable
R=${NSC_REPO:-C:/NSC/NSC/NoSafeCircle}; fam=$1; dep=$2; min=${3:-1}

git -C "$R" rev-parse --verify -q main >/dev/null || { echo "FAIL: no repo or no main at $R"; exit 2; }
mapfile -t files < <(git -C "$R" ls-tree -r --name-only main -- "Tools/Host/$fam")
[ "${#files[@]}" -ge "$min" ] || { echo "FAIL: inventory for Tools/Host/$fam has ${#files[@]} files, expected >= $min"; exit 2; }

checked=0; drift=0; missing=0
for p in "${files[@]}"; do
  rel=${p#Tools/Host/$fam/}
  case "$rel" in */*) sub=${rel%%/*};; *) sub="";; esac
  [ -n "$NSC_SKIP_SUBTREE" ] && [ "$sub" = "$NSC_SKIP_SUBTREE" ] && continue   # subtree with its own root
  live="$dep/$rel"
  [ -f "$live" ] || { echo "  MISSING (unclassified) $rel"; missing=$((missing+1)); continue; }
  t=$(git -C "$R" show "main:$p" | tr -d '\r' | sha256sum | cut -c1-16) || { echo "FAIL: cannot read main:$p"; exit 2; }
  l=$(tr -d '\r' < "$live" | sha256sum | cut -c1-16) || { echo "FAIL: cannot read $live"; exit 2; }
  checked=$((checked+1))
  [ "$t" = "$l" ] || { echo "  DRIFT $rel tracked=$t deployed=$l"; drift=$((drift+1)); }
done
[ "$checked" -gt 0 ] || { echo "FAIL: compared 0 files"; exit 2; }
echo "$fam: compared $checked, drift $drift, unclassified missing $missing"
[ $((drift + missing)) -eq 0 ] || exit 1
```

**Why it is this defensive, and not shorter.** The first version of this check **exited 0 having
compared nothing** — a misspelled family or an unreadable repository produced silence that read as
"no drift". That is runbook rule 25's false green, in the tool written to catch drift. It now
**validates the repository, requires a non-empty inventory, propagates read failures, and prints
the count it actually compared.** A drift check that cannot say how many files it checked has not
told you anything.

**Take the deployed root from the table in `Tools/Host/README.md`, not from the family name,** and
**exclude any subtree with its own root** (`NSC_SKIP_SUBTREE=templates` for `jobs`), then check that
subtree separately against its own. `jobs/templates/` deploys to `C:/nscrev/claude-jobs/templates/`;
running `jobs` against one root reported six false missing files on 2026-09-20.

**Three outcomes, and conflating them is what makes a drift check noisy:**

| Outcome | Meaning | Action |
|---|---|---|
| Hashes differ | **Real drift.** Someone edited one side only | Reconcile, then edit the tracked source from now on |
| No deployed copy | **Unclassified — it is a finding, not a category.** It *may* be authored-in-repo, or a deliberately retired deployment such as `main_write.py.removed-20260920`, but **the check cannot tell and neither can you until you look** | Investigate and record which. **Never classify an unknown as deliberate retirement** — that is how a missing deployment becomes invisible |
| Hashes match | In step | Nothing |

Only the first is a defect; the second is an open question the check is right to raise.

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
