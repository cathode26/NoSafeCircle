"""Process-scoped authority for disposable synthetic component fixtures only.

Production ships with an empty allowlist. Tests explicitly enter this context
to exercise the protocol with invented repository identities. There is no
environment variable, persisted policy, or production entry point for this seam.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import sys
from types import ModuleType
from unittest.mock import patch

FIXTURE_REPOSITORY = "fixture-owner/pipeline-rehearsal"
FIXTURE_REPOSITORIES = frozenset((FIXTURE_REPOSITORY, "fixture-owner/agent-rehearsal"))


@contextmanager
def synthetic_fixture_authority():
    # Load all direct consumers before patching their imported constant copies.
    from Pipeline.TaskReviewAgent import issue_workflow, prepare_synthetic_gauntlet
    from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver

    replacements = {
        "AUTOMATED_VALIDATION_REPOSITORY": FIXTURE_REPOSITORY,
        "AUTOMATED_VALIDATION_REPOSITORIES": FIXTURE_REPOSITORIES,
        "PRIVATE_REPOSITORY": FIXTURE_REPOSITORY,
    }
    originals = {
        "AUTOMATED_VALIDATION_REPOSITORY": issue_workflow.AUTOMATED_VALIDATION_REPOSITORY,
        "AUTOMATED_VALIDATION_REPOSITORIES": issue_workflow.AUTOMATED_VALIDATION_REPOSITORIES,
        "PRIVATE_REPOSITORY": prepare_synthetic_gauntlet.PRIVATE_REPOSITORY,
    }
    modules_before = set(sys.modules)
    with ExitStack() as stack:
        for name, module in tuple(sys.modules.items()):
            if not isinstance(module, ModuleType):
                continue
            if name != "__main__" and not name.startswith(("Pipeline.", "TaskReviewAgent.")):
                continue
            for attribute, value in replacements.items():
                if attribute in vars(module):
                    stack.enter_context(patch.object(module, attribute, value))
        try:
            yield
        finally:
            # Modules imported during the fixture may have copied a constant;
            # restore those copies too before returning to public assertions.
            for name in set(sys.modules).difference(modules_before):
                module = sys.modules.get(name)
                if not isinstance(module, ModuleType) or not name.startswith(("Pipeline.", "TaskReviewAgent.")):
                    continue
                for attribute, value in replacements.items():
                    if vars(module).get(attribute) == value:
                        setattr(module, attribute, originals[attribute])


def run_with_synthetic_authority(action, *args, **kwargs):
    with synthetic_fixture_authority():
        return action(*args, **kwargs)
