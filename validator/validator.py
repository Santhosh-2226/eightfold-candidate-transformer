"""
Validation Engine.
Checks that a claim's value is well-formed for its field type.
Invalid values are flagged (not silently kept) -- downstream, an
invalid claim is excluded from matching/scoring rather than trusted.
"""
from normalizer.normalizer import normalize_email, normalize_phone, is_valid_url


def is_valid_claim(field: str, value, normalized_value=None) -> bool:
    if field == "email":
        return normalize_email(value) is not None
    if field == "phone":
        return normalize_phone(value) is not None
    if field in ("github_url", "portfolio"):
        return is_valid_url(value) if value else True  # optional fields
    if field == "years_experience":
        try:
            v = float(value)
            return 0 <= v <= 60
        except (TypeError, ValueError):
            return False
    # text fields: just must be non-empty after stripping
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None
