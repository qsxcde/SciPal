"""Export the FastAPI schema to contracts/openapi.json.

The file is the single source of truth for the REST contract: the frontend
generates its types from it, and CI fails when the committed copy is stale.
"""

import json
from pathlib import Path

SSE_EVENT_MODELS = (
    "ChatStreamStatusEvent",
    "ChatStreamTokenEvent",
    "ChatStreamSourcesEvent",
    "ChatStreamWarningEvent",
    "ChatStreamErrorEvent",
    "ChatStreamDoneEvent",
)


def contracts_dir() -> Path:
    """Repository-level contracts directory (sibling of backend/ and frontend/)."""
    return Path(__file__).resolve().parents[4] / "contracts"


def _attach_sse_events(schema: dict) -> None:
    """Add the SSE payload models to components.

    Streaming responses do not appear in OpenAPI, so without this the event
    union would never reach the generated TypeScript types.
    """
    from backend.api import schemas

    components = schema.setdefault("components", {}).setdefault("schemas", {})
    refs = []
    for name in SSE_EVENT_MODELS:
        model = getattr(schemas, name)
        model_schema = model.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        for definition_name, definition in model_schema.pop("$defs", {}).items():
            components.setdefault(definition_name, definition)
        components[name] = model_schema
        refs.append({"$ref": f"#/components/schemas/{name}"})
    components["ChatStreamEvent"] = {
        "title": "ChatStreamEvent",
        "oneOf": refs,
    }


def build_schema() -> dict:
    """Build the contract exactly as it is committed."""
    from backend.main import app

    schema = app.openapi()
    _attach_sse_events(schema)
    return schema


def export() -> Path:
    schema = build_schema()
    target = contracts_dir() / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> None:
    target = export()
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
