# Raw Import Manifest

Imported: 2026-08-30

These files are immutable historical transcripts imported during the context-system bootstrap.

Common private-token patterns were scanned before packaging (OpenAI `sk-...`, GitHub classic/fine-grained token prefixes, AWS access-key IDs, private-key headers); no matching credential values were detected. This is a lightweight hygiene check, not a guarantee that every possible sensitive value is absent.

| File | Bytes | SHA-256 |
|---|---:|---|
| `imported-2026-08-30-Build-Task-Orchestrator1.txt` | 534253 | `aa4c1134a54f14b9757bdbe8589e37a3202cd899d66b973857505b7dcbd63905` |
| `imported-2026-08-30-Build-Task-Orchestrator2.txt` | 1221417 | `0e2b5900b82d5b5ef60412534c6d8a8503d36a2271153e35626fc76c30c677ab` |
| `imported-2026-08-30-Set-Coding-Standards.txt` | 48357 | `6ddc1b6eaf651ac464ba5f918e0ab2dcf7cfd928780be8c4f942f74a535e1b84` |

## Later imports

The entries above are the original bootstrap import and are not restated or recalculated here.

### Added 2026-09-01

| File | Bytes | SHA-256 |
|---|---:|---|
| `imported-2026-08-31-Build-Task-Orchestrator3.txt` | 663736 | `b89c55d3ae0d4e8de7afc41e99e700728d4e1c1cd2ab8c442c43ee5bcd100814` |
| `imported-2026-09-01-Gauntlet-PR-CI.txt` | 571323 | `4d30440460dce5736c78ca9867757e6faaa9b13b5d3a775f5a65ffe9876129cc` |

`imported-2026-08-31-Build-Task-Orchestrator3.txt` is the 2026-08-31 live Gauntlet session
(synthetic lifecycle, production #104 read-after-write hardening, NSC-601 evidence checkpoint, and
the PR #9 exact-head CI problem plus the preparation work for a fresh-CI retry). It ends while
that fresh-CI recovery is still being prepared; it does **not** contain the completed exact-head CI
recovery or the NSC-601 live lifecycle acceptance. It was originally staged on the draft
documentation PR #110 branch, which was never merged, and is restored here unchanged.

`imported-2026-09-01-Gauntlet-PR-CI.txt` is the long 2026-08-31 -> 2026-09-01 working session. It
picks up past the point where the previous transcript ends and covers the PR #9 exact-head CI
recovery, NSC-601 same-worker live lifecycle acceptance, the Stage-2 bulk state observation scaling
diagnosis and repair, Phase A/Phase B completion, Stage-5 D1C Slices 1-3, the pivot to one
supervised polling Software Architect (ADR-045), the new Software Architect Acceptance Gauntlet,
the integration mapping, and the execution-routing and decomposition-authorization planning.

Both files are advisory raw history with the same status as the bootstrap imports: they are not
authority for current Git, GitHub, TaskGraph, or checkout state, and they contain many
intermediate states and failed commands that were later superseded within the same session. The
concise current record is `../CURRENT_CONTEXT.md`; the structured rationale is
`../2026-09-01-software-architect-integration.md`.

No credential scan was performed on these two files during this import. The bootstrap-scan
statement above applies only to the three original 2026-08-30 files.

### Byte/hash convention

Sizes and SHA-256 values in this manifest are computed from the exact bytes of the Windows
working-tree copy, which uses CRLF line endings. The corresponding Git blob is stored with LF and
therefore has a different size and hash. Recompute against a Windows checkout when verifying.

## Rules

- Do not edit these files to make old facts look current.
- Do not use them as authority for current Git/GitHub/TaskGraph state.
- If a transcript is later found to contain sensitive or unrelated material, remove it deliberately and document that cleanup rather than silently rewriting history.
