"""
Parser for a GitHub profile, given a username or profile URL.
Uses the public REST API (no auth needed for public profiles, but
subject to rate limiting -- failures degrade gracefully to an empty
record rather than crashing the run).
"""
import re
from typing import List, Optional
import requests
from schemas.canonical import RawRecord


def _extract_username(url_or_username: str) -> Optional[str]:
    m = re.search(r"github\.com/([A-Za-z0-9_-]+)", url_or_username)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", url_or_username.strip()):
        return url_or_username.strip()
    return None


def parse_github(url_or_username: str, timeout: float = 5.0) -> List[RawRecord]:
    username = _extract_username(url_or_username)
    if not username:
        return []

    warnings = []
    fields = {"login": username}
    try:
        resp = requests.get(f"https://api.github.com/users/{username}", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            fields.update({
                "name": data.get("name"),
                "bio": data.get("bio"),
                "company": data.get("company"),
                "blog": data.get("blog"),
                "location": data.get("location"),
                "public_repos": data.get("public_repos"),
                "html_url": data.get("html_url"),
            })
        else:
            warnings.append(f"github api returned status {resp.status_code}")
    except requests.RequestException as e:
        warnings.append(f"github api unreachable: {e}")

    return [RawRecord(
        source_type="github",
        source_name=f"github_{username}",
        fields=fields,
        warnings=warnings,
    )]
