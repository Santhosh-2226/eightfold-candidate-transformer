"""
Parser for resume files (PDF or plain text).
Rule-based extraction only (regex + section heuristics) -- no LLM,
to keep the pipeline fully deterministic.

Extracts:
  - full_name, email, phone
  - skills (full vocabulary via shared skills_vocab)
  - experience[] with company, title, employment_type, start, end, summary[]
  - education[] with institution, degree, field, start_year, end_year, cgpa
  - years_experience (computed from internship date spans; falls back
    to the year-range heuristic)

Experience extraction strategy (rewritten):
  Resume layouts vary a lot in WHERE the company name sits relative to
  the title/date line (before it, after it, same line). Rather than
  assuming a fixed order, we find every line containing a date range
  ("anchor" lines) and then search a small window of lines AROUND each
  anchor for the company name, instead of only checking the single
  line immediately before it. This is what fixes the previous bug
  where a title+date+employment-type line and its company name (which
  appeared on a LATER line, not an earlier one) were being split into
  two separate, half-empty experience entries.
"""
import re
from typing import List, Optional, Dict, Any
from schemas.canonical import RawRecord
from extractor.skills_vocab import KNOWN_SKILLS
from canonicalizer.canonicalizer import canonicalize_company, canonicalize_degree

# ── Regex primitives ────────────────────────────────────────────────────────
EMAIL_RE     = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE     = re.compile(r"(\+?\d[\d\s\-\(\)]{7,}\d)")
YEAR_RE      = re.compile(r"(19|20)\d{2}")
LINKEDIN_RE  = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-]+)", re.IGNORECASE)
GITHUB_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_\-]+)", re.IGNORECASE)

# Month names / abbreviations → zero-padded number
_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

DATE_RE = re.compile(
    r"(?:(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<yr1>\d{4})"  # "May 2025"
    r"|(?P<yr2>\d{4})[/-](?P<mon2>\d{2})"              # "2024-08"
    r"|(?P<mon3>\d{2})/(?P<yr3>\d{4}))",               # "08/2024"
    re.IGNORECASE,
)

RANGE_RE = re.compile(
    r"((?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{2}/\d{4})\s*[-–—to]+\s*"
    r"((?:[A-Za-z]{3,9}\.?\s+)?\d{4}|\d{2}/\d{4}|[Pp]resent|[Cc]urrent)",
    re.IGNORECASE,
)

# "Role: X" / "Role - X" parenthetical, common in some resume builders
ROLE_PAREN_RE = re.compile(r"\(?\s*role\s*[:\-]\s*([^()|,]+?)\s*\)?(?=[,|]|$)", re.IGNORECASE)

EMPLOYMENT_TYPE_RE = re.compile(
    r"\b(full[\s-]?time|part[\s-]?time|internship|intern\b|contract|freelance|temporary)\b",
    re.IGNORECASE,
)
_EMPLOYMENT_TYPE_DISPLAY = {
    "full time": "Full Time", "fulltime": "Full Time", "full-time": "Full Time",
    "part time": "Part Time", "parttime": "Part Time", "part-time": "Part Time",
    "internship": "Internship", "intern": "Internship",
    "contract": "Contract", "freelance": "Freelance", "temporary": "Temporary",
}

# Section header detector (case-insensitive, tolerates bold/underline markers)
SECTION_HEADERS = {
    "experience":  re.compile(r"^\s*(experience|work experience|internship|internships|professional experience)\s*:?\s*$", re.IGNORECASE),
    "education":   re.compile(r"^\s*(education|academic background|qualifications)\s*:?\s*$", re.IGNORECASE),
    "skills":      re.compile(r"^\s*(skills|technical skills|key skills|competencies)\s*:?\s*$", re.IGNORECASE),
    "projects":    re.compile(r"^\s*(projects|personal projects|key projects)\s*:?\s*$", re.IGNORECASE),
    "summary":     re.compile(r"^\s*(summary|profile|about|objective)\s*:?\s*$", re.IGNORECASE),
    "certifications": re.compile(r"^\s*(certifications?|certificates?|courses?)\s*:?\s*$", re.IGNORECASE),
    "links":       re.compile(r"^\s*(links?|profiles?|contact|online presence)\s*:?\s*$", re.IGNORECASE),
}


