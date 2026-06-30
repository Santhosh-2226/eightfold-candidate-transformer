"""
Parser registry. Adding a new source type means registering a new
function here -- no existing parser code needs to change.
"""
from typing import Callable, Dict, List
from schemas.canonical import RawRecord

from parsers.csv_parser import parse_csv
from parsers.ats_parser import parse_ats_json
from parsers.github_parser import parse_github
from parsers.notes_parser import parse_notes
from parsers.resume_parser import parse_resume

REGISTRY: Dict[str, Callable[[str], List[RawRecord]]] = {
    "csv": parse_csv,
    "ats_json": parse_ats_json,
    "github": parse_github,
    "notes": parse_notes,
    "resume": parse_resume,
}


import warnings


def run_parser(source_type: str, path_or_handle: str) -> List[RawRecord]:
    parser = REGISTRY.get(source_type)
    if parser is None:
        return []
    try:
        return parser(path_or_handle)
    except Exception as exc:
        # A single bad source must never crash the whole run, but we DO want
        # to know about it — a bare `except` would silently hide Python bugs.
        warnings.warn(
            f"Parser '{source_type}' raised an unexpected error for "
            f"'{path_or_handle}': {type(exc).__name__}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return []

