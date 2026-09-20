Correction to the reset assignment: reuse the existing reset implementation rather than creating an unrelated reset system.

Start from `Pipeline/TaskReviewAgent/reset_rehearsal_task.py` and its tests/runbook. Extract or adapt its proven planning, exact-identity, dry-run/apply, and recovery behavior for AssistantControl's local no-remote `gauntlet-replay/*` mode.

The current old command itself requires a private GitHub rehearsal repository and an additive pushed revert, so do not invoke that production-shaped path against the local no-remote replay. Add only the thin AssistantControl adapter needed for the same operator meaning: the selected task becomes fresh and runnable again, old evidence remains archived, unrelated tasks are preserved, and no GitHub operation occurs.

Keep the prior acceptance cases. Avoid duplicating reset algorithms already available in the old implementation.
