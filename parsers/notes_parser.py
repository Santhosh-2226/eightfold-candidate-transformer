"""
Parser for free-text recruiter notes (.txt).
Lowest-reliability source -- rule-based regex for email/phone,
full shared vocabulary for skill keyword scan.
"""
import re
from typing import List
from schemas.canonical import RawRecord
from extractor.skills_vocab import KNOWN_SKILLS

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s\-\(\)]{7,}\d)")


def parse_notes(path: str) -> List[RawRecord]:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []

    if not text.strip():
        return []

    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    lower  = text.lower()
    found_skills = sorted({
        s for s in KNOWN_SKILLS
        if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", lower)
    })

    fields = {
        "raw_text": text.strip(),
        "email":    emails[0] if emails else None,
        "phone":    phones[0].strip() if phones else None,
        "skills":   found_skills,
    }
    return [RawRecord(
        source_type="notes",
        source_name="recruiter_notes",
        fields=fields,
        warnings=[],
    )]
