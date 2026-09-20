OpenAI GPT-5.6 Sol — supervisor schema investigation

The exact NSC-1001 failure is recorded in `C:\NSC\TwoLocalGauntletDemo-t20260909-015701z\all-claude\Checkouts\.task-review-agent\local-rehearsals\claude-local-all-claude-reset-t20260909-025044z\checkouts\.task-review-agent\outputs\NSC-1001\scheduler-nsc-1001-a454246e2eea426e\progress.log` at 03:20:50Z:

`action acquire_agent_lease arguments mismatch; missing=[], extras=['expected_result']`

Cause: `Pipeline/TaskReviewAgent/codex_supervisor.py:decision_schema()` exposes one union of every action argument, including `expected_result`, with `additionalProperties: false`. The later action-specific validator permits `acquire_agent_lease` only `planned_approach` and `expected_validation`. Claude therefore returned output that was valid against the provider-facing schema but invalid for the selected action. It corrected the call on turn 2, but this avoidable retry cost about 50 seconds and another 21,316 tokens.

The corrected host action then took 145.88 seconds from 03:21:40Z to 03:24:05Z. That host/GitHub mutation latency is separate from the schema retry.

Proposed fix: build the provider-facing argument properties from the currently allowed action set, or use action-discriminated schema branches if both providers accept them. Add a regression test where `acquire_agent_lease` cannot emit `expected_result`, while human-handoff actions continue to require it. Keep the existing fail-closed action-specific validator as defense in depth.
