"""Check every request the tools send against Beds24's published OpenAPI spec.

Catches endpoints, query parameters and body fields that Beds24 does not define,
and values of the wrong type or outside an allowed list.
"""

from pathlib import Path
from typing import Any

import httpx
import jsonschema
import pytest
import yaml
from conftest import TOOL_ARGS, call

SPEC_URL = "https://beds24.com/api/v2/apiV2.yaml"
SPEC_CACHE = Path(__file__).parent / ".cache" / "apiV2.yaml"


@pytest.fixture(scope="session")
def spec() -> dict[str, Any]:
    if not SPEC_CACHE.exists():
        response = httpx.get(SPEC_URL, timeout=30, follow_redirects=True)
        response.raise_for_status()
        SPEC_CACHE.parent.mkdir(exist_ok=True)
        SPEC_CACHE.write_text(response.text)
    return yaml.safe_load(SPEC_CACHE.read_text())


def resolve(spec: dict[str, Any], node: Any) -> Any:
    """Follow $ref links and merge allOf, recursively, into one plain schema."""
    if isinstance(node, list):
        return [resolve(spec, item) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target: Any = spec
        for part in node["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return resolve(spec, target)
    node = {key: resolve(spec, value) for key, value in node.items()}
    if "allOf" in node:
        merged: dict[str, Any] = {"properties": {}}
        for part in node.pop("allOf"):
            merged["properties"].update(part.get("properties", {}))
            merged.update({k: v for k, v in part.items() if k != "properties"})
        merged["properties"].update(node.pop("properties", {}))
        node = {**merged, **node}
    return node


def unknown_fields(schema: dict[str, Any], value: Any, path: str = "") -> list[str]:
    """Field paths in value that the schema does not define."""
    if isinstance(value, list):
        items = schema.get("items", {})
        return [f for v in value for f in unknown_fields(items, v, path + "[]")]
    if not isinstance(value, dict) or "properties" not in schema:
        return []
    found = []
    for key, item in value.items():
        if key not in schema["properties"]:
            found.append(f"{path}{key}")
        else:
            found += unknown_fields(schema["properties"][key], item, f"{path}{key}.")
    return found


def operation(spec: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    path = spec["paths"].get(request["endpoint"])
    assert path, f"{request['endpoint']} is not a Beds24 endpoint"
    assert request["method"] in path, f"Beds24 has no {request['method'].upper()} {request['endpoint']}"
    return resolve(spec, path[request["method"]])


# Mismatches with the spec that are known and not yet fixed. Each one fails the test if it gets fixed,
# so this list has to be kept up to date.
KNOWN_MISMATCHES: dict[str, str] = {
    # The spec's POST /bookings schema marks roomId etc. required, but that applies to NEW bookings;
    # existing bookings are changed by sending "id" plus only the fields to change. Field names for
    # these two are checked against the spec in tests/test_bookings.py instead.
    "update_booking": "partial update by id; schema's required fields only apply to new bookings",
    "cancel_booking": "partial update by id; schema's required fields only apply to new bookings",
    "send_message": "sends subject, which POST /bookings/messages does not define",
}


@pytest.mark.parametrize("tool", TOOL_ARGS)
async def test_requests_match_beds24_spec(
    mcp: Any, beds24: Any, spec: dict[str, Any], tool: str, request: pytest.FixtureRequest
) -> None:
    if tool in KNOWN_MISMATCHES:
        request.applymarker(pytest.mark.xfail(reason=KNOWN_MISMATCHES[tool], strict=True))

    await call(mcp, tool, TOOL_ARGS[tool])
    assert beds24.requests, f"{tool} made no request"

    problems = []
    for sent in beds24.requests:
        op = operation(spec, sent)
        where = f"{sent['method'].upper()} {sent['endpoint']}"
        if sent["method"] == "get":
            allowed = {p["name"]: p.get("schema", {}) for p in op.get("parameters", [])}
            for name, value in sent["params"].items():
                if name not in allowed:
                    problems.append(f"{where}: unknown query parameter {name!r}")
                    continue
                schema = allowed[name]
                if schema.get("type") == "array":
                    schema = schema.get("items", {})
                if schema.get("type") == "boolean" and isinstance(value, bool):
                    continue
                if "enum" in schema and value not in schema["enum"]:
                    problems.append(f"{where}: {name}={value!r} not one of {schema['enum']}")
        else:
            schema = op["requestBody"]["content"]["application/json"]["schema"]
            problems += [f"{where}: unknown body field {f!r}" for f in unknown_fields(schema, sent["body"])]
            try:
                jsonschema.validate(sent["body"], schema)
            except jsonschema.ValidationError as error:
                problems.append(f"{where}: {error.message} at {list(error.absolute_path)}")

    assert not problems, "\n".join(problems)
