"""
Schema Mapping Engine.
Each source has its own field names; this module is the single place
that knows how to translate them into the canonical vocabulary.

Output: a list of (canonical_field, value, source_type, source_name, method)
tuples -- "candidate claims" -- ready for canonicalization/normalization.

Resume now also emits experience_entries and education_entries (structured
dicts) that are assembled into Experience/Education objects in the pipeline.
"""
from typing import List, Tuple, Any
from schemas.canonical import RawRecord

Claim = Tuple[str, Any, str, str, str]  # field, value, source_type, source_name, method


def map_record(record: RawRecord) -> List[Claim]:
    f  = record.fields
    st = record.source_type
    sn = record.source_name
    claims: List[Claim] = []

    def add(field, value, method):
        if value not in (None, "", []):
            claims.append((field, value, st, sn, method))

    if st == "csv":
        add("full_name",       f.get("full_name"),       "CSVParser")
        add("email",           f.get("email"),            "CSVParser")
        add("phone",           f.get("phone"),            "CSVParser")
        add("current_company", f.get("current_company"), "CSVParser")
        add("title",           f.get("title"),            "CSVParser")

    elif st == "ats_json":
        add("full_name",       f.get("candidateName"),   "ATSParser")
        add("email",           f.get("mail"),             "ATSParser")
        add("phone",           f.get("mobile"),           "ATSParser")
        add("current_company", f.get("employer"),         "ATSParser")
        add("title",           f.get("role"),             "ATSParser")

    elif st == "github":
        add("full_name",        f.get("name"),     "GitHubAPI")
        add("headline",         f.get("bio"),      "GitHubAPI")
        # GitHub's `company` field is free-text affiliation (e.g. "@google" or
        # "Stanford University") — it answers a different question than the
        # employer recorded in CSV/ATS.  Map it to a distinct field so it never
        # enters the current_company trust-scoring pool or provenance conflicts.
        add("affiliation_raw",  f.get("company"),  "GitHubAPI")
        add("github_url",       f.get("html_url"), "GitHubAPI")
        add("portfolio",        f.get("blog"),     "GitHubAPI")
        loc = f.get("location")
        if loc:
            add("location_raw", loc, "GitHubAPI")

    elif st == "resume":
        add("full_name",          f.get("full_name"),         "ResumeRegex")
        add("email",              f.get("email"),             "ResumeRegex")
        add("phone",              f.get("phone"),             "ResumeRegex")
        add("linkedin_url",       f.get("linkedin_url"),      "ResumeRegex")
        add("github_url",         f.get("github_url"),        "ResumeRegex")
        add("years_experience",   f.get("years_experience"), f.get("years_experience_method", "ResumeHeuristic"))
        for skill in f.get("skills") or []:
            add("skill", skill, "ResumeKeywordScan")
        # Structured blocks (assembled into Experience/Education in pipeline)
        for exp in f.get("experience") or []:
            add("experience_entry", exp, "ResumeParser")
        for edu in f.get("education") or []:
            add("education_entry", edu, "ResumeParser")

    elif st == "notes":
        add("email", f.get("email"), "NotesRegex")
        add("phone", f.get("phone"), "NotesRegex")
        for skill in f.get("skills") or []:
            add("skill", skill, "NotesKeywordScan")

    return claims
