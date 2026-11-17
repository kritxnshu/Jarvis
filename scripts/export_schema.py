"""Export the backend's API models as one JSON Schema document (input to TS generation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from jarvis.api.schemas import (
    ErrorResponse,
    HealthResponse,
    Setting,
    SettingsResponse,
    SettingUpdate,
)
from jarvis.events import EventEnvelope

# Models the backend sends: every field is always present, so all are required in TS.
OUTPUT_MODELS: tuple[type[BaseModel], ...] = (
    ErrorResponse,
    HealthResponse,
    Setting,
    SettingsResponse,
    EventEnvelope,
)
# Models the UI sends.
INPUT_MODELS: tuple[type[BaseModel], ...] = (SettingUpdate,)

_SCHEMA_KEYS = {"type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const", "items"}


def _clean_property(prop: dict[str, Any]) -> dict[str, Any]:
    prop = {k: v for k, v in prop.items() if k != "title"}  # titles become noisy TS aliases
    if not _SCHEMA_KEYS & prop.keys():
        prop["tsType"] = "unknown"  # pydantic `Any`
    if prop.get("type") == "object" and "properties" not in prop:
        extra = prop.get("additionalProperties")
        if extra is True or extra is None or extra == {}:
            prop["tsType"] = "Record<string, unknown>"
    if isinstance(prop.get("items"), dict):
        prop["items"] = _clean_property(prop["items"])
    for key in ("anyOf", "oneOf"):
        if key in prop:
            prop[key] = [_clean_property(p) for p in prop[key]]
    return prop


def _clean_model(schema: dict[str, Any], all_required: bool) -> dict[str, Any]:
    props: dict[str, Any] = schema.get("properties", {})
    schema["properties"] = {name: _clean_property(p) for name, p in props.items()}
    if all_required:
        schema["required"] = sorted(props)
    schema["additionalProperties"] = False
    return schema


def build_schema() -> dict[str, Any]:
    defs: dict[str, Any] = {}
    for models, all_required in ((OUTPUT_MODELS, True), (INPUT_MODELS, False)):
        for model in models:
            mode = "serialization" if all_required else "validation"
            schema = model.model_json_schema(ref_template="#/$defs/{model}", mode=mode)
            for name, sub in schema.pop("$defs", {}).items():
                defs[name] = _clean_model(sub, all_required)
            defs[model.__name__] = _clean_model(schema, all_required)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "JarvisContracts",
        "type": "object",
        "properties": {name: {"$ref": f"#/$defs/{name}"} for name in sorted(defs)},
        "$defs": dict(sorted(defs.items())),
    }


def main() -> int:
    out = Path(sys.argv[1])
    out.write_text(json.dumps(build_schema(), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