# ── Text extraction ─────────────────────────────────────────────────────────
def _extract_text(path: str) -> Optional[str]:
    if path.lower().endswith(".pdf"):
        try:
            import pdfplumber
            parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts)
        except Exception:
            return None
    else:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None


# ── Section splitting ───────────────────────────────────────────────────────
def _split_sections(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    sections: Dict[str, list] = {"header": []}
    current = "header"
    for line in lines:
        matched = False
        for sec_name, pattern in SECTION_HEADERS.items():
            if pattern.match(line):
                current = sec_name
                sections.setdefault(current, [])
                matched = True
                break
        if not matched:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


# ── Date parsing ────────────────────────────────────────────────────────────
def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    m = DATE_RE.search(raw)
    if not m:
        y = YEAR_RE.search(raw)
        return f"{y.group()}-01" if y else None
    g = m.groupdict()
    if g.get("mon") and g.get("yr1"):
        mon = _MONTHS.get(g["mon"].lower()[:3])
        return f"{g['yr1']}-{mon}" if mon else f"{g['yr1']}-01"
    if g.get("yr2") and g.get("mon2"):
        return f"{g['yr2']}-{g['mon2'].zfill(2)}"
    if g.get("mon3") and g.get("yr3"):
        return f"{g['yr3']}-{g['mon3'].zfill(2)}"
    return None


def _parse_range(text: str):
    m = RANGE_RE.search(text)
    if not m:
        return None, None
    start = _parse_date(m.group(1))
    end_raw = m.group(2).strip()
    end = "Present" if end_raw.lower() in ("present", "current") else _parse_date(end_raw)
    return start, end


def _months_between(start: Optional[str], end: Optional[str]) -> float:
    if not start:
        return 0.0
    import datetime
    try:
        sy, sm = int(start[:4]), int(start[5:7])
        if end and end != "Present":
            ey, em = int(end[:4]), int(end[5:7])
        else:
            today = datetime.date.today()
            ey, em = today.year, today.month
        months = (ey - sy) * 12 + (em - sm)
        return round(max(0.0, months / 12.0), 2)
    except Exception:
        return 0.0


# ── Name heuristic ──────────────────────────────────────────────────────────
def _guess_name(text: str) -> Optional[str]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip lines that look like section headers — they can be short,
        # title-cased, and still be completely wrong as a name.
        if any(p.match(line) for p in SECTION_HEADERS.values()):
            break
        words = line.split()
        if (1 < len(words) <= 4
                and all(w[0:1].isupper() for w in words)
                and "@" not in line
                and not any(ch.isdigit() for ch in line)):
            return line
        break
    return None


TITLE_KEYWORDS_RE = re.compile(
    r"\b(engineer|developer|manager|intern|analyst|scientist|designer|lead|director|"
    r"consultant|specialist|architect|administrator|coordinator|associate|researcher|"
    r"officer|executive|president|founder|head\b|recruiter)\b",
    re.IGNORECASE,
)


# ── Experience extraction (rewritten: anchor + window search) ──────────────
def _is_bullet(line: str) -> bool:
    return line.startswith(("•", "*", "-", "‣", "◦"))


def _looks_like_company_line(line: str) -> bool:
    """
    Heuristic for "this line is a company name", not a summary sentence
    or a pure employment-type/date line:
      - not a bullet
      - not a section header
      - doesn't itself contain a date range
      - short (<=8 words)
      - doesn't end in a period (summary sentences usually do)
      - isn't JUST an employment-type word ("Full Time")
    """
    if not line or _is_bullet(line):
        return False
    if any(p.match(line) for p in SECTION_HEADERS.values()):
        return False
    if RANGE_RE.search(line):
        return False
    words = line.split()
    if not (0 < len(words) <= 8):
        return False
    if line.rstrip().endswith("."):
        return False
    bare = EMPLOYMENT_TYPE_RE.sub("", line).strip(" |,-")
    if not bare:
        return False
    return True


def _strip_anchor_line(line: str) -> str:
    """Remove date range, 'Role: X' parenthetical, and pipe segments that
    are pure employment-type, leaving the remaining title text."""
    cleaned = RANGE_RE.sub("", line)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)  # leftover empty parens
    # Drop pipe segments that are ONLY an employment type
    segments = [s.strip() for s in cleaned.split("|")]
    segments = [s for s in segments if s and not EMPLOYMENT_TYPE_RE.fullmatch(s.strip())]
    cleaned = " | ".join(segments)
    cleaned = cleaned.strip(" ,|-–—")
    return cleaned


