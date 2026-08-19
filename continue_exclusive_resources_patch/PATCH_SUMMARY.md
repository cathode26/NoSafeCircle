# Exclusive Resources — Partial Patch Recovery

The original exclusive-resources patch stopped after successfully modifying:

- `reconciliation_agent.py`
- `prompts/reconcile.md`
- `verification_crew.py`

It failed because the first `structure_auditor.md` text anchor was too brittle.

This continuation script does not revert the successfully applied work. It
patches only the remaining verification prompts, smoke tests, and README, using
smaller anchors, then verifies that all core and continuation markers are
present.

After applying it, run:

docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py
