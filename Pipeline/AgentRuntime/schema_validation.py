"""A deliberately small, fail-closed JSON Schema subset."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .json_values import JsonValueError, freeze_json

SUPPORTED_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
SUPPORTED_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "minimum", "maximum",
}


class SchemaValidationError(ValueError):
    pass


def _schema_types(kind: Any, path: str) -> tuple[tuple[str, ...], str]:
    if type(kind) is str:
        if kind not in SUPPORTED_TYPES:
            raise SchemaValidationError(f"{path}: a supported type is required")
        return (kind,), kind
    if type(kind) is tuple:
        if (
            len(kind) != 2
            or any(type(item) is not str for item in kind)
            or len(set(kind)) != len(kind)
            or "null" not in kind
        ):
            raise SchemaValidationError(
                f"{path}: type array must contain null and one unique supported non-null type"
            )
        non_null = next(item for item in kind if item != "null")
        if non_null not in SUPPORTED_TYPES - {"null"}:
            raise SchemaValidationError(
                f"{path}: type array must contain null and one unique supported non-null type"
            )
        return kind, non_null
    raise SchemaValidationError(f"{path}: a supported type is required")


def _matches_type(value: Any, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, Mapping)
    if kind == "array":
        return isinstance(value, (list, tuple))
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
    if kind == "boolean":
        return isinstance(value, bool)
    return value is None


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    return type(left) is type(right) and left == right


def validate_schema(schema: Any, path: str = "$") -> None:
    try:
        snapshot = freeze_json(schema, path=path)
    except JsonValueError as exc:
        raise SchemaValidationError(str(exc)) from exc
    _validate_schema(snapshot, path)


def _validate_schema(schema: Any, path: str) -> None:
    if not isinstance(schema, Mapping):
        raise SchemaValidationError(f"{path}: schema must be an object")
    unknown = set(schema) - SUPPORTED_KEYWORDS
    if unknown:
        raise SchemaValidationError(f"{path}: unsupported schema keywords: {sorted(unknown)}")
    kinds, kind = _schema_types(schema.get("type"), path)
    for keyword in ("minimum", "maximum"):
        if keyword in schema:
            bound = schema[keyword]
            if kind not in {"integer", "number"}:
                raise SchemaValidationError(
                    f"{path}: {keyword} requires integer or number type"
                )
            if isinstance(bound, bool) or not isinstance(bound, (int, float)):
                raise SchemaValidationError(
                    f"{path}: {keyword} must be a finite JSON number"
                )
            if isinstance(bound, float) and not math.isfinite(bound):
                raise SchemaValidationError(
                    f"{path}: {keyword} must be a finite JSON number"
                )
    if (
        "minimum" in schema
        and "maximum" in schema
        and schema["minimum"] > schema["maximum"]
    ):
        raise SchemaValidationError(f"{path}: minimum may not exceed maximum")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, (list, tuple)) or not enum:
            raise SchemaValidationError(f"{path}: enum must be a non-empty array")
        prior_values: list[Any] = []
        for index, item in enumerate(enum):
            try:
                freeze_json(item, path=f"{path}.enum[{index}]")
            except JsonValueError as exc:
                raise SchemaValidationError(str(exc)) from exc
            if not any(_matches_type(item, candidate) for candidate in kinds):
                declared = kind if len(kinds) == 1 else list(kinds)
                raise SchemaValidationError(
                    f"{path}: enum value at index {index} is incompatible with {declared}"
                )
            if any(_json_equal(item, prior) for prior in prior_values):
                raise SchemaValidationError(
                    f"{path}: enum contains duplicate JSON values"
                )
            prior_values.append(item)
    if kind == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping) or any(
            not isinstance(k, str) for k in properties
        ):
            raise SchemaValidationError(f"{path}: properties must be an object")
        for key, child in properties.items():
            _validate_schema(child, f"{path}.{key}")
        required = schema.get("required", [])
        if (
            not isinstance(required, (list, tuple))
            or any(not isinstance(x, str) for x in required)
            or len(set(required)) != len(required)
        ):
            raise SchemaValidationError(
                f"{path}: required must contain unique strings"
            )
        if any(x not in properties for x in required):
            raise SchemaValidationError(
                f"{path}: required names must exist in properties"
            )
        if not isinstance(schema.get("additionalProperties", True), bool):
            raise SchemaValidationError(
                f"{path}: additionalProperties must be boolean"
            )
    elif any(k in schema for k in ("properties", "required", "additionalProperties")):
        raise SchemaValidationError(f"{path}: object keywords require object type")
    if kind == "array":
        if "items" not in schema:
            raise SchemaValidationError(f"{path}: array items is required")
        _validate_schema(schema["items"], f"{path}[]")
    elif "items" in schema:
        raise SchemaValidationError(f"{path}: items requires array type")


def validate_instance(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    try:
        value_snapshot = freeze_json(value, path=path)
        schema_snapshot = freeze_json(schema, path=path)
    except JsonValueError as exc:
        raise SchemaValidationError(str(exc)) from exc
    _validate_schema(schema_snapshot, path)
    _validate_instance(value_snapshot, schema_snapshot, path)


def _validate_instance(value: Any, schema: Mapping[str, Any], path: str) -> None:
    kinds, kind = _schema_types(schema["type"], path)
    if not any(_matches_type(value, candidate) for candidate in kinds):
        expected = kinds[0] if len(kinds) == 1 else list(kinds)
        raise SchemaValidationError(f"{path}: expected {expected}")
    if "enum" in schema and not any(
        _json_equal(value, item) for item in schema["enum"]
    ):
        raise SchemaValidationError(f"{path}: value is not in enum")
    if value is None and len(kinds) == 2:
        return
    if kind in {"integer", "number"}:
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path}: value is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path}: value is above maximum")
    if kind == "object":
        for name in schema.get("required", []):
            if name not in value:
                raise SchemaValidationError(
                    f"{path}: missing required property {name}"
                )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties", True) is False:
            extra = set(value) - set(properties)
            if extra:
                raise SchemaValidationError(
                    f"{path}: additional properties: {sorted(extra)}"
                )
        for name, child in properties.items():
            if name in value:
                _validate_instance(value[name], child, f"{path}.{name}")
    elif kind == "array":
        for index, item in enumerate(value):
            _validate_instance(item, schema["items"], f"{path}[{index}]")
