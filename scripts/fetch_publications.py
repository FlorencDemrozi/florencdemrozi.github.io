#!/usr/bin/env python3
"""
fetch_publications.py
─────────────────────────────────────────────────────────────────
Updates _data/publications.yml from OpenAlex (https://openalex.org),
using the author's ORCID. OpenAlex is a free, open scholarly index
that allows automated access (Google Scholar blocks CI servers).

Usage:
  python scripts/fetch_publications.py                   # publications only
  python scripts/fetch_publications.py --collaborations  # also rebuild _data/collaborations.json

Dependencies:
  pip install pyyaml

Merge rules:
  - Hand-curated entries (ids starting with C, J, B, P, T) are kept as
    written; only a missing DOI is filled in.
  - Auto-generated entries (old Scholar "S..." ids and OpenAlex "W..." ids)
    are refreshed from OpenAlex (type, venue, year, authors, DOI).
  - Entries not found in OpenAlex are kept.
  - Duplicates (same DOI or same normalised title) are removed,
    preferring the hand-curated entry.

GitHub Actions runs this weekly (see .github/workflows/update_publications.yml).
─────────────────────────────────────────────────────────────────
"""

import copy
import datetime
import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

import yaml

# ── CONFIG ────────────────────────────────────────────────────
ORCID      = "0000-0002-5422-9826"
SCHOLAR_ID = "gF5XNDIAAAAJ"
REPO_ROOT  = Path(__file__).parent.parent
PUBS_FILE  = REPO_ROOT / "_data" / "publications.yml"
API        = "https://api.openalex.org/works"
# C/J/B/P/T (and old E) ids = hand-curated: never overwritten here
CURATED_PREFIXES = ("C", "J", "B", "P", "T", "E")
USER_AGENT = "florencdemrozi.github.io publication updater (https://florencdemrozi.github.io)"
SELECT = "id,doi,title,publication_year,type,primary_location,authorships,cited_by_count"


def norm_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"^\s*editorial\s*:\s*", "", t)
    return re.sub(r"[^a-z0-9]", "", t)


JUNK_TITLES = re.compile(r"protected by copyright|all rights reserved", re.I)


def find_fuzzy(title: str, fetched: list, year=None, cutoff: float = 0.86):
    """Closest title above `cutoff`. When the year is known, only papers from the
    same or a neighbouring year count, so a conference paper and its later
    journal extension (similar titles) are not merged into one entry."""
    key = norm_title(title)
    best, best_r = None, cutoff
    for f in fetched:
        if year and f.get("year") and abs(int(year) - int(f["year"])) > 1:
            continue
        r = difflib.SequenceMatcher(None, key, norm_title(f["title"])).ratio()
        if r >= best_r:
            best, best_r = f, r
    return best


def norm_doi(doi: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", (doi or "").strip(), flags=re.I).lower()


# surname particles: "Silvia Del Din" -> "Del Din S.", "Jan van der Berg" -> "van der Berg J."
PARTICLES = {"da", "dal", "dalla", "de", "dei", "del", "della", "der", "di", "do", "dos", "du",
             "la", "le", "van", "von", "ter", "ten", "zu"}


def short_name(display_name: str) -> str:
    """'Ruggero Angelo Bacchin' -> 'Bacchin R.A.'; Demrozi -> 'Demrozi F.'"""
    parts = (display_name or "").replace(".", ". ").split()
    if not parts:
        return ""
    if len(parts) > 1 and parts[-1].isupper() and len(parts[-1]) > 2:
        parts[-1] = parts[-1].title()
    cut = len(parts) - 1          # surname starts at the last word, plus any particles before it
    while cut > 1 and parts[cut - 1].lower() in PARTICLES:
        cut -= 1
    last = " ".join(parts[cut:])
    initials = "".join(p[0].upper() + "." for p in parts[:cut] if p[0].isalpha())
    name = f"{last} {initials}".strip()
    return "Demrozi F." if last.lower() == "demrozi" else name


def map_type(work: dict) -> str:
    t = work.get("type") or ""
    src_type = (((work.get("primary_location") or {}).get("source") or {}).get("type") or "")
    if t == "dataset":
        return "dataset"
    if t == "preprint":
        return "preprint"
    if t in ("book", "book-chapter"):
        return "book"
    if t == "dissertation":
        return "thesis"
    if t == "conference-paper" or src_type == "conference":
        return "conference"
    if src_type == "book series":
        return "conference"
    return "journal"


def http_json(url: str) -> dict:
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt + 1} failed: {e}")
            time.sleep(5 * (attempt + 1))
    print(f"ERROR: could not reach OpenAlex ({url.split('?')[0]}). Nothing was changed.")
    sys.exit(1)


def fetch_openalex() -> list:
    works, cursor = [], "*"
    while cursor:
        url = (f"{API}?filter=author.orcid:{ORCID}&per-page=200"
               f"&select={SELECT}&cursor={cursor}")
        data = http_json(url)
        works += data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")
        if not data.get("results"):
            break
    print(f"  Found {len(works)} works on OpenAlex")
    return works


def to_entry(work: dict) -> dict:
    src = ((work.get("primary_location") or {}).get("source") or {})
    # OpenAlex drops apostrophes: "Parkinson s Disease" -> "Parkinson's Disease"
    venue = re.sub(r"(?<=[A-Za-z]) s (?=[A-Z])", "'s ", src.get("display_name") or "")
    authors = ", ".join(short_name((a.get("author") or {}).get("display_name", ""))
                        for a in work.get("authorships", []))
    year = work.get("publication_year")
    if not year:
        return None
    entry = {
        "id": "W" + work["id"].rsplit("/W", 1)[-1],
        "type": map_type(work),
        "year": int(year),
        "year_str": str(year),
        "title": (work.get("title") or "").strip(),
        "authors": authors,
        "venue": venue,
    }
    doi = norm_doi(work.get("doi"))
    if doi:
        entry["doi"] = doi
    return entry


