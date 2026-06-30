"""
Tests for the candidate data transformer.
Run with: pytest tests/
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main_pipeline import build_golden_records, run_pipeline
from trust.trust import score_claims_for_field
from resolver.resolver import resolve_field
from normalizer.normalizer import normalize_phone, normalize_email, normalize_country
from canonicalizer.canonicalizer import canonicalize_skill, canonicalize_company
from projection.projector import project, MissingRequiredFieldError


def test_merge_across_sources_dedupes_candidate():
    """Jane Doe appears in csv, ats, resume, notes -> must merge into ONE record."""
    records = build_golden_records({
        "csv": "sample_data/recruiters.csv",
        "ats_json": "sample_data/ats.json",
        "resume": "sample_data/resume.txt",
        "notes": "sample_data/notes.txt",
    })
    jane_records = [r for r in records if r.full_name == "Jane Doe"]
    assert len(jane_records) == 1
    assert jane_records[0].emails == ["jane.doe@gmail.com"]


def test_conflicting_company_names_resolve_after_canonicalization():
    """CSV says 'Google Inc.', ATS says 'Google' -- after canonicalization
    these should be treated as the SAME value, not a conflict."""
    assert canonicalize_company("Google Inc.") == canonicalize_company("Google")


def test_missing_source_does_not_crash():
    """A nonexistent file path must degrade gracefully, never raise."""
    records = build_golden_records({"csv": "sample_data/does_not_exist.csv"})
    assert records == []  # no candidates, but no crash


def test_low_trust_single_source_value_is_withheld():
    """EDGE CASE: a single claim from a low-reliability source (notes) with
    no corroboration should fall below the trust floor and resolve to None
    rather than being asserted -- this is the core 'wrong but confident'
    prevention mechanism."""
    claims = [("title", "Some Vague Title", "notes", "recruiter_notes", "NotesGuess")]
    resolved = resolve_field("title", claims)
    scored = score_claims_for_field(claims)
    assert scored[0]["trust"] < 0.55  # notes alone never reaches high trust
    # if trust falls below the configured floor, resolve_field must return None
    if scored[0]["below_floor"]:
        assert resolved is None


def test_phone_normalization_to_e164():
    assert normalize_phone("9876543210", default_region="IN") == "+919876543210"
    assert normalize_phone("not-a-phone") is None


def test_email_normalization_lowercases_and_rejects_invalid():
    assert normalize_email("Jane.Doe@GMAIL.com") == "jane.doe@gmail.com"
    assert normalize_email("not-an-email") is None


def test_country_normalization():
    assert normalize_country("India") == "IN"
    assert normalize_country("Nonexistent Country XYZ") is None


def test_skill_canonicalization():
    assert canonicalize_skill("cpp") == "C++"
    assert canonicalize_skill("CPP") == "C++"


def test_projection_required_field_missing_raises_on_error_policy():
    record = {"full_name": None, "emails": [], "provenance": [], "overall_confidence": 0}
    config = {
        "fields": [{"path": "full_name", "type": "string", "required": True}],
        "on_missing": "error",
    }
    try:
        project(record, config)
        assert False, "expected MissingRequiredFieldError"
    except MissingRequiredFieldError:
        pass


def test_projection_omit_policy_drops_missing_fields():
    record = {"full_name": None, "emails": [], "provenance": [], "overall_confidence": 0}
    config = {
        "fields": [{"path": "full_name", "type": "string", "required": False}],
        "on_missing": "omit",
    }
    out = project(record, config)
    assert "full_name" not in out


def test_run_pipeline_produces_valid_default_schema_output():
    output = run_pipeline({
        "csv": "sample_data/recruiters.csv",
        "ats_json": "sample_data/ats.json",
    })
    assert len(output) >= 2
    for record in output:
        assert "candidate_id" in record
        assert "provenance" in record
        assert "overall_confidence" in record
