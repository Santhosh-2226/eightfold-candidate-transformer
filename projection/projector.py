"""
Projection Engine.
Takes the rich internal CanonicalCandidate and a runtime config, and
produces the requested output shape -- WITHOUT mutating the internal
canonical record. This is the "same engine, no code changes" layer.

Config shape (matches the assignment's example):
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
    {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
  ],
  "include_confidence": true,
  "on_missing": "null"   # "null" | "omit" | "error"
}
"""
from typing import Any, Dict
import re

ARRAY_INDEX_RE = re.compile(r"^(\w+)\[(\d*)\]$")
ARRAY_FIELD_RE = re.compile(r"^(\w+)\[\]\.(\w+)$")


class MissingRequiredFieldError(Exception):
    pass


def _resolve_path(record: Dict[str, Any], path: str):
    """Resolve a 'from' path like 'emails[0]' or 'skills[].name' against
    the canonical record (already dumped to a plain dict)."""
    m = ARRAY_FIELD_RE.match(path)
    if m:
        list_field, sub_field = m.groups()
        items = record.get(list_field) or []
        return [item.get(sub_field) for item in items if isinstance(item, dict)]

    m = ARRAY_INDEX_RE.match(path)
    if m:
        list_field, idx = m.groups()
        items = record.get(list_field) or []
        if idx == "":
            return items
        idx = int(idx)
        return items[idx] if 0 <= idx < len(items) else None

    return record.get(path)


def project(canonical_record: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    on_missing = config.get("on_missing", "null")
    include_confidence = config.get("include_confidence", True)
    include_provenance = config.get("include_provenance", True)

    output: Dict[str, Any] = {}

    for field_spec in config.get("fields", []):
        out_path = field_spec["path"]
        source_path = field_spec.get("from", out_path)
        required = field_spec.get("required", False)

        value = _resolve_path(canonical_record, source_path)

        is_missing = value is None or value == [] or value == ""
        if is_missing:
            if required and on_missing == "error":
                raise MissingRequiredFieldError(f"required field '{out_path}' is missing")
            if on_missing == "omit":
                continue
            output[out_path] = None
            continue

        output[out_path] = value

    if include_confidence and "overall_confidence" not in output:
        output["overall_confidence"] = canonical_record.get("overall_confidence")

    if include_provenance and "provenance" not in output:
        output["provenance"] = canonical_record.get("provenance")
    elif not include_provenance:
        output.pop("provenance", None)

    return output
