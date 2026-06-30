"""
Entity Matching.
Groups parsed records into clusters that represent the same real
candidate. Priority: exact email match > exact phone match >
fuzzy name+company match (RapidFuzz) as a fallback only.

Emails/phones are stronger identifiers than names because names
collide far more often (assumption documented in README).
"""
from typing import List, Dict, Any
from rapidfuzz import fuzz
from config.settings import FUZZY_MATCH_THRESHOLD
from normalizer.normalizer import normalize_email, normalize_phone


def _record_keys(record_claims: Dict[str, list]) -> Dict[str, str]:
    """Extract normalized match keys available for one source record's claims."""
    keys = {}
    emails = [v for (f, v) in record_claims if f == "email"]
    phones = [v for (f, v) in record_claims if f == "phone"]
    names = [v for (f, v) in record_claims if f == "full_name"]
    companies = [v for (f, v) in record_claims if f == "current_company"]

    if emails:
        norm = normalize_email(emails[0])
        if norm:
            keys["email"] = norm
    if phones:
        norm = normalize_phone(phones[0])
        if norm:
            keys["phone"] = norm
    if names:
        keys["name"] = names[0].strip().lower()
    if companies:
        keys["company"] = companies[0].strip().lower()
    return keys


def cluster_records(per_source_claims: List[List[tuple]]) -> List[List[int]]:
    """
    per_source_claims: list of claim-lists, one per parsed source record.
    Returns: list of clusters, each a list of indices into per_source_claims,
    grouped as belonging to the same candidate.
    """
    keysets = [_record_keys([(f, v) for (f, v, *_rest) in claims])
               for claims in per_source_claims]

    n = len(keysets)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            ki, kj = keysets[i], keysets[j]
            matched = False
            # exact match priority: email, then phone
            if ki.get("email") and kj.get("email") and ki["email"] == kj["email"]:
                matched = True
            elif ki.get("phone") and kj.get("phone") and ki["phone"] == kj["phone"]:
                matched = True
            elif ki.get("name") and kj.get("name"):
                name_score = fuzz.token_sort_ratio(ki["name"], kj["name"])
                company_score = 100
                if ki.get("company") and kj.get("company"):
                    company_score = fuzz.token_sort_ratio(ki["company"], kj["company"])
                if name_score >= FUZZY_MATCH_THRESHOLD and company_score >= 60:
                    matched = True
            if matched:
                union(i, j)

    clusters: Dict[int, List[int]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)
    return list(clusters.values())
