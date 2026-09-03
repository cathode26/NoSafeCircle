"""Canonical repository-scope facade with revision-qualified Git search parsing."""

from __future__ import annotations

from typing import Any, Iterable

from .pipeline_scope import (
    AcceptedExecutionScope,
    RepositoryScopeAuthority as _RepositoryScopeAuthority,
    RepositoryScopeError,
    SCOPE_SCHEMA_VERSION,
    _READ_PREFIXES,
    _decode,
    _git,
    _repo_path,
    _under,
)


class RepositoryScopeAuthority(_RepositoryScopeAuthority):
    """Repository scope authority with correct `git grep HEAD` result parsing."""

    def list_files(
        self,
        *,
        prefix: str = "Assets/",
        limit: int = 200,
    ) -> dict[str, Any]:
        if not isinstance(prefix, str) or prefix.strip() not in (".", "./"):
            return super().list_files(prefix=prefix, limit=limit)
        self._assert_checkout()
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise RepositoryScopeError("file-list limit must be from 1 through 1000")
        paths = [path for path in self._tracked() if _under(path, _READ_PREFIXES)]
        return {
            "prefix": ".",
            "count": min(len(paths), limit),
            "truncated": len(paths) > limit,
            "paths": paths[:limit],
        }

    def search(
        self,
        *,
        query: str,
        prefixes: Iterable[str] = ("Assets/",),
        limit: int = 80,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if type(query) is not str or not query.strip() or len(query) > 160:
            raise RepositoryScopeError("search query must be 1 through 160 characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in query):
            raise RepositoryScopeError("search query contains a control character")
        if type(limit) is not int or not 1 <= limit <= 300:
            raise RepositoryScopeError("search limit must be from 1 through 300")
        normalized_prefixes: list[str] = []
        for item in prefixes:
            if isinstance(item, str) and item.strip() in (".", "./"):
                normalized_prefixes.extend(_READ_PREFIXES)
                continue
            path = _repo_path(item, field="search prefix")
            check_path = path if path.endswith("/") else path + "/"
            if not _under(check_path, _READ_PREFIXES):
                raise RepositoryScopeError(f"search prefix is outside approved roots: {path}")
            normalized_prefixes.append(path)
        normalized_prefixes = list(dict.fromkeys(normalized_prefixes))
        result = _git(
            self.checkout,
            "grep",
            "-n",
            "-I",
            "-F",
            "--",
            query,
            "HEAD",
            "--",
            *normalized_prefixes,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise RepositoryScopeError("git grep failed while searching the task checkout")
        matches: list[dict[str, Any]] = []
        for line in _decode(result.stdout, label="git grep output").splitlines():
            rendered = line[5:] if line.startswith("HEAD:") else line
            try:
                path, line_number, text = rendered.split(":", 2)
                matches.append(
                    {
                        "path": path,
                        "line": int(line_number),
                        "text": text[:500],
                    }
                )
            except (ValueError, TypeError):
                continue
            if len(matches) >= limit:
                break
        return {
            "query": query,
            "prefixes": normalized_prefixes,
            "count": len(matches),
            "truncated": len(matches) >= limit,
            "matches": matches,
        }


# TaskReviewAgent modules created before this facade imported the original class directly.
# Install the corrected method on that class so all existing call sites receive the same
# deterministic search behavior without widening the read authority.
_RepositoryScopeAuthority.list_files = RepositoryScopeAuthority.list_files
_RepositoryScopeAuthority.search = RepositoryScopeAuthority.search


__all__ = (
    "AcceptedExecutionScope",
    "RepositoryScopeAuthority",
    "RepositoryScopeError",
    "SCOPE_SCHEMA_VERSION",
)
