"""
Conflict Resolution / Golden Record Construction.

Implements a small library of NAMED resolution functions
(adapted from Michelfeit, Knap & Necasky, arXiv:1410.7990),
selected per field. "Deciding" functions choose among observed
values; "mediating" functions compute a new value (e.g. median).
We only ever select or compute from OBSERVED data -- never invent.
"""
from typing import List, Optional
from config.settings import TRUST_FLOOR
from trust.trust import score_claims_for_field
from canonicalizer.canonicalizer import looks_like_education_institution


def resolve_best(scored: List[dict]) -> Optional[dict]:
    """Deciding function: highest-trust value wins."""
    if not scored:
        return None
    top = scored[0]
    return None if top["below_floor"] else top


def resolve_best_source(scored: List[dict], preferred_source: str) -> Optional[dict]:
    """Deciding function: prefer a named source if it claimed a value at all."""
    for r in scored:
        if preferred_source in r["sources"]:
            return None if r["below_floor"] else r
    return resolve_best(scored)


def resolve_vote(scored: List[dict]) -> Optional[dict]:
    """Deciding function: value with the most distinct supporting sources wins."""
    if not scored:
        return None
    top = max(scored, key=lambda r: len(r["sources"]))
    return None if top["trust"] < TRUST_FLOOR else top


def resolve_concat(scored: List[dict]) -> List[dict]:
    """Mediating function: union of all above-floor values (e.g. skills, emails)."""
    return [r for r in scored if not r["below_floor"]]


# field -> which resolution function to apply
FIELD_STRATEGY = {
    "full_name": "best",
    "email": "concat",       # emails[] is a list in the output schema
    "phone": "concat",       # phones[] is a list
    "current_company": "best",
    "title": "best",
    "headline": "best",
    "years_experience": "best",
    "skill": "concat",       # skills[] union, each with its own confidence
}


def _filter_claims(field: str, claims_for_field: list) -> list:
    """
    Field-specific pre-filters applied BEFORE scoring, so a bad
    candidate value never gets the chance to win on raw source
    reliability alone.

    current_company: drop any claim whose value reads like an
    educational institution (e.g. a GitHub bio listing a university)
    -- regardless of how reliable that source normally is.
    """
    if field == "current_company":
        filtered = [c for c in claims_for_field if not looks_like_education_institution(str(c[1]))]
        # Only apply the filter if it doesn't wipe out every claim --
        # if literally every source says "university", keep them rather
        # than silently returning nothing.
        return filtered if filtered else claims_for_field
    return claims_for_field


def resolve_field(field: str, claims_for_field: list, preferred_source: str = None):
    claims_for_field = _filter_claims(field, claims_for_field)
    scored = score_claims_for_field(claims_for_field)
    strategy = FIELD_STRATEGY.get(field, "best")

    if strategy == "best":
        return resolve_best(scored)
    if strategy == "best_source" and preferred_source:
        return resolve_best_source(scored, preferred_source)
    if strategy == "vote":
        return resolve_vote(scored)
    if strategy == "concat":
        return resolve_concat(scored)
    return resolve_best(scored)