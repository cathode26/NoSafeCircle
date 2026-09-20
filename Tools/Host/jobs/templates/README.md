# Docker Claude job templates

These jobs run on Vincent's **Gmail** Claude account in Docker, which spares the desktop (Outlook) account that every agent session uses. Vincent approved them on 2026-09-17 for helper work in each agent's own lane.

**How to run a job:** follow `C:\NSC\nsc-codex-jobs-guide.md`, section 4.3 (clone, prompt, run, read the result).

| Template | Service | Model | Instead of |
|---|---|---|---|
| `lookup-job-prompt.md` | `claude-exec` (read-only) | Haiku or Sonnet | Explore or Haiku lookup subagents |
| `review-job-prompt.md` | `claude-exec` (read-only) | Sonnet; Opus for risky code | `pipeline-reviewer` and other Claude reviews |
| `test-run-job-prompt.md` | `claude-exec` (read-only; tests run in `/tmp` copies) | Haiku | `test-runner`, except Windows-only tests |
| `clone-edit-job-prompt.md` | `claude` (read-write, job clone only) | Sonnet | Sonnet "easy fix" subagents; porting a known commit |
| `contract-draft-job-prompt.md` | `claude` (read-write, job clone only) | Sonnet | `ger-drafter` |

**Stay on desktop subagents** for Unity (`unity-runner`, `delivery-evidence`), PixelLab (`pixellab-batch-recorder`), files outside a repo clone (`scribe`, `doc-sync`, the board, the journal, `C:\NSC` docs), Windows-only tests, and steps that need your session's context.

Jobs write prompts, results and logs next to this folder, in `C:\nscrev\claude-jobs\`. The two verification jobs from 2026-09-17 are there too.
