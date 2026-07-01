"""
Pipeline orchestration: source detection -> parse -> map -> extract ->
match -> resolve -> golden record -> project -> validate.

This module contains the engine; main.py (CLI) just wires inputs/config
to this function and prints the result.

Key design points:
  - 6-tuple claims: (field, value, source_type, source_name, method, raw_value)
  - active_sources computed per cluster and passed to score_claims_for_field
    so the trust engine can correctly classify NO_EVIDENCE vs CONFLICT
  - Experience[], Education[] assembled from resume_entry claims
  - links.github, links.portfolio, links.linkedin assembled from all sources
  - location_raw parsed into location.city / location.country
  - Overall confidence: weighted average over POPULATED fields only;
    null fields never reduce the score
"""
import warnings
import uuid
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set

from parsers.registry import run_parser
from mapper.schema_mapper import map_record
from extractor.extractor import process_claims
from matcher.matcher import cluster_records
from resolver.resolver import FIELD_STRATEGY, _filter_claims
from trust.trust import score_claims_for_field
from provenance.provenance import build_provenance
from projection.projector import project
from schemas.canonical import (
    CanonicalCandidate, Skill, ProvenanceEntry, Experience, Education, Location
)
from canonicalizer.canonicalizer import canonicalize_company
from config.settings import SOURCE_RELIABILITY, OVERALL_CONFIDENCE_WEIGHTS, TRUST_FLOOR
from normalizer.normalizer import normalize_country


