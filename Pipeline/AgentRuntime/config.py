"""Strict provider-neutral runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .contracts import MODEL_CAPABILITY_CLASSES, ContractValidationError
from .json_values import JsonValueError, freeze_json, thaw_json, validate_text

_CONFIG_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*$")


@dataclass(frozen=True)
class ProviderSelection:
    provider: str
    model: str


@dataclass(frozen=True)
class RuntimeConfiguration:
    provider_configurations: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        if not isinstance(self.provider_configurations, Mapping):
            raise ContractValidationError(
                "provider_configurations must be an object"
            )
        try:
            detached = thaw_json(self.provider_configurations)
        except JsonValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        if not detached:
            raise ContractValidationError(
                "provider configuration set must not be empty"
            )
        for key, entry in detached.items():
            if (
                not isinstance(key, str)
                or not _CONFIG_IDENTIFIER.fullmatch(key)
                or not isinstance(entry, dict)
                or set(entry) != {"provider", "models"}
            ):
                raise ContractValidationError("invalid provider configuration entry")
            models = entry["models"]
            if (
                not isinstance(entry["provider"], str)
                or not _CONFIG_IDENTIFIER.fullmatch(entry["provider"])
                or not isinstance(models, dict)
                or set(models) != MODEL_CAPABILITY_CLASSES
            ):
                raise ContractValidationError(
                    "provider configuration requires exactly all "
                    "capability-class mappings"
                )
            for model in models.values():
                if (
                    not isinstance(model, str)
                    or not model
                    or model != model.strip()
                ):
                    raise ContractValidationError(
                        "model identifiers must be non-empty and already trimmed"
                    )
                try:
                    validate_text(model, path="model identifier")
                except JsonValueError as exc:
                    raise ContractValidationError(
                        "model identifiers must be valid UTF-8"
                    ) from exc
        try:
            frozen = freeze_json(detached, path="$.provider_configurations")
        except JsonValueError as exc:
            raise ContractValidationError(str(exc)) from exc
        object.__setattr__(self, "provider_configurations", frozen)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeConfiguration":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "provider_configurations",
        }:
            raise ContractValidationError(
                "configuration has missing or unsupported fields"
            )
        if (
            value["schema_version"] != "1.0"
            or not isinstance(value["provider_configurations"], dict)
        ):
            raise ContractValidationError("invalid configuration schema")
        return cls(value["provider_configurations"])

    @classmethod
    def load(cls, path: Path) -> "RuntimeConfiguration":
        def reject_constant(value: str) -> None:
            raise ContractValidationError(f"invalid JSON constant: {value}")

        def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ContractValidationError(f"duplicate JSON object key: {key}")
                result[key] = value
            return result

        try:
            value = json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=reject_constant,
                object_pairs_hook=reject_duplicates,
            )
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise ContractValidationError("invalid configuration JSON") from exc
        return cls.from_dict(value)

    def resolve(
        self,
        key: str,
        capability_class: str,
        registry: Mapping[str, Any],
    ) -> ProviderSelection:
        if key not in self.provider_configurations:
            raise ContractValidationError("unknown provider configuration")
        entry = self.provider_configurations[key]
        provider = entry["provider"]
        if provider not in registry:
            raise ContractValidationError("unknown provider registry entry")
        if capability_class not in entry["models"]:
            raise ContractValidationError("missing configured capability mapping")
        return ProviderSelection(provider, entry["models"][capability_class])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "provider_configurations": thaw_json(self.provider_configurations),
        }
