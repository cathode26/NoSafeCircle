# ADR-045 — `needs_testing` does not block downstream dependencies

**Accepted:** 2026-08-25

## Context

TaskGraph schema-v2 conformance states describe whether committed evidence currently proves one task at committed `HEAD`. They do not define dependency readiness or execution authorization.

`needs_testing` is emitted when a task was previously delivered/evidenced but one of its tracked conformance surfaces or other current-state invariants changed later. The completed behavior may need another testing/revalidation pass before that task can again claim current `conformant` status.

During NSC-040 startup, an orchestrator incorrectly generated a guard that required every dependency to report exactly `conformant`. That would have treated NSC-038's `needs_testing` state as if its implementation were missing and would have blocked unrelated downstream progress even though NSC-038 had already been delivered and remained integrated on `main`.

## Decision

A dependency whose TaskGraph state is `needs_testing` is **non-blocking solely because of that state**.

`needs_testing` means revalidation debt on the dependency itself. It does not revoke the fact that the dependency's implementation was previously delivered and integrated, and it does not by itself make downstream implementation, checkout, decomposition, or execution ineligible.

The following rule is mandatory for human-directed orchestration:

> Never require `dependency.state == "conformant"` as a generic prerequisite for downstream work. In particular, `needs_testing` must not block downstream work solely because current conformance evidence needs refreshing.

This is an interim dependency-state semantic while the repository's full deterministic dependency-readiness/dispatch policy remains intentionally unimplemented.

## Operational consequences

When inspecting a selected task's dependencies:

- `conformant` — current evidence proves the dependency; no conformance warning is needed.
- `needs_testing` — the dependency was previously delivered/evidenced and needs revalidation; record or surface that revalidation debt if useful, but **continue downstream work** unless there is a separate concrete blocker.
- other states — inspect their actual meaning and repository history. Do not infer readiness or blockage from a state name alone; determine whether the required implementation is actually integrated, whether the contract changed, whether evidence is invalid/ambiguous, or whether a real prerequisite is absent.

A separate concrete blocker can still stop downstream work. Examples include:

- the required dependency implementation was never merged or is actually absent from current `main`;
- the dependency's contract changed materially (`needs_replan`) such that the downstream contract no longer has a stable prerequisite;
- current repository inspection shows the downstream task requires behavior that does not exist;
- the Contract Locality Auditor identifies an undeclared or missing required integration;
- an exclusive-resource conflict makes parallel work unsafe.

Those are independent facts. `needs_testing` itself is not such a fact.

## Command-generation rule

Do not generate guards like:

```powershell
if ($Dependency.state -ne "conformant") {
    throw "Dependency is not ready"
}
```

If dependency conformance is displayed during setup, `needs_testing` must be informational/non-blocking, for example:

```powershell
switch ($Dependency.state) {
    "conformant" {
        Write-Host "Dependency is currently conformant."
    }
    "needs_testing" {
        Write-Host "Dependency was previously delivered; revalidation is outstanding and does not block downstream work."
    }
    default {
        Write-Host "Dependency state requires separate manual interpretation: $($Dependency.state)"
    }
}
```

Do not turn the `default` branch above into a generic automatic blocker unless an approved readiness policy later defines that behavior.

## Relationship to evidence-derived conformance

This decision does **not** weaken `needs_testing` or make TaskGraph lie about current evidence. The conformance evaluator should continue returning `needs_testing` when appropriate.

The distinction is:

```text
current conformance of dependency
        !=
downstream dependency satisfaction/readiness
```

Current conformance answers whether evidence proves that dependency at today's `HEAD`. Dependency satisfaction/readiness answers whether downstream work may proceed. Those are different axes.

## Relationship to future readiness policy

TaskGraph currently documents:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
```

A future deterministic readiness policy may define additional prerequisite rules, but it must preserve this decision unless explicitly superseded: `needs_testing` alone must not revoke an already-integrated dependency or cascade-block downstream work.

## Scope

This ADR governs task selection, checkout/setup commands, generic retry behavior, human-directed implementation orchestration, and decomposition candidate reasoning. It does not automatically mark `needs_testing` tasks conformant, suppress their revalidation work, or authorize autonomous dispatch.
