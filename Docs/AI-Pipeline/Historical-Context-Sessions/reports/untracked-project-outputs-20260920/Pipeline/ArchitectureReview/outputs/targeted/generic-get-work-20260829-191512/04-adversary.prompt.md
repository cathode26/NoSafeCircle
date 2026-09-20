Read $containerOutput/00-problem-brief.md completely, then inspect the actual repository.

Act as an adversarial QA and failure-mode reviewer. Try to break a future generic get-work dispatcher. Look for duplicate Issues, split leases, stale task contracts, stale main, branch-name collisions, orphan claims, resource aliasing, priority starvation, completed-task resurrection, unsafe explicit overrides, partial GitHub outages, interrupted processes, and misleading success exits. Require evidence for every claimed safety property.

Required headings:
- Highest-risk failure modes
- Race interleavings
- Authority and identity attacks
- Recovery failures
- Observability requirements
- Mandatory negative tests
- Conditions that must block release
- Smallest design that survives the review