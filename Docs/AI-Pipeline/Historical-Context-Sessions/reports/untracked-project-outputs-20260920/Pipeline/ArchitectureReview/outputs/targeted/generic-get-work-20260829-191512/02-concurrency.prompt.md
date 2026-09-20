Read $containerOutput/00-problem-brief.md completely, then inspect the actual repository.

Act as a distributed-systems architect. Assume two workers begin the same no-task-ID command at nearly the same time with an empty Issue queue. Reconstruct every race in candidate selection, branch/ref creation, Issue initialization, lease acquisition, resource reservation, and checkout creation. Compare the proposed locking/claim alternatives and choose a concrete linearization point. Include crash recovery and cross-machine behavior.

Required headings:
- Current race window
- Safety and liveness invariants
- Claim mechanism comparison
- Recommended atomic claim protocol
- Crash and orphan recovery
- Resource-conflict revalidation
- Exact module changes
- Concurrency test harness
- Designs that appear safe but are not