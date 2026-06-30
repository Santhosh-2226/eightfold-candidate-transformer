"""
Schema Validation (final stage).
Validates a projected output dict against its requested config shape:
required fields present (or correctly nulled/omitted per on_missing),
and correct basic types.
"""
from typing import Any, Dict, List


class SchemaValidationError(Exception):
    pass


def _type_ok(value: Any, expected: str) -> bool:
    if value is None:
        return True  # nulls are allowed unless required (checked separately)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float))
    if expected == "string[]":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if expected == "boolean":
        return isinstance(value, bool)
    return True  # unknown/complex types: skip strict check


def validate_output(output: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    """Returns a list of validation errors (empty list = valid)."""
    errors = []
    on_missing = config.get("on_missing", "null")

    for field_spec in config.get("fields", []):
        path = field_spec["path"]
        required = field_spec.get("required", False)
        expected_type = field_spec.get("type")

        if path not in output:
            if on_missing == "omit":
                continue
            errors.append(f"field '{path}' missing from output")
            continue

        value = output[path]
        if required and value is None:
            errors.append(f"required field '{path}' is null")
        if expected_type and not _type_ok(value, expected_type):
            errors.append(f"field '{path}' expected type {expected_type}, got {type(value).__name__}")

    return errors
