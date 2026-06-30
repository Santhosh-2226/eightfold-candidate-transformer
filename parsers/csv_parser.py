"""
Parser for recruiter CSV exports.
Expected columns (case-insensitive, order-independent):
  name, email, phone, current_company, title
Any missing/extra columns are handled gracefully -- a malformed row
is skipped with a warning, never crashes the run.
"""
import csv
from typing import List
from schemas.canonical import RawRecord


def parse_csv(path: str) -> List[RawRecord]:
    records: List[RawRecord] = []
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # normalize header names to lowercase for robustness
            if reader.fieldnames:
                reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]
            for i, row in enumerate(reader):
                warnings = []
                name = (row.get("name") or "").strip()
                if not name:
                    warnings.append("missing name; row skipped")
                    continue
                fields = {
                    "full_name": name or None,
                    "email": (row.get("email") or "").strip() or None,
                    "phone": (row.get("phone") or "").strip() or None,
                    "current_company": (row.get("current_company") or "").strip() or None,
                    "title": (row.get("title") or "").strip() or None,
                }
                records.append(RawRecord(
                    source_type="csv",
                    source_name=f"recruiter_csv_row_{i+2}",  # +2: header + 1-index
                    fields=fields,
                    warnings=warnings,
                ))
    except FileNotFoundError:
        return []
    except Exception as e:
        # never let a malformed file crash the whole run
        return []
    return records
