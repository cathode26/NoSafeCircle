Read $containerOutput/00-problem-brief.md, all four completed reviewer reports below, and the relevant repository code:

- $containerOutput/01-authority.md
- $containerOutput/02-concurrency.md
- $containerOutput/03-operator.md
- $containerOutput/04-adversary.md

You are the principal architect. Do not majority-vote. Resolve disagreements by checking the code and choosing the smallest design that actually satisfies the safety and operator requirements.

Produce one implementation-ready architecture. It must decide, not merely list alternatives.

Required headings:
- Executive decision
- Why the current command is resume-only
- Final command semantics
- Committed dispatch-policy schema
- Exact candidate eligibility algorithm
- Exact deterministic priority algorithm
- Atomic fresh-claim protocol and linearization point
- Two-worker behavior from an empty queue
- Crash and orphan recovery
- Resource and WIP enforcement
- Explicit -TaskId behavior
- No-work and policy-disabled behavior
- Durable events, receipts, branches, and Issues
- Exact patch plan by module/function
- Ordered implementation stages
- Complete deterministic regression matrix
- Production canary plan
- Rejected alternatives and why
- Open questions requiring Vincent's decision

For the patch plan, name precise files/functions and describe inputs, outputs, and invariants. Do not write code. Do not claim atomicity without naming the atomic primitive or election rule.