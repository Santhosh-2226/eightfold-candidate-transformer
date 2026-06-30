"""
Parser for ATS JSON blobs. ATS field names do NOT match our canonical
names -- the schema_mapper handles renaming, this parser only handles
file I/O and shape validation.

Expected (example) shape, one or many records:
[
  {
    "candidateName": "...",
    "contact": {"mail": "...", "mobile": "..."},
    "employer": "...",
    "role": "..."
  },
  ...
]
"""
import json
from typing import List
from schemas.canonical import RawRecord


def parse_ats_json(path: str) -> List[RawRecord]:
    records: List[RawRecord] = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        warnings = []
        contact = item.get("contact") or {}
        name = item.get("candidateName") or item.get("name")
        if not name:
            warnings.append("missing candidateName; record skipped")
            continue
        fields = {
            "candidateName": name,
            "mail": contact.get("mail") or item.get("mail"),
            "mobile": contact.get("mobile") or item.get("mobile"),
            "employer": item.get("employer"),
            "role": item.get("role"),
        }
        records.append(RawRecord(
            source_type="ats_json",
            source_name=f"ats_record_{i}",
            fields=fields,
            warnings=warnings,
        ))
    return records