def build_golden_records(sources: Dict[str, str]) -> List[CanonicalCandidate]:
    """
    sources: dict mapping source_type -> path/handle, e.g.
      {"csv": "sample_data/recruiters.csv", "resume": "sample_data/resume.pdf"}
    Missing keys are simply not parsed -- a missing source never crashes the run.
    """
    all_records = []
    for source_type, path in sources.items():
        all_records.extend(run_parser(source_type, path))

    per_record_claims = []
    for record in all_records:
        raw_claims = map_record(record)
        processed = process_claims(raw_claims)
        per_record_claims.append(processed)

    if not per_record_claims:
        return []

    clusters = cluster_records(per_record_claims)

    golden_records = []
    for cluster in clusters:
        cluster_claims = []
        for idx in cluster:
            cluster_claims.extend(per_record_claims[idx])
        if not cluster_claims:
            warnings.warn(
                f"Empty cluster (indices {cluster}) — source produced no valid claims; "
                "record skipped.  Check that the source file has parseable content.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        golden_records.append(_build_one_record(cluster_claims))

    return golden_records


def _raw_value(claim) -> Optional[str]:
    """Extract raw_value (6th element of tuple) if present, else None."""
    return claim[5] if len(claim) > 5 else None


def _score_once(
    field: str,
    field_claims: list,
    active_sources: Set[str],
    apply_filter: bool = False,
) -> List[dict]:
    """
    Score a field's claims exactly once, passing active_sources so the trust
    engine can distinguish NO_EVIDENCE from CONFLICT.
    Optionally apply _filter_claims (used for current_company to drop
    educational institution values).
    """
    claims = _filter_claims(field, field_claims) if apply_filter else field_claims
    return score_claims_for_field(claims, active_sources=active_sources)


def _pick_best(scored: List[dict]) -> Optional[dict]:
    """Return the highest-trust scored value that clears TRUST_FLOOR, or None."""
    if not scored:
        return None
    top = scored[0]
    return None if top["trust"] < TRUST_FLOOR else top


def _build_one_record(claims) -> CanonicalCandidate:
    by_field = defaultdict(list)
    for claim in claims:
        by_field[claim[0]].append(claim)

    candidate = CanonicalCandidate(candidate_id=str(uuid.uuid4())[:8])

    # active_sources: every source type present in this candidate's cluster.
    # Passed to score_claims_for_field so it can classify NO_EVIDENCE correctly
    # (a capable source that IS active but didn't provide a value for this field).
    active_sources: Set[str] = {claim[2] for claim in claims}

    # field_trusts: {field_name -> confidence} for weighted overall confidence
    field_trusts: Dict[str, float] = {}

    # ── Scalar "best" fields ──────────────────────────────────────────────────
    for field in ("full_name", "current_company", "title", "headline", "years_experience"):
        apply_filter = (field == "current_company")
        field_claims = by_field.get(field, [])
        scored = _score_once(field, field_claims, active_sources, apply_filter=apply_filter)
        resolved = _pick_best(scored)
        if resolved:
            was_conflict = bool(resolved.get("conflicting_sources"))
            raw = next((_raw_value(c) for c in field_claims if _raw_value(c)), None)
            prov = build_provenance(
                field, resolved, FIELD_STRATEGY.get(field, "best"),
                normalization=None, was_conflict=was_conflict,
                raw_value=raw, competing_values=scored,
            )
            candidate.provenance.append(prov)
            field_trusts[field] = resolved["trust"]

            if field == "full_name":
                candidate.full_name = resolved["value"]
            elif field == "years_experience":
                candidate.years_experience = float(resolved["value"])
            elif field == "headline":
                candidate.headline = resolved["value"]

    # ── List fields: emails, phones ───────────────────────────────────────────
    for field, target_attr, norm_label in (
        ("email", "emails", "lowercase"),
        ("phone", "phones", "E164"),
    ):
        field_claims = by_field.get(field, [])
        scored = _score_once(field, field_claims, active_sources)
        resolved_list = [r for r in scored if not r["below_floor"]]
        values = []
        for r in resolved_list:
            was_conflict = bool(r.get("conflicting_sources"))
            raw = next((_raw_value(c) for c in field_claims
                        if str(c[1]) == str(r["value"]) and _raw_value(c)), None)
            prov = build_provenance(
                field, r, "concat",
                normalization=norm_label, was_conflict=was_conflict,
                raw_value=raw, competing_values=scored,
            )
            candidate.provenance.append(prov)
            values.append(r["value"])
        setattr(candidate, target_attr, values)
        if values:
            field_trusts[field] = max(r["trust"] for r in resolved_list)

    # ── Skills ────────────────────────────────────────────────────────────────
    skill_claims = by_field.get("skill", [])
    scored_skills = _score_once("skill", skill_claims, active_sources)
    resolved_skills = [r for r in scored_skills if not r["below_floor"]]
    for r in resolved_skills:
        candidate.skills.append(Skill(
            name=r["value"], confidence=r["trust"], sources=r["sources"]
        ))
        candidate.provenance.append(build_provenance(
            "skill", r, "concat",
            normalization="canonical", was_conflict=bool(r.get("conflicting_sources")),
            competing_values=scored_skills,
        ))
    if resolved_skills:
        avg_skill_trust = sum(r["trust"] for r in resolved_skills) / len(resolved_skills)
        field_trusts["skill"] = round(avg_skill_trust, 3)

    # ── Links: github_url, portfolio, linkedin_url ────────────────────────────
    links_trusts = []
    for link_field, link_attr in (
        ("github_url",   "github"),
        ("portfolio",    "portfolio"),
        ("linkedin_url", "linkedin"),
    ):
        field_claims = by_field.get(link_field, [])
        if field_claims:
            scored = _score_once(link_field, field_claims, active_sources)
            best = _pick_best(scored)
            if best:
                setattr(candidate.links, link_attr, best["value"])
                links_trusts.append(best["trust"])
                candidate.provenance.append(build_provenance(
                    link_field, best, "best",
                    normalization=None, was_conflict=bool(best.get("conflicting_sources")),
                    competing_values=scored,
                ))
    if links_trusts:
        field_trusts["links"] = round(sum(links_trusts) / len(links_trusts), 3)

    # ── affiliation_raw (GitHub self-reported affiliation) ────────────────────
    aff_claims = by_field.get("affiliation_raw", [])
    if aff_claims:
        scored = _score_once("affiliation_raw", aff_claims, active_sources)
        best = _pick_best(scored)
        if best:
            candidate.affiliation_raw = str(best["value"]).lstrip("@").strip() or None

    # ── Location: parse location_raw ─────────────────────────────────────────
    loc_claims = by_field.get("location_raw", [])
    if loc_claims:
        scored = _score_once("location_raw", loc_claims, active_sources)
        best = _pick_best(scored)
        if best:
            raw_loc = str(best["value"]).strip()
            parts = [p.strip() for p in raw_loc.split(",") if p.strip()]
            city = parts[0] if len(parts) >= 1 else None
            country_raw = parts[-1] if len(parts) >= 2 else None
            country_code = normalize_country(country_raw) if country_raw else None
            candidate.location = Location(
                city=city,
                country=country_code or (country_raw if len(parts) >= 2 else None),
            )
            if city or country_code:
                field_trusts["location"] = round(best["trust"], 3)

    # ── Experience: parsed entries from resume ────────────────────────────────
    exp_entries_built = False
    for claim in by_field.get("experience_entry", []):
        entry = claim[1]
        if not isinstance(entry, dict):
            continue
        company = entry.get("company")
        if company:
            company = canonicalize_company(company)

        # Trust computed from settings, not hardcoded
        exp_trust = round(SOURCE_RELIABILITY.get("resume", 0.70) * 0.75, 3)

        exp = Experience(
            company=company,
            title=entry.get("title"),
            employment_type=entry.get("employment_type"),
            start=entry.get("start"),
            end=entry.get("end"),
            summary=entry.get("summary") or [],
            extraction_quality=entry.get("extraction_quality"),
        )
        candidate.experience.append(exp)
        exp_entries_built = True

        candidate.provenance.append(ProvenanceEntry(
            field="experience",
            value=f"{company or '?'} | {entry.get('title') or '?'}",
            source=claim[2],
            method=claim[4],
            normalization=None,
            trust=exp_trust,
            reasons=[
                f"Parsed from resume: {entry.get('start', '')} - {entry.get('end', '')}",
                "Single-source value retained because no conflicting information exists.",
                "Resolution strategy: concat",
            ],
            confidence_breakdown={
                "base_reliability":    SOURCE_RELIABILITY.get("resume", 0.70),
                "agreement_bonus":     0.05,
                "conflict_penalty":    0.0,
                "normalization_bonus": 0.0,
                "confirmed_sources":   ["resume"],
                "conflicting_sources": [],
                "no_evidence_sources": [],
                "final_confidence":    exp_trust,
            },
        ))
        field_trusts.setdefault("experience", exp_trust)

    # Fallback: use current_company/title from ATS/CSV when no resume entries
    if not exp_entries_built:
        company_prov = next((p for p in candidate.provenance if p.field == "current_company"), None)
        title_prov   = next((p for p in candidate.provenance if p.field == "title"), None)
        if company_prov or title_prov:
            candidate.experience.append(Experience(
                company=company_prov.value if company_prov else None,
                title=title_prov.value if title_prov else None,
                summary=[],
            ))

    # ── Education ─────────────────────────────────────────────────────────────
    for claim in by_field.get("education_entry", []):
        entry = claim[1]
        if not isinstance(entry, dict):
            continue
        edu_trust = round(SOURCE_RELIABILITY.get("resume", 0.70) * 0.75, 3)
        edu = Education(
            institution=entry.get("institution"),
            degree=entry.get("degree"),
            field=entry.get("field"),
            start_year=entry.get("start_year"),
            end_year=entry.get("end_year"),
            cgpa=entry.get("cgpa"),
        )
        candidate.education.append(edu)

        candidate.provenance.append(ProvenanceEntry(
            field="education",
            value=f"{entry.get('institution', '?')} | {entry.get('degree', '?')}",
            source=claim[2],
            method=claim[4],
            normalization=None,
            trust=edu_trust,
            reasons=[
                f"Parsed from resume - field: {entry.get('field', 'N/A')}, "
                f"year: {entry.get('end_year', 'N/A')}",
                "Single-source value retained because no conflicting information exists.",
                "Resolution strategy: concat",
            ],
            confidence_breakdown={
                "base_reliability":    SOURCE_RELIABILITY.get("resume", 0.70),
                "agreement_bonus":     0.05,
                "conflict_penalty":    0.0,
                "normalization_bonus": 0.0,
                "confirmed_sources":   ["resume"],
                "conflicting_sources": [],
                "no_evidence_sources": [],
                "final_confidence":    edu_trust,
            },
        ))
        field_trusts.setdefault("education", edu_trust)

    # ── Overall confidence ────────────────────────────────────────────────────
    candidate.overall_confidence = _compute_overall_confidence(field_trusts)

    return candidate


def _compute_overall_confidence(field_trusts: Dict[str, float]) -> float:
    """
    Weighted average of per-field confidence scores using OVERALL_CONFIDENCE_WEIGHTS.

    Only POPULATED fields contribute — null fields never reduce the overall score.
    Weights of unpopulated fields are redistributed to zero (not to other fields),
    so the denominator is only the total weight of what we actually know.

    Fields not listed in OVERALL_CONFIDENCE_WEIGHTS get a small residual weight
    (0.02) so they still contribute marginally without dominating the score.
    """
    if not field_trusts:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0

    for field, trust in field_trusts.items():
        w = OVERALL_CONFIDENCE_WEIGHTS.get(field, 0.02)
        weighted_sum += w * trust
        total_weight += w

    if total_weight == 0.0:
        return 0.0

    return round(weighted_sum / total_weight, 3)


def run_pipeline(sources: Dict[str, str], config: Optional[Dict[str, Any]] = None):
    records = build_golden_records(sources)
    if config is None:
        return [r.model_dump() for r in records]

    projected = []
    for r in records:
        projected.append(project(r.model_dump(), config))
    return projected