"""Goal-oriented supervisor for taking one explicit NSC task to human Unity review."""

from .contracts import TASK_REVIEW_SCHEMA_VERSION
from .repository_scope import RepositoryScopeAuthority
from .mainline_reintegration import install_mainline_reintegration

# Install the deterministic downstream transition before run_pipeline_agent imports
# the controller and Codex action table. The installer is idempotent.
install_mainline_reintegration()

__all__ = [
    "TASK_REVIEW_SCHEMA_VERSION",
    "RepositoryScopeAuthority",
    "install_mainline_reintegration",
]
