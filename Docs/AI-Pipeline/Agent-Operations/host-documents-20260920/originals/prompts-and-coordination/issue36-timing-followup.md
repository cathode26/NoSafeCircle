Additional viewer defect observed during the live eight-task gauntlet:

Task details renders the `pipeline timing` section, but AssistantControl's `/api/state` returns all of these task progress fields as null while the controller journal contains exact `action_started` / `action_completed` timestamps and `duration_seconds`:

- `current_attempt_elapsed_seconds`
- `stage_elapsed_seconds`
- `total_elapsed_seconds`
- `durable_stage_elapsed_seconds`
- `durable_task_elapsed_seconds`

Please extend the isolated viewer fix to project authenticated controller-journal timing into each in-scope task's existing `progress` schema. Preserve timing when `_apply_running_controller_projection` changes a task's phase; it currently replaces the entire progress dictionary. Use completed journal durations for durable stages and the matching active `action_started` timestamp for the live stage. Never invent a zero duration when evidence is absent. Cover a running action, a completed action, decomposition, post-crew validation, and a row with no timing evidence. Keep this viewer-only: do not alter controller execution, task contracts, generated task outputs, GitHub state, or main.
