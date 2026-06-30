"""
Central config: source reliability priors and trust thresholds.
Kept in one place so the trust formula stays explainable and tunable.
"""

# Static prior reliability per source type.
# Higher = we trust this source type more by default, before
# looking at agreement/conflict with other sources.
SOURCE_RELIABILITY = {
    "csv": 0.90,          # recruiter-entered structured data
    "ats_json": 0.95,     # system of record, usually validated upstream
    "github": 0.85,       # public API, structured, but self-reported by candidate
    "resume": 0.70,       # candidate-authored prose, unverified
    "notes": 0.50,        # free-text recruiter notes, least structured/reliable
}

# Extraction-method reliability multiplier, layered on top of source
# reliability. A tightly-anchored regex match (email/phone) is more
# trustworthy than a loose keyword scan (skills) even from the SAME
# source -- this is what keeps every resume-derived field from
# flatlining at the exact same trust score.
METHOD_RELIABILITY_MULTIPLIER = {
    "ResumeRegex": 1.10,          # email/phone -- tightly anchored pattern
    "ResumeDateRange": 1.05,      # structured date-range match
    "ResumeExperienceSpan": 1.00, # years computed from 2+ dated experience entries
    "ResumeKeywordScan": 0.90,    # skills -- loose vocabulary scan
    "ResumeHeuristic": 0.85,      # name/years-experience last-resort guesses
    "ResumeSectionParse": 1.00,   # experience/education section parse
}

# Below this trust score, a field value is withheld (set to null)
# rather than asserted -- this is the "honestly-empty over
# wrong-but-confident" rule from the assignment.
TRUST_FLOOR = 0.40

# Field-level match keys used for entity resolution, in priority order.
MATCH_KEY_PRIORITY = ["email", "phone", "fuzzy_name_company"]

# RapidFuzz threshold (0-100) for the fallback name+company match.
FUZZY_MATCH_THRESHOLD = 88

# Per-field weights for overall_confidence (must roughly sum to 1.0;
# any field not listed falls back to an even share of the remainder).
OVERALL_CONFIDENCE_WEIGHTS = {
    "full_name": 0.10,
    "email": 0.15,
    "phone": 0.15,
    "current_company": 0.10,
    "title": 0.05,
    "headline": 0.05,
    "years_experience": 0.05,
    "skill": 0.20,
    "experience": 0.10,
    "education": 0.05,
}