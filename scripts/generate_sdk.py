"""根据 openapi.json 生成 SDK 方法元数据。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "openapi.json"
OUTPUT_PATH = ROOT / "src" / "shunplus" / "_generated.py"


def main() -> None:
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    endpoints = _collect_endpoints(spec)
    OUTPUT_PATH.write_text(_render(endpoints), encoding="utf-8")


def _collect_endpoints(spec: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for path, path_item in spec.get("paths", {}).items():
        for http_method, operation in path_item.items():
            sdk_method = operation.get("x-sdk-method") or operation.get("operationId")
            if not sdk_method:
                continue
            endpoints.append(
                {
                    "name": sdk_method,
                    "operation_id": operation.get("operationId"),
                    "http_method": http_method.upper(),
                    "path": path,
                    "summary": operation.get("summary", ""),
                    "description": operation.get("description", ""),
                    "tags": operation.get("tags", []),
                    "parameters": operation.get("parameters", []),
                    "response_kind": _response_kind(operation),
                    "fields": operation.get("x-finhub-fields", []),
                    "field_variants": operation.get("x-finhub-field-variants", {}),
                }
            )
    return sorted(endpoints, key=lambda item: item["name"])


def _render(endpoints: list[dict[str, Any]]) -> str:
    lines = [
        '"""由 scripts/generate_sdk.py 根据 openapi.json 生成，请勿手工修改。"""',
        "# ruff: noqa: E501",
        "",
        "from __future__ import annotations",
        "",
        "import json",
        "from typing import Any, List, Optional, Tuple, Union",
        "",
        "from ._types import DateLike, ResultFormat",
        "",
        "ENDPOINTS = json.loads(",
        f"    {_json_endpoints(endpoints)!r}",
        ")",
        "",
        "ENDPOINT_ALIASES = {",
    ]
    for endpoint in endpoints:
        if endpoint["operation_id"] and endpoint["operation_id"] != endpoint["name"]:
            lines.append(f'    "{endpoint["operation_id"]}": "{endpoint["name"]}",')
    lines.append("}")
    lines.extend(
        [
            "",
            "",
            "class GeneratedDataMethods:",
            '    """由 OpenAPI 生成的数据查询方法。"""',
            "",
        ]
    )
    for endpoint in endpoints:
        lines.extend(_render_method(endpoint))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _json_endpoints(endpoints: list[dict[str, Any]]) -> str:
    compact: dict[str, dict[str, Any]] = {}
    for endpoint in endpoints:
        compact[endpoint["name"]] = {
            "operation_id": endpoint["operation_id"],
            "http_method": endpoint["http_method"],
            "path": endpoint["path"],
            "summary": endpoint["summary"],
            "description": endpoint["description"],
            "tags": endpoint["tags"],
            "parameters": [
                {
                    "name": param.get("name"),
                    "required": param.get("required", False),
                    "description": param.get("description", ""),
                    "schema": param.get("schema", {}),
                }
                for param in endpoint["parameters"]
            ],
            "response_kind": endpoint["response_kind"],
            "fields": endpoint["fields"],
            "field_variants": endpoint["field_variants"],
        }
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def _render_method(endpoint: dict[str, Any]) -> list[str]:
    params = endpoint["parameters"]
    signature_parts = ["self"]
    if params:
        signature_parts.append("*")
    call_parts: list[str] = []
    for param in params:
        name = param["name"]
        annotation = _annotation(param.get("schema", {}), required=param.get("required", False))
        default = _default(param)
        signature_parts.append(f"{name}: {annotation}{default}")
        call_parts.append(f'"{name}": {name}')
    if endpoint["response_kind"] == "table":
        signature_parts.append("fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None")
        signature_parts.append("format: Optional[ResultFormat] = None")
    signature = ", ".join(signature_parts)

    method_lines = [
        f"    def {endpoint['name']}({signature}) -> Any:",
        f'        """{_doc(endpoint)}"""',
        "",
        "        params = {",
    ]
    for call_part in call_parts:
        method_lines.append(f"            {call_part},")
    method_lines.extend(
        [
            "        }",
        ]
    )
    if endpoint["response_kind"] == "table":
        method_lines.append(
            f'        return self.query("{endpoint["name"]}", '
            "fields=fields, format=format, **params)"
        )
    else:
        method_lines.append(f'        return self.request_json("{endpoint["name"]}", **params)')
    return method_lines


def _response_kind(operation: dict[str, Any]) -> str:
    if operation.get("x-finhub-fields") is not None:
        return "table"

    responses = operation.get("responses", {})
    success = responses.get("200", {})
    content = success.get("content", {})
    schema = content.get("application/json", {}).get("schema", {})
    if schema.get("$ref", "").endswith("/DataApiTableResponse"):
        return "table"
    return "json"


def _annotation(schema: dict[str, Any], *, required: bool) -> str:
    def optional(annotation: str) -> str:
        return annotation if required else f"Optional[{annotation}]"

    schema_type = schema.get("type")
    if schema.get("format") == "date-time":
        return "Optional[DateLike]"
    enum = schema.get("enum")
    if enum:
        return "str"
    if schema_type == "integer":
        return optional("int")
    if schema_type == "number":
        return optional("float")
    if schema_type == "boolean":
        return optional("bool")
    if schema_type == "string":
        return optional("str")
    for item in schema.get("anyOf", []):
        if item.get("format") == "date-time":
            return "Optional[DateLike]"
        if item.get("type") == "integer":
            return optional("int")
        if item.get("type") == "boolean":
            return optional("bool")
    return "Any"


def _default(param: dict[str, Any]) -> str:
    if param.get("required"):
        return ""
    if param.get("name") == "limit":
        return " = None"
    schema = param.get("schema", {})
    if "default" in schema:
        return f" = {schema['default']!r}"
    return " = None"


def _doc(endpoint: dict[str, Any]) -> str:
    summary = endpoint["summary"].strip()
    description = endpoint["description"].strip()
    if summary and description and summary != description:
        return f"{summary}\\n\\n{description}"
    return summary or description or endpoint["name"]


if __name__ == "__main__":
    main()
