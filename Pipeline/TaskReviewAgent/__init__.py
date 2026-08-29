"""Goal-oriented supervisor for taking one explicit NSC task to human Unity review."""

from . import codex_supervisor as _codex_supervisor
from .contracts import TASK_REVIEW_SCHEMA_VERSION
from .repository_scope import RepositoryScopeAuthority
from .mainline_reintegration import install_mainline_reintegration
from .downstream_resilience import install_downstream_resilience
from . import downstream_determinism as _downstream_determinism
from .downstream_determinism import install_downstream_determinism
from .downstream_action_grounding import install_downstream_action_grounding
from .operator_logging import install_operator_logging
from .git_identity_guard import install_git_identity_guard

# Install deterministic downstream extensions before run_pipeline_agent imports
# the controller and Codex action table. Resilience wraps reintegration;
# downstream determinism restores durable event authority and narrows routing;
# action grounding supplies exact host-verified proposal identities. Operator
# logging remains the outer presentation-only layer. Git identity safety is
# installed last so every automated commit path uses a non-attributable address.
install_mainline_reintegration()
install_downstream_resilience()
install_downstream_determinism()

# The shared AgentRuntime intentionally supports a small JSON-Schema subset and
# OpenAI Structured Outputs does not need to carry general search-content
# constraints. Keep nonblank strings/arrays and nonempty prefixes enforced by
# the patched host argument validator and downstream controller instead of
# emitting unsupported minLength/minItems schema keywords. The action-grounding
# layer may still add supported enum constraints for one exact proposal turn.
_codex_supervisor.decision_schema = _downstream_determinism._ORIGINALS[
    "decision_schema"
]

install_downstream_action_grounding()
install_operator_logging()
install_git_identity_guard()

__all__ = [
    "TASK_REVIEW_SCHEMA_VERSION",
    "RepositoryScopeAuthority",
    "install_mainline_reintegration",
    "install_downstream_resilience",
    "install_downstream_determinism",
    "install_downstream_action_grounding",
    "install_operator_logging",
    "install_git_identity_guard",
]
