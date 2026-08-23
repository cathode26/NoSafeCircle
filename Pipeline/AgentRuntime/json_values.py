"""Strict validation, freezing, and copying for JSON-compatible values."""

from __future__ import annotations

import math
from types import MappingProxyType
from typing import Any


class JsonValueError(ValueError):
    """Raised when a value cannot be represented by strict JSON."""


MAX_JSON_NESTING_DEPTH = 64


def validate_text(value: Any, *, path: str) -> str:
    """Require exact built-in text that can be emitted as UTF-8."""
    if type(value) is not str:
        raise JsonValueError(f"{path}: value must be built-in text")
    _validate_utf8(value, path=path)
    return value


def freeze_json(value: Any, *, path: str = "$") -> Any:
    """Freeze strict JSON, rejecting polymorphic containers, cycles, and excess depth."""
    return _freeze_json(value, path=path, depth=0, active=set())


def _freeze_json(value: Any, *, path: str, depth: int, active: set[int]) -> Any:
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        _validate_utf8(value, path=path)
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise JsonValueError(f"{path}: number must be finite")
        return value
    if type(value) in (list, tuple):
        return _freeze_container(
            value,
            path,
            depth,
            active,
            lambda: tuple(
                _freeze_json(
                    item,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                    active=active,
                )
                for index, item in enumerate(value)
            ),
        )
    if type(value) in (dict, MappingProxyType):
        def build() -> Any:
            frozen: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise JsonValueError(f"{path}: object keys must be built-in strings")
                _validate_utf8(key, path=f"{path} object key")
                frozen[key] = _freeze_json(
                    item,
                    path=f"{path}.{key}",
                    depth=depth + 1,
                    active=active,
                )
            return MappingProxyType(frozen)

        return _freeze_container(value, path, depth, active, build)
    raise JsonValueError(
        f"{path}: unsupported JSON value type {type(value).__name__}"
    )


def _freeze_container(
    value: Any,
    path: str,
    depth: int,
    active: set[int],
    build: Any,
) -> Any:
    if depth >= MAX_JSON_NESTING_DEPTH:
        raise JsonValueError(
            f"{path}: JSON nesting exceeds maximum depth {MAX_JSON_NESTING_DEPTH}"
        )
    identity = id(value)
    if identity in active:
        raise JsonValueError(f"{path}: cyclic JSON value")
    active.add(identity)
    try:
        return build()
    except JsonValueError:
        raise
    except Exception as exc:
        raise JsonValueError(
            f"{path}: JSON container could not be read safely: {type(exc).__name__}"
        ) from exc
    finally:
        active.remove(identity)


def thaw_json(value: Any) -> Any:
    """Return a detached, mutable JSON-compatible copy of a frozen value."""
    return _thaw_json(value, path="$", depth=0, active=set())


def _thaw_json(value: Any, *, path: str, depth: int, active: set[int]) -> Any:
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        _validate_utf8(value, path=path)
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise JsonValueError(f"{path}: number must be finite")
        return value
    if type(value) in (list, tuple):
        return _freeze_container(
            value,
            path,
            depth,
            active,
            lambda: [
                _thaw_json(
                    item,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                    active=active,
                )
                for index, item in enumerate(value)
            ],
        )
    if type(value) in (dict, MappingProxyType):
        def build() -> Any:
            result: dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise JsonValueError(f"{path}: object keys must be built-in strings")
                _validate_utf8(key, path=f"{path} object key")
                result[key] = _thaw_json(
                    item,
                    path=f"{path}.{key}",
                    depth=depth + 1,
                    active=active,
                )
            return result

        return _freeze_container(value, path, depth, active, build)
    raise JsonValueError(
        f"cannot thaw unsupported value type {type(value).__name__}"
    )


def validate_json(value: Any, *, path: str = "$") -> None:
    """Validate a value as strict JSON without retaining it."""
    freeze_json(value, path=path)


def _validate_utf8(value: str, *, path: str) -> None:
    try:
        str.encode(value, "utf-8")
    except UnicodeEncodeError as exc:
        raise JsonValueError(f"{path}: string must be valid UTF-8") from exc
