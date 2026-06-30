"""
Normalization: format standardization, distinct from canonicalization
(semantic equivalence). Invalid input never crashes the pipeline --
it returns None and the caller records a validation warning.
"""
from typing import Optional
import re
import phonenumbers
import pycountry


def normalize_phone(raw: str, default_region: str = "IN") -> Optional[str]:
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def normalize_email(raw: str) -> Optional[str]:
    if not raw or "@" not in raw:
        return None
    return raw.strip().lower()


# ── Deterministic date normalizer ─────────────────────────────────────────────
# Replaces dateparser (which is locale/tz-sensitive and non-deterministic).
# Handles: "May 2025", "2024-08", "08/2024", "2025", "Jan 2020 - Present"
_MONTHS_LOCAL = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}
_DATE_NORM_RE = re.compile(
    r"(?:(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<yr1>\d{4})"   # "May 2025"
    r"|(?P<yr2>\d{4})[/-](?P<mon2>\d{2})"               # "2024-08"
    r"|(?P<mon3>\d{2})/(?P<yr3>\d{4})"                  # "08/2024"
    r"|(?P<yr4>(?:19|20)\d{2}))",                        # bare year "2025"
    re.IGNORECASE,
)


def normalize_date_to_year_month(raw: str) -> Optional[str]:
    """
    Convert any recognised date format to YYYY-MM.
    Returns None for unrecognised input.  Fully deterministic.
    """
    if not raw:
        return None
    raw = raw.strip()
    m = _DATE_NORM_RE.search(raw)
    if not m:
        return None
    g = m.groupdict()
    if g.get("mon") and g.get("yr1"):
        mon_num = _MONTHS_LOCAL.get(g["mon"].lower()[:3])
        return f"{g['yr1']}-{mon_num}" if mon_num else f"{g['yr1']}-01"
    if g.get("yr2") and g.get("mon2"):
        return f"{g['yr2']}-{g['mon2'].zfill(2)}"
    if g.get("mon3") and g.get("yr3"):
        return f"{g['yr3']}-{g['mon3'].zfill(2)}"
    if g.get("yr4"):
        return f"{g['yr4']}-01"
    return None


def normalize_country(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        match = pycountry.countries.lookup(raw)
        return match.alpha_2
    except LookupError:
        return None


def is_valid_url(raw: str) -> bool:
    if not raw:
        return False
    return raw.strip().lower().startswith(("http://", "https://"))
