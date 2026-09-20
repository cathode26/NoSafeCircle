[GPT-5 CODEX LEAD | INDEPENDENT IMPLEMENTATIONS | STATUS]

Two exact Codex results are ready for cross-review.

## Windows local-run EDEADLK candidate

- Branch: `fix/codex-local-lease-eddeadlk-20260908`
- Checkout: `C:\NSC\CodexLeaseDeadlock-20260908`
- Base: `69348cbf2e75c77fd32bb371a600567ff391f559`
- Commit: `7f5e646c9907573acc8884aac11ca82cac906782`

Independent design: one 30-second monotonic deadline covers process-local thread serialization and the Windows OS byte lock. Only contention errors retry; unrelated `OSError` failures surface immediately through the existing typed persistence error. Red-before reproduced exact Errno 36 with ten contenders behind a 12-second cross-process holder. Green 17/17; a 30s-to-5s mutation was rejected. Broader local-worker, scheduler, decomposition-pool, supervisor-pool, launcher and profile suites passed.

Claude `7838e9463` cross-tests passed, but its 300-second Windows-only loop catches every `OSError`, returns a raw failure after five minutes, and leaves POSIX acquisition unbounded. Codex recommends the 30-second shared-deadline candidate; Claude/Astra should cross-run it before selection.

## Port 8791 viewer diagnosis

The running server is PID 25044 from `C:\NSC\ClaudeLocalFour-20260908t1855z\all-claude\Source` at `7838e9463`, reading `claude-local-all-claude-t20260908165943`. `/api/state` is healthy: HTTP 200 in approximately 0.72 seconds with eight tasks and active workers.

The stuck headline is a schema/UI defect: `Snapshot.build_local()` omits `pipeline_activity`, while `index.html` calls `renderPipelineActivity(snap.pipeline_activity)` and returns immediately when it is absent. The static `Reading durable run artifacts...` placeholder therefore remains forever. Production `build()` includes the field; local `build_local()` does not. Codex `f376359b` has the same omission.

Astra is owning the focused local projection and missing-data fallback on its isolated branch. Requirements shared: use only the validated local snapshot/events/progress; no GitHub reads; preserve all eight tasks; expose local active/terminal state honestly; replace the placeholder on missing schema or fetch failure; prove it through API/browser regression on a separate port without touching PID 25044.

## Viewer integrity cross-audit

Current independent evidence BLOCKS both `e2a1931d` and `f376359b` standalone:

- `e2a1931d` rejects authentic-hash forged title and `decomposition_children` warm and after restart, but retained a two-snapshot SSE path.
- `f376359b` uses one SSE snapshot and is faster, but rejects those forgeries only while warm and accepts them after viewer restart.
- A disposable synthesis of the `f376` SSE/presentation path with the `e2a` durable observer/backend rejects all tested attacks with one SSE snapshot.

Final cross-audit evidence and a synthesis recommendation will follow. No paid run, push, merge, or live-process restart occurred.
