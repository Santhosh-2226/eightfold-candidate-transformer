"""
Information Extraction + Canonicalization + Normalization.
Applied to the claims produced by the schema mapper.

Now also propagates the raw_value (pre-normalization) alongside each claim
so the provenance layer can build normalization traces like:
  "6374071150 → +916374071150"
  "CPP → C++"

Claim tuple extended to 6 elements:
  (field, norm_value, source_type, source_name, method, raw_value)
"""
from typing import List, Tuple, Optional
from canonicalizer.canonicalizer import canonicalize_skill, canonicalize_company
from normalizer.normalizer import normalize_phone, normalize_email
from validator.validator import is_valid_claim

# 6-tuple: field, norm_value, source_type, source_name, method, raw_value
Claim = Tuple[str, object, str, str, str, Optional[str]]


def process_claims(raw_claims) -> List[Claim]:
    """
    Canonicalize + normalize + validate each claim.
    Invalid claims are dropped (never silently kept as garbage).
    Returns 6-tuples including the original raw_value for trace purposes.
    """
    processed = []
    for item in raw_claims:
        # Support both old 5-tuple and any future shapes
        field, value, source_type, source_name, method = item[:5]
        raw_value = str(value) if value is not None else None
        norm_value = value

        if field == "phone":
            norm_value = normalize_phone(str(value))
            method = method + "+E164"
        elif field == "email":
            norm_value = normalize_email(str(value))
            method = method + "+lowercase"
        elif field == "skill":
            norm_value = canonicalize_skill(str(value))
            method = method + "+canonical"
        elif field == "current_company":
            norm_value = canonicalize_company(str(value))
            method = method + "+canonical"
        elif field in ("experience_entry", "education_entry"):
            # Structured dicts — pass through without normalization
            processed.append((field, value, source_type, source_name, method, None))
            continue

        if norm_value is None:
            continue
        if not is_valid_claim(field, norm_value):
            continue

        # Only record raw_value if it actually changed (non-trivial trace)
        trace = raw_value if (raw_value and str(norm_value) != raw_value) else None
        processed.append((field, norm_value, source_type, source_name, method, trace))

    return processed
