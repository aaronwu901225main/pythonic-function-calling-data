import json
import sys
from typing import Any, Dict

from jsonschema import validate, Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "type": {"const": "object"},
                            "properties": {"type": "object"},
                            "required": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["type", "properties", "required"],
                        "additionalProperties": True,
                    },
                },
                "required": ["name", "parameters"],
                "additionalProperties": True,
            },
        },
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["user", "assistant", "tool"]},
                    "content": {"type": ["string", "null"]},
                    "tool_calls": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"const": "function"},
                                "function": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "arguments": {"type": "object"},
                                    },
                                    "required": ["name", "arguments"],
                                },
                            },
                            "required": ["type", "function"],
                        },
                    },
                },
                "required": ["role"],
                "additionalProperties": True,
                "allOf": [
                    {
                        "if": {"properties": {"role": {"const": "assistant"}}},
                        "then": {
                            "anyOf": [
                                {"required": ["content"]},
                                {"required": ["tool_calls"]},
                            ]
                        }
                    },
                    {
                        "if": {"properties": {"role": {"const": "user"}}},
                        "then": {"required": ["content"]}
                    },
                    {
                        "if": {"properties": {"role": {"const": "tool"}}},
                        "then": {"required": ["content"]}
                    }
                ],
            },
        },
        "label_kind": {"type": "string"},
    },
    "required": ["id", "tools", "messages", "label_kind"],
}


def main(path: str) -> int:
    validator = Draft202012Validator(SCHEMA)
    errors = 0
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Line {i}: Invalid JSON: {e}")
                errors += 1
                continue
            for err in sorted(validator.iter_errors(obj), key=str):
                print(f"Line {i}: {err.message}")
                errors += 1
    if errors == 0:
        print("Validation PASS: All lines conform to schema.")
        return 0
    else:
        print(f"Validation FAIL: {errors} issue(s) found.")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline/tools/validate_multi_turn_eng.py <path-to-jsonl>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