def is_curated(entry: dict) -> bool:
    return str(entry.get("id", "")).startswith(CURATED_PREFIXES)


def merge(existing: list, fetched: list) -> list:
    by_doi = {e["doi"]: e for e in fetched if e.get("doi")}
    by_title = {norm_title(e["title"]): e for e in fetched}
    used = set()
    out, seen = [], set()

    # curated first so they win duplicate checks
    ordered = sorted(existing, key=lambda e: 0 if is_curated(e) else 1)
    for e in ordered:
        if JUNK_TITLES.search(e.get("title", "")):
            continue
        doi = norm_doi(e.get("doi"))
        oa = by_doi.get(doi) if doi else None
        oa = oa or by_title.get(norm_title(e.get("title", "")))
        oa = oa or find_fuzzy(e.get("title", ""), [f for f in fetched if id(f) not in used], e.get("year"))
        if oa:
            used.add(id(oa))
            if is_curated(e):
                if not e.get("doi") and oa.get("doi"):
                    e["doi"] = oa["doi"]
            else:
                keep = {k: e[k] for k in ("award", "url") if e.get(k)}
                e = {**oa, **keep}
        keys = {norm_title(e.get("title", ""))} | ({norm_doi(e.get("doi"))} if e.get("doi") else set())
        if keys & seen:
            continue
        seen |= keys
        out.append(e)

    for oa in fetched:
        if id(oa) in used or not oa["title"] or JUNK_TITLES.search(oa["title"]):
            continue
        keys = {norm_title(oa["title"])} | ({oa["doi"]} if oa.get("doi") else set())
        if keys & seen:
            continue
        seen |= keys
        out.append(oa)

    out.sort(key=lambda x: (-int(x.get("year", 0)), str(x.get("id", ""))))
    return out


def build_openalex_collaborations(works: list):
    """Builds _data/collaborations.json (map, institutions, co-authors, network) from OpenAlex."""
    from collab import build_collaborations, h_index, write_collaborations
    inst_ids = {i["id"] for w in works for a in w.get("authorships", []) for i in a.get("institutions", []) if i.get("id")}
    geo, ids = {}, sorted(inst_ids)
    for k in range(0, len(ids), 50):
        chunk = "|".join(i.rsplit("/", 1)[-1] for i in ids[k:k + 50])
        res = http_json(f"https://api.openalex.org/institutions?filter=openalex_id:{chunk}&per-page=50&select=id,display_name,geo")
        for r in res.get("results", []):
            geo[r["id"]] = r
    self_ids, papers = set(), []
    for w in works:
        authors = []
        for a in w.get("authorships", []):
            au = a.get("author") or {}
            if (au.get("orcid") or "").endswith(ORCID):
                self_ids.add(au.get("id"))
            affs = []
            for i in a.get("institutions", []):
                g = (geo.get(i.get("id")) or {}).get("geo") or {}
                affs.append({"id": i.get("id"), "name": i.get("display_name", ""),
                             "city": g.get("city") or "", "country": g.get("country") or "",
                             "lat": g.get("latitude"), "lon": g.get("longitude")})
            authors.append({"id": au.get("id"), "name": au.get("display_name", ""), "affiliations": affs})
        papers.append({"title": w.get("title") or "", "year": w.get("publication_year") or 0,
                       "citations": w.get("cited_by_count") or 0, "authors": authors})
    cites = [p["citations"] for p in papers]
    profile = {"documents": len(papers), "citations": sum(cites), "h_index": h_index(cites),
               "first_year": min((p["year"] for p in papers if p["year"]), default=None)}
    data = build_collaborations(papers, self_ids, "OpenAlex", profile)
    if not data["coauthors"]:
        print("ERROR: no co-authors found; keeping the existing collaborations.json.")
        sys.exit(1)
    write_collaborations(data)


def main():
    data = {}
    if PUBS_FILE.exists():
        data = yaml.safe_load(PUBS_FILE.read_text(encoding="utf-8")) or {}
    existing = data.get("items", [])
    print(f"Existing entries: {len(existing)}")

    works = fetch_openalex()
    if not works:
        # An empty answer means an OpenAlex problem, not that all papers vanished.
        print("ERROR: OpenAlex returned no works for this ORCID. Nothing was changed.")
        sys.exit(1)
    fetched = [e for e in (to_entry(w) for w in works) if e]
    skipped = len(works) - len(fetched)
    if skipped:
        print(f"  Skipped {skipped} work(s) without a publication year")
    before = copy.deepcopy(existing)   # merge() edits curated entries in place
    merged = merge(existing, fetched)
    print(f"Merged total:     {len(merged)} ({len(merged) - len(existing):+d})")

    if merged == before:
        print("Publications unchanged.")
    else:
        output = {
            "last_updated": datetime.date.today().isoformat(),
            "scholar_url": f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en",
            "items": merged,
        }
        PUBS_FILE.write_text(
            yaml.dump(output, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120),
            encoding="utf-8",
        )
        print(f"Updated {PUBS_FILE}")

    if "--collaborations" in sys.argv:
        build_openalex_collaborations(works)


if __name__ == "__main__":
    main()
