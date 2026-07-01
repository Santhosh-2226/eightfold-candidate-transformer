"""
Central config: source reliability priors and trust thresholds.
Kept in one place so the trust formula stays explainable and tunable.
"""

# Static prior reliability per source type.
# Higher = we trust this source type more by default.
SOURCE_RELIABILITY = {
    "csv":      0.90,   # recruiter-entered structured data
    "ats_json": 0.95,   # system of record, usually validated upstream
    "github":   0.85,   # public API, structured, but self-reported by candidate
    "resume":   0.70,   # candidate-authored prose, unverified
    "notes":    0.50,   # free-text recruiter notes, least structured/reliable
}

# Extraction-method reliability multiplier, layered on top of source reliability.
# A tightly-anchored regex (email/phone) is more trustworthy than a keyword scan
# (skills) even from the SAME source.
METHOD_RELIABILITY_MULTIPLIER = {
    "ResumeRegex":          1.10,  # email/phone — tightly anchored pattern
    "ResumeDateRange":      1.05,  # structured date-range match
    "ResumeExperienceSpan": 1.00,  # years from 2+ dated experience entries
    "ResumeKeywordScan":    0.90,  # skills — loose vocabulary scan
    "ResumeHeuristic":      0.85,  # name/years-experience last-resort guesses
    "ResumeSectionParse":   1.00,  # experience/education section parse
}

# Below this confidence the field value is withheld (set to null).
# "Wrong-but-confident is worse than honestly-empty."
TRUST_FLOOR = 0.40

# Field-level match keys used for entity resolution, in priority order.
MATCH_KEY_PRIORITY = ["email", "phone", "fuzzy_name_company"]

# RapidFuzz threshold (0-100) for the fallback name+company match.
FUZZY_MATCH_THRESHOLD = 88

# ── Field Coverage ────────────────────────────────────────────────────────────
# Defines which source types are CAPABLE of providing each canonical field.
# Used only for evidence classification (CONFIRMED / CONFLICT / NO_EVIDENCE).
# It does NOT automatically reduce confidence when a source is absent.
FIELD_COVERAGE = {
    "full_name":        ["csv", "ats_json", "resume", "github", "notes"],
    "email":            ["csv", "ats_json", "resume", "notes"],
    "phone":            ["csv", "ats_json", "resume", "notes"],
    "headline":         ["resume", "github"],
    "current_company":  ["csv", "ats_json", "resume"],  # github -> affiliation_raw
    "title":            ["csv", "ats_json", "resume"],
    "skill":            ["resume", "notes"],
    "experience_entry": ["resume", "ats_json"],
    "education_entry":  ["resume"],
    "years_experience": ["resume"],
    "location_raw":     ["resume", "github", "notes"],
    "github_url":       ["github", "resume"],
    "linkedin_url":     ["resume"],
    "portfolio":        ["resume", "github"],
    "affiliation_raw":  ["github"],
}

# ── Overall confidence weights ────────────────────────────────────────────────
# Weights for fields that contribute to overall_confidence.
# Only POPULATED (non-null) fields contribute — null fields never reduce score.
# Weights are normalized over the populated subset at runtime.
OVERALL_CONFIDENCE_WEIGHTS = {
    "full_name":       0.10,
    "email":           0.20,
    "phone":           0.15,
    "experience":      0.15,
    "skill":           0.15,
    "education":       0.10,
    "current_company": 0.10,
    "headline":        0.05,
    "links":           0.05,
    "location":        0.05,
}