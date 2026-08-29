from __future__ import annotations

"""Migration-aware Git object access for immutable TaskGraph evidence."""

from pathlib import Path

try:
    from conformance_records import ConformanceRecordError, GitRepository
    from history_identity_migrations import (
        HistoryIdentityMigrationError,
        HistoryIdentityMigrationResolver,
    )
except ImportError:  # pragma: no cover - package import compatibility
    from .conformance_records import ConformanceRecordError, GitRepository
    from .history_identity_migrations import (
        HistoryIdentityMigrationError,
        HistoryIdentityMigrationResolver,
    )


class HistoryAwareGitRepository(GitRepository):
    """Resolve exact old commit IDs through approved tree-preserving migrations."""

    def __init__(self, root: Path | str) -> None:
        super().__init__(root)
        try:
            self.history_identity = HistoryIdentityMigrationResolver(
                self.root,
                super().head(),
            )
        except HistoryIdentityMigrationError as exc:
            raise ConformanceRecordError(
                f"invalid repository history identity migration: {exc}"
            ) from exc

    def resolve_commit(self, commit: str) -> str:
        return self.history_identity.resolve(commit)

    def tree(self, commit: str) -> str:
        return super().tree(self.resolve_commit(commit))

    def read(self, commit: str, path: str) -> bytes:
        return super().read(self.resolve_commit(commit), path)

    def blob(self, commit: str, path: str) -> str:
        return super().blob(self.resolve_commit(commit), path)

    def exists(self, commit: str, path: str) -> bool:
        return super().exists(self.resolve_commit(commit), path)

    def files(self, commit: str, prefix: str) -> list[str]:
        return super().files(self.resolve_commit(commit), prefix)

    def is_ancestor(self, older: str, newer: str) -> bool:
        return super().is_ancestor(
            self.resolve_commit(older),
            self.resolve_commit(newer),
        )

    def path_history(self, commit: str, path: str) -> list[str]:
        return super().path_history(self.resolve_commit(commit), path)
