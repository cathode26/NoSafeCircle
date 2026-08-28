"""Goal-oriented supervisor for taking one explicit NSC task to human Unity review."""

from .contracts import TASK_REVIEW_SCHEMA_VERSION
from .repository_scope import RepositoryScopeAuthority
from .mainline_reintegration import install_mainline_reintegration
from .downstream_resilience import install_downstream_resilience

# Install deterministic downstream extensions before run_pipeline_agent imports
# the controller and Codex action table. Both installers are idempotent and the
# resilience layer intentionally wraps the already-installed reintegration layer.
install_mainline_reintegration()
install_downstream_resilience()

__all__ = [
    "TASK_REVIEW_SCHEMA_VERSION",
    "RepositoryScopeAuthority",
    "install_mainline_reintegration",
    "install_downstream_resilience",
]
