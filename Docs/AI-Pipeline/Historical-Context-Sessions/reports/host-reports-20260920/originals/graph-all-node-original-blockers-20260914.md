# No Safe Circle all-node audit: original Graph Sol blockers

Date: 2026-09-14  
Canonical source: `C:/NSC/NSC/NoSafeCircle`, `f2a9a6e1d`  
Scope: read-only audit; no provider, Docker, Unity, canonical, Issue, or viewer mutation.

## Result

`taskcontrol validate` passes: 91 contracts, 68 `single_agent` implementations, 93 resource groups, connected/acyclic hierarchy and dependency graph. The only clear missing-new-file ownership cluster is NSC-089 through NSC-092. It is already repaired on isolated branch `codex/nsc-new-file-scope-repair`, commit `fdbeb9634ab2b8b09bf9967039ad305e8c882297` (based on `731c1c10c`), and is also present at canonical `f2a9a6e1d`.

The repair adds exact `repo-file:` claims and matching resource-group entries for every newly named gameplay script/test in NSC-089..092, plus the tracked `Scripts/Enemies/.gitkeep` parent. No additional safe claim additions were identified.

## Method and limits

Every `Tasks/*.yaml` file was parsed as JSON-backed schema-v2 YAML. All 91 IDs were enumerated and classified by `kind`, `execution_scope`, `decomposition_state`, parent, and disposition. For each active `single_agent` contract, acceptance/decomposition/execution text was scanned for exact `Create`, `Add`, or `New` `Assets/...` paths; each candidate was normalized for punctuation and compared with its `exclusive_resources` declarations. Resource-group membership was checked against `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`; existing ownership was checked with `git ls-tree` at canonical HEAD. This proves declared ownership consistency, not provider behavior or runtime correctness. Paths mentioned as read-only context, generated Unity output, or prose examples were not promoted into write claims.

## All 91-node classification

Aggregate/decomposed or non-executable: NSC-001, NSC-002, NSC-006, NSC-010, NSC-014, NSC-016, NSC-018, NSC-021, NSC-022, NSC-025, NSC-027, NSC-029, NSC-030, NSC-031, NSC-034, NSC-035, NSC-036, NSC-056.

Human integration required: NSC-057. Unknown execution scope: NSC-088. Artifact: NSC-059.

Concrete `single_agent` nodes with no newly named unclaimed `Assets` path in the static scan: NSC-003, NSC-004, NSC-005, NSC-007, NSC-008, NSC-009, NSC-011, NSC-012, NSC-013, NSC-017, NSC-019, NSC-020, NSC-023, NSC-024, NSC-028, NSC-032, NSC-037, NSC-039, NSC-040, NSC-041, NSC-042, NSC-044, NSC-045, NSC-046, NSC-047, NSC-048, NSC-049, NSC-050, NSC-051, NSC-052, NSC-053, NSC-054, NSC-055, NSC-058, NSC-060, NSC-061, NSC-062, NSC-063, NSC-064, NSC-065, NSC-066, NSC-067, NSC-068, NSC-069, NSC-070, NSC-071, NSC-072, NSC-073, NSC-074, NSC-075, NSC-077, NSC-078, NSC-079, NSC-080, NSC-081, NSC-082, NSC-083, NSC-084, NSC-085, NSC-086, NSC-087.

Fixed new-file ownership cluster: NSC-089, NSC-090, NSC-091, NSC-092.

## Known scheduler repeat risks

Historical `C:/NSC/NoSafeCircle-AssistantCheckouts/.assistant-control/graph-controller.json` is `blocked`. NSC-003 has a failed Claude worker (`ExecutionCrew reasoning effort is supported only for codex`), then a retry rejected for `role made no required file modification`; its checkout remains `prepared` with stale worker history. The controller did not advance to another candidate. Event logs show NSC-038 and NSC-059 failing automatic scope because there was no resolvable committed C# test. NSC-043 is also a shortlist item with missing automatic-scope proof in the historical run. These are scheduler/scope recovery risks, distinct from resource declarations.

## Confidence limits and priority

High confidence: schema/resource validation and the NSC-089..092 diff. Medium confidence: historical blocked-checkout behavior, because the inspected control root is a prior run and not live authority. Low confidence: claims about current blue viewer nodes; port 8828 serves held viewer source `C:/NSC/viewer-held-live` at `6464c19b`, idle and separate from canonical main.

Priority 1 is to integrate/revalidate the isolated NSC-089..092 resource repair. Priority 2 is scheduler recovery: on worker rejection or blocked checkout, release/mark the failed candidate and continue bounded selection. Priority 3 is to give NSC-038, NSC-043, and NSC-059 resolvable committed tests or explicitly route them to human/decomposition handling; do not guess ownership for them.
