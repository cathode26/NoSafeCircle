"""Dependency-neutral ExecutionCrew role capability identities.

The host session owner and the crew runner both need these immutable mappings.
Keeping them outside ``run_crew`` prevents importing the TaskReviewAgent package
from recursively importing a partially initialized crew runner.
"""

from __future__ import annotations


ROLE_CAPABILITY_CLASSES = {
    "contract_locality_auditor": "high_reasoning",
    "implementer": "standard",
    "test_author": "low_cost",
    "validator": "high_reasoning",
}

PROFILE_ROLE_CAPABILITY_CLASSES = {
    **ROLE_CAPABILITY_CLASSES,
    "lead_developer": "high_reasoning",
}


__all__ = ["ROLE_CAPABILITY_CLASSES", "PROFILE_ROLE_CAPABILITY_CLASSES"]