def _extract_experience(section_text: str) -> List[Dict[str, Any]]:
    lines = [l.strip() for l in section_text.splitlines() if l.strip()]
    anchors = [i for i, l in enumerate(lines) if RANGE_RE.search(l)]
    if not anchors:
        return []

    entries = []
    used_company_lines = set()
    for idx, anchor_i in enumerate(anchors):
        anchor_line = lines[anchor_i]
        prev_anchor = anchors[idx - 1] if idx > 0 else -1
        next_anchor = anchors[idx + 1] if idx + 1 < len(anchors) else len(lines)

        start, end = _parse_range(anchor_line)

        # Employment type, from the anchor line
        et_match = EMPLOYMENT_TYPE_RE.search(anchor_line)
        employment_type = _EMPLOYMENT_TYPE_DISPLAY.get(
            et_match.group(1).lower().replace(" ", " "), et_match.group(1).title()
        ) if et_match else None

        # Title: prefer "Role: X" pattern, else the cleaned anchor line text
        role_match = ROLE_PAREN_RE.search(anchor_line)
        if role_match:
            title = role_match.group(1).strip()
        else:
            title = _strip_anchor_line(anchor_line)
            # If a pipe is still present after stripping, take the first segment
            if "|" in title:
                title = title.split("|", 1)[0].strip()
        title = title or None

        # Company: search the window AROUND the anchor (both directions),
        # bounded by neighboring anchors, for a company-shaped line.
        # Prefer the closest candidate line to the anchor.
        window_indices = (
            list(range(max(prev_anchor + 1, anchor_i - 3), anchor_i))[::-1]  # backward, closest first
            + list(range(anchor_i + 1, min(next_anchor, anchor_i + 4)))      # forward
        )
        company = None
        for j in window_indices:
            if j in used_company_lines:
                continue
            cand = lines[j]
            if not _looks_like_company_line(cand):
                continue
            # A line containing job-title keywords ("Engineer", "Intern", ...)
            # is almost certainly a title, not a company -- if we don't have
            # a title yet, claim it as the title instead of the company.
            if title is None and TITLE_KEYWORDS_RE.search(cand):
                title = cand
                used_company_lines.add(j)
                continue
            company = cand
            used_company_lines.add(j)
            break

        # Summary: bullet lines (or sentence-ending lines) in the window
        # that are NOT the company line itself.
        summary = []
        for j in range(anchor_i + 1, min(next_anchor, len(lines))):
            lj = lines[j]
            if lj == company:
                continue
            if any(p.match(lj) for p in SECTION_HEADERS.values()):
                break
            if _is_bullet(lj) or lj.rstrip().endswith("."):
                summary.append(lj.lstrip("•*-‣◦ ").strip())

        quality = "complete" if (company and title and start) else (
            "partial" if (company or title) else "low_confidence"
        )

        entries.append({
            "company": canonicalize_company(company) if company else None,
            "title": title,
            "employment_type": employment_type,
            "start": start,
            "end": end,
            "summary": summary,
            "extraction_quality": quality,
        })

    return entries


