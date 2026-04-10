#!/usr/bin/env python3
"""
fetch_publications.py
─────────────────────────────────────────────────────────────────
Fetches publication data from Google Scholar and updates
_data/publications.yml in the Jekyll repository.

Usage:
  python scripts/fetch_publications.py

Dependencies:
  pip install scholarly pyyaml

The script:
1. Fetches all publications from the configured Google Scholar profile
2. Merges with existing hand-curated entries in _data/publications.yml
   (hand-curated entries with matching title are updated, not replaced)
3. Writes the updated YAML back to _data/publications.yml
4. Preserves hand-added fields (doi, url, award, id) for matched entries

GitHub Actions runs this weekly (see .github/workflows/update_publications.yml).
─────────────────────────────────────────────────────────────────
"""

import sys
import os
import yaml
import re
import datetime
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────
SCHOLAR_ID = "gF5XNDIAAAAJ"
REPO_ROOT  = Path(__file__).parent.parent
PUBS_FILE  = REPO_ROOT / "_data" / "publications.yml"

# Mapping of Google Scholar "cites_id" venue patterns → type
TYPE_PATTERNS = {
    "journal": [
        r"IEEE Access", r"IEEE Transactions", r"IEEE Journal", r"IEEE Sensors",
        r"Scientific Data", r"Journal of Parkinson", r"Electronics",
        r"SN Computer Science", r"Computers and Electrical",
        r"Current Opinion", r"Peripheral Nervous System",
    ],
    "conference": [
        r"Conference", r"Workshop", r"Symposium", r"DATE", r"COINS",
        r"EMBC", r"COMPSAC", r"INERTIAL", r"WF-IoT", r"PerCom", r"ICDH",
        r"VLSI", r"HLDVT", r"FDL",
    ],
}


def guess_type(venue: str) -> str:
    """Guess publication type from venue string."""
    if not venue:
        return "conference"
    for pub_type, patterns in TYPE_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, venue, re.IGNORECASE):
                return pub_type
    return "conference"


def normalize_title(title: str) -> str:
    """Normalize title for matching."""
    return re.sub(r'\s+', ' ', title.strip().lower())


def scholar_to_entry(pub, idx: int) -> dict:
    """Convert a scholarly publication to our YAML format."""
    bib = pub.get("bib", {})
    title = bib.get("title", "").strip()
    authors_raw = bib.get("author", "")
    venue = bib.get("venue", "") or bib.get("journal", "") or ""
    year = bib.get("pub_year") or bib.get("year") or "Unknown"

    # Format authors: highlight "Demrozi" entries
    if isinstance(authors_raw, list):
        authors = ", ".join(authors_raw)
    else:
        authors = str(authors_raw)
    # Normalize "Florenc Demrozi" variations → "Demrozi F."
    authors = re.sub(r"Florenc Demrozi|F\. Demrozi|Demrozi, Florenc|Demrozi, F\.",
                     "Demrozi F.", authors, flags=re.IGNORECASE)

    pub_type = guess_type(venue)
    try:
        year_int = int(year)
    except (ValueError, TypeError):
        year_int = 2000

    entry = {
        "id": f"S{idx+1:03d}",
        "type": pub_type,
        "year": year_int,
        "year_str": str(year),
        "title": title,
        "authors": authors,
        "venue": venue,
    }

    # Add DOI if present
    eprint = pub.get("eprint_url") or pub.get("pub_url") or ""
    doi_match = re.search(r"10\.\d{4,}/\S+", eprint)
    if doi_match:
        entry["doi"] = doi_match.group(0).rstrip(".")

    return entry


def load_existing(path: Path) -> dict:
    """Load existing publications YAML."""
    if not path.exists():
        return {"last_updated": "", "scholar_url": "", "items": []}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "items" not in data:
        data["items"] = []
    return data


def merge_entries(existing: list, fetched: list) -> list:
    """
    Merge fetched entries into existing, preserving hand-curated fields.
    Strategy:
    - If a fetched entry title matches an existing entry → update venue/year,
      keep existing id, doi, url, award.
    - New entries (no match) are appended with Scholar-generated IDs.
    - Existing entries with no match in Scholar are kept as-is.
    """
    existing_by_title = {normalize_title(e.get("title", "")): e for e in existing}
    fetched_by_title  = {normalize_title(f.get("title", "")): f for f in fetched}

    merged = []

    # Keep all existing entries, update fields from Scholar where matched
    for entry in existing:
        norm = normalize_title(entry.get("title", ""))
        if norm in fetched_by_title:
            scholar = fetched_by_title[norm]
            # Update only non-critical fields; preserve hand-curated ones
            entry.setdefault("authors", scholar.get("authors", ""))
            if not entry.get("venue") and scholar.get("venue"):
                entry["venue"] = scholar["venue"]
            entry["year"] = scholar.get("year", entry.get("year"))
            entry["year_str"] = str(entry["year"])
        merged.append(entry)

    # Add genuinely new entries (not already in existing)
    for fetch in fetched:
        norm = normalize_title(fetch.get("title", ""))
        if norm not in existing_by_title:
            merged.append(fetch)

    # Sort by year descending, then by id
    merged.sort(key=lambda x: (-int(x.get("year", 0)), x.get("id", "")))
    return merged


def fetch_from_scholar() -> list:
    """Fetch publications from Google Scholar using scholarly."""
    try:
        from scholarly import scholarly as sch
        print(f"Fetching publications for Scholar ID: {SCHOLAR_ID}")
        author = sch.search_author_id(SCHOLAR_ID)
        sch.fill(author, sections=["publications"])
        pubs = author.get("publications", [])
        print(f"  Found {len(pubs)} publications on Scholar")
        entries = []
        for i, pub in enumerate(pubs):
            try:
                sch.fill(pub)
                entry = scholar_to_entry(pub, i)
                if entry["title"]:
                    entries.append(entry)
            except Exception as e:
                print(f"  Warning: could not process publication {i}: {e}")
        return entries
    except ImportError:
        print("ERROR: 'scholarly' package not installed. Run: pip install scholarly")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR fetching from Scholar: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("IEEE COINS / Florenc Demrozi — Publication Fetcher")
    print("=" * 60)

    existing_data = load_existing(PUBS_FILE)
    existing_items = existing_data.get("items", [])
    print(f"Existing entries in YAML: {len(existing_items)}")

    fetched = fetch_from_scholar()
    print(f"Fetched from Scholar:     {len(fetched)}")

    merged = merge_entries(existing_items, fetched)
    print(f"Merged total:             {len(merged)}")

    output = {
        "last_updated": datetime.date.today().isoformat(),
        "scholar_url": f"https://scholar.google.it/citations?user={SCHOLAR_ID}&hl=en",
        "items": merged,
    }

    with open(PUBS_FILE, "w", encoding="utf-8") as f:
        yaml.dump(output, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120)

    print(f"\n✅  Updated {PUBS_FILE}")
    print(f"    Total publications: {len(merged)}")


if __name__ == "__main__":
    main()
