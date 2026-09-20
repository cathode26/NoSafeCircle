Final scope clarification: **do not build a new reset engine**.

Make AssistantControl expose and call the existing reset implementation. Add only the compatibility layer needed to map AssistantControl's task record, checkout root, source binding, and local replay mode into the old reset command's proven plan/apply/recovery flow. Reuse its checks and tests wherever possible.

Operator result: `AssistantControl reset-task NSC-1124` dry-runs; adding `--apply` makes NSC-1124 fresh and immediately runnable again. No stale checkout, reservation, decomposition failure, or controller projection may survive. Other tasks remain untouched. No GitHub activity for a local no-remote Gauntlet replay.