# ── Education extraction ────────────────────────────────────────────────────
_DEGREE_WORDS = re.compile(
    r"\b(b\.?tech|b\.?e\b|btech|be\b|m\.?tech|mtech|m\.?sc|bsc|b\.?sc|"
    r"b\.?com|mba|ph\.?d|bachelor|master|associate|diploma)\b",
    re.IGNORECASE,
)
_CGPA_RE  = re.compile(r"(?:cgpa|gpa|score)\s*[:\-–]?\s*([\d.]+)(?:\s*/\s*\d+(?:\.\d+)?)?", re.IGNORECASE)
_YEAR_END = re.compile(r"(?:20)\d{2}")
_YEAR_RANGE_RE = re.compile(r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})")


def _clean_fragment(text: Optional[str]) -> Optional[str]:
    """Collapse leftover punctuation/whitespace after regex substitutions
    (e.g. "Data Science,  | " -> "Data Science")."""
    if not text:
        return None
    text = re.sub(r"\s*\|\s*", " ", text)
    text = re.sub(r"\s*,\s*,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ,|-–—")
    return text or None


def _extract_education(section_text: str) -> List[Dict[str, Any]]:
    entries = []
    lines = [l.strip() for l in section_text.splitlines() if l.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        institution, degree, field_of_study = None, None, None
        start_year, end_year, cgpa = None, None, None

        deg_match = _DEGREE_WORDS.search(line)
        degree_line = None
        if deg_match:
            degree_line = line
            degree = canonicalize_degree(deg_match.group())
            after = line[deg_match.end():].strip().lstrip("–—-:, ")
            after = re.sub(r"^in\s+", "", after, flags=re.IGNORECASE).strip()
            # Strip a trailing year range / CGPA fragment from the field text
            after = _YEAR_RANGE_RE.sub("", after)
            after = _CGPA_RE.sub("", after)
            after = after.strip(" ,|-–—")
            field_of_study = _clean_fragment(after)

            if i > 0 and not _DEGREE_WORDS.search(lines[i - 1]):
                institution = lines[i - 1]
            elif i + 1 < len(lines) and not _DEGREE_WORDS.search(lines[i + 1]):
                institution = lines[i + 1]

        elif len(line.split()) >= 2 and not _is_bullet(line):
            if i + 1 < len(lines) and _DEGREE_WORDS.search(lines[i + 1]):
                institution = line
                deg_match = _DEGREE_WORDS.search(lines[i + 1])
                degree_line = lines[i + 1]
                degree = canonicalize_degree(deg_match.group())
                after = lines[i + 1][deg_match.end():].strip().lstrip("–—-:, ")
                after = re.sub(r"^in\s+", "", after, flags=re.IGNORECASE).strip()
                after = _YEAR_RANGE_RE.sub("", after)
                after = _CGPA_RE.sub("", after)
                field_of_study = _clean_fragment(after)
                i += 1

        if institution or degree:
            if institution:
                institution = re.sub(r",(?=\S)", ", ", institution)
            institution = canonicalize_company(institution) if institution else None

            scan_lines = ([degree_line] if degree_line else []) + [
                lines[j] for j in range(i + 1, min(i + 4, len(lines)))
                if not any(p.match(lines[j]) for p in SECTION_HEADERS.values())
            ]
            for scan_line in scan_lines:
                cg = _CGPA_RE.search(scan_line)
                if cg and cgpa is None:
                    try:
                        cgpa = float(cg.group(1))
                    except ValueError:
                        pass
                yr_range = _YEAR_RANGE_RE.search(scan_line)
                if yr_range and not (start_year and end_year):
                    start_year, end_year = int(yr_range.group(1)), int(yr_range.group(2))
                elif not end_year:
                    yr_m = _YEAR_END.findall(scan_line)
                    if yr_m:
                        end_year = int(max(yr_m))
            entries.append({
                "institution": institution,
                "degree": degree,
                "field": field_of_study,
                "start_year": start_year,
                "end_year": end_year,
                "cgpa": cgpa,
            })
        i += 1
    return entries


# ── Years experience ───────────────────────────────────────────────────
def _compute_years_from_experience(exp_entries: List[Dict]) -> Optional[float]:
    """
    Only sum across entries that have at least a start date.  Require at least
    two entries with dates before returning a number — a single internship span
    produces a misleadingly precise number that isn’t the same thing as real
    multi-year tenure.  With < 2 dated entries we return None and let the
    field be resolved from a more authoritative source (CSV/ATS).
    """
    dated = [e for e in exp_entries if e.get("start")]
    if len(dated) < 2:
        return None   # not enough signal for an honest estimate
    total = sum(_months_between(e.get("start"), e.get("end")) for e in dated)
    return round(total, 2) if total > 0 else None


def _guess_years_heuristic(text: str, experience_entries_found: int) -> Optional[float]:
    """
    Last-resort span heuristic: only kick in when we have no parsed experience
    entries at all (e.g. no recognisable section header).  Even then, require
    at least two distinct years so we don’t fabricate a number from a single
    graduation year or date-of-birth.
    """
    if experience_entries_found > 0:
        return None   # parsed entries exist; don’t override with a heuristic
    years = sorted({int(m.group()) for m in YEAR_RE.finditer(text)})
    if len(years) >= 2:
        span = years[-1] - years[0]
        if 0 < span <= 45:
            return float(span)
    return None


# ── Main entry point ─────────────────────────────────────────────────────────
def parse_resume(path: str) -> List[RawRecord]:
    text = _extract_text(path)
    warnings = []
    if text is None:
        return [RawRecord(
            source_type="resume", source_name="resume",
            fields={}, warnings=["could not read resume file; source skipped"],
        )]
    if not text.strip():
        warnings.append("resume appears empty (e.g. scanned image with no text layer)")
        return [RawRecord(source_type="resume", source_name="resume", fields={}, warnings=warnings)]

    sections = _split_sections(text)
    lower = text.lower()

    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)

    # LinkedIn and GitHub URLs — extracted from resume text (links section or header)
    linkedin_m = LINKEDIN_RE.search(text)
    linkedin_url = linkedin_m.group(0) if linkedin_m else None
    if linkedin_url and not linkedin_url.lower().startswith("http"):
        linkedin_url = "https://" + linkedin_url

    github_m = GITHUB_URL_RE.search(text)
    github_url = github_m.group(0) if github_m else None
    if github_url and not github_url.lower().startswith("http"):
        github_url = "https://" + github_url

    skills = sorted({
        s for s in KNOWN_SKILLS
        if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", lower)
    })

    exp_section = sections.get("experience", "")
    experience = _extract_experience(exp_section) if exp_section.strip() else []
    if not experience:
        # fall back to scanning the whole resume in case there's no
        # explicit "Experience" header (e.g. internships listed under
        # "Projects" or with no section header at all)
        experience = _extract_experience(text)

    edu_section = sections.get("education", "")
    education = _extract_education(edu_section) if edu_section.strip() else []

    years_exp = _compute_years_from_experience(experience)
    years_exp_method = "ResumeExperienceSpan"  # computed from multiple dated entries
    if years_exp is None:
        years_exp = _guess_years_heuristic(text, experience_entries_found=len(experience))
        years_exp_method = "ResumeHeuristic"   # last-resort span guess

    fields = {
        "raw_text": text,
        "full_name": _guess_name(sections.get("header", text)),
        "email": emails[0] if emails else None,
        "phone": phones[0].strip() if phones else None,
        "linkedin_url": linkedin_url,
        "github_url": github_url,
        "skills": skills,
        "years_experience": years_exp,
        "years_experience_method": years_exp_method,
        "experience": experience,
        "education": education,
    }
    return [RawRecord(
        source_type="resume", source_name="resume",
        fields=fields, warnings=warnings,
    )]