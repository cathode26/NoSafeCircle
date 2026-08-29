"""Goal-oriented supervisor for taking one explicit NSC task to human Unity review."""

from .contracts import TASK_REVIEW_SCHEMA_VERSION
from .repository_scope import RepositoryScopeAuthority
from .mainline_reintegration import install_mainline_reintegration
from .downstream_resilience import install_downstream_resilience
from .downstream_determinism import install_downstream_determinism
from .operator_logging import install_operator_logging

# Install deterministic downstream extensions before run_pipeline_agent imports
# the controller and Codex action table. Resilience wraps reintegration;
# downstream determinism then restores durable event authority and narrows
# supervisor routing. Operator logging remains the outer presentation-only layer.
install_mainline_reintegration()
install_downstream_resilience()
install_downstream_determinism()
install_operator_logging()

__all__ = [
    "TASK_REVIEW_SCHEMA_VERSION",
    "RepositoryScopeAuthority",
    "install_mainline_reintegration",
    "install_downstream_resilience",
    "install_downstream_determinism",
    "install_operator_logging",
]
