# Raw Import Manifest

Imported: 2026-08-30

These files are immutable historical transcripts imported during the context-system bootstrap.

Common private-token patterns were scanned before packaging (OpenAI `sk-...`, GitHub classic/fine-grained token prefixes, AWS access-key IDs, private-key headers); no matching credential values were detected. This is a lightweight hygiene check, not a guarantee that every possible sensitive value is absent.

| File | Bytes | SHA-256 |
|---|---:|---|
| `imported-2026-08-30-Build-Task-Orchestrator1.txt` | 534253 | `aa4c1134a54f14b9757bdbe8589e37a3202cd899d66b973857505b7dcbd63905` |
| `imported-2026-08-30-Build-Task-Orchestrator2.txt` | 1221417 | `0e2b5900b82d5b5ef60412534c6d8a8503d36a2271153e35626fc76c30c677ab` |
| `imported-2026-08-30-Set-Coding-Standards.txt` | 48357 | `6ddc1b6eaf651ac464ba5f918e0ab2dcf7cfd928780be8c4f942f74a535e1b84` |

## Rules

- Do not edit these files to make old facts look current.
- Do not use them as authority for current Git/GitHub/TaskGraph state.
- If a transcript is later found to contain sensitive or unrelated material, remove it deliberately and document that cleanup rather than silently rewriting history.
