#!/usr/bin/env python3
"""
fetch_students.py
─────────────────────────────────────────────────────────────────
Updates _data/students_nva.yml with the bachelor and master theses
supervised by Florenc Demrozi, taken from NVA (https://nva.sikt.no),
the Norwegian national research archive. Uses NVA's public search API.

Usage:
  python scripts/fetch_students.py

What comes from NVA (automatic):   student name, level, year, thesis link
What comes from _data/students_uis.yml (manual): programme, preferred
  spelling of the name, and students that are not in NVA.

Rules:
  - Only records where Demrozi is listed with the role "Supervisor".
  - Duplicate records of the same thesis are merged: one row per student
    and level (latest year wins).
  - A student is matched to a manual entry when the words of one name are
    all contained in the other (e.g. "Rakul Inthrakumar" matches
    "Rakul Ponnuthurai Inthrakumar"); the manual spelling is then used.
  - If NVA is unreachable or returns nothing, the script exits with an error
    and leaves the existing file untouched.

GitHub Actions runs this weekly (see .github/workflows/update_publications.yml).
─────────────────────────────────────────────────────────────────
"""

import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT   = Path(__file__).parent.parent
OUT_FILE    = REPO_ROOT / "_data" / "students_nva.yml"
MANUAL_FILE = REPO_ROOT / "_data" / "students_uis.yml"
API         = "https://api.nva.unit.no/search/resources"
QUERY       = "Demrozi"
SUPERVISOR  = {"florenc", "demrozi"}
CATEGORIES  = {"DegreeMaster": "M.Sc.", "DegreeBachelor": "B.Sc."}
USER_AGENT  = "florencdemrozi.github.io student list updater (https://florencdemrozi.github.io)"


def tokens(name: str) -> frozenset:
    t = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return frozenset(re.findall(r"[a-z]+", t))


def display_name(raw: str) -> str:
    """'Haland, Katarzyna' -> 'Katarzyna Haland'; trims stray dots and spaces."""
    name = re.sub(r"\s+", " ", raw or "").strip().rstrip(".").strip()
    if "," in name:
        last, first = (p.strip().rstrip(".").strip() for p in name.split(",", 1))
        name = f"{first} {last}"
    return name


def same_person(a: frozenset, b: frozenset) -> bool:
    return bool(a) and bool(b) and (a <= b or b <= a)


def fetch(category: str) -> list:
    hits, start = [], 0
    while True:
        url = f"{API}?query={QUERY}&category={category}&size=100&from={start}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        page = data.get("hits", [])
        hits += page
        start += len(page)
        if not page or start >= data.get("totalHits", 0):
            return hits


def main() -> int:
    manual = yaml.safe_load(MANUAL_FILE.read_text(encoding="utf-8")) if MANUAL_FILE.exists() else []
    manual_names = [(m["name"], tokens(m["name"])) for m in (manual or []) if m.get("name")]

    rows = []  # dicts with name, level, year, title, url, _tok
    try:
        for category, level in CATEGORIES.items():
            for hit in fetch(category):
                desc = hit.get("entityDescription", {})
                contribs = desc.get("contributors", [])
                if not any(c.get("role", {}).get("type") == "Supervisor"
                           and SUPERVISOR <= tokens(c.get("identity", {}).get("name"))
                           for c in contribs):
                    continue
                year = (desc.get("publicationDate") or {}).get("year")
                year = int(year) if str(year or "").isdigit() else None
                title = re.sub(r"\s+", " ", desc.get("mainTitle") or "").strip()
                url = f"https://nva.sikt.no/registration/{hit['identifier']}"
                for c in contribs:
                    if c.get("role", {}).get("type") != "Creator":
                        continue
                    name = display_name(c.get("identity", {}).get("name"))
                    tok = tokens(name)
                    if not tok:
                        continue
                    match = next((m for m, mt in manual_names if same_person(tok, mt)), None)
                    if match:
                        name, tok = match, tokens(match)
                    existing = next((r for r in rows if r["level"] == level and same_person(r["_tok"], tok)), None)
                    if existing is None:
                        rows.append({"name": name, "level": level, "year": year,
                                     "title": title, "url": url, "_tok": tok})
                    else:
                        if len(tok) > len(existing["_tok"]) and not match:
                            existing["name"], existing["_tok"] = name, tok
                        if year and (existing["year"] or 0) < year:
                            existing.update(year=year, title=title, url=url)
    except Exception as e:  # network / API errors: keep the old file
        print(f"ERROR: NVA request failed: {e}", file=sys.stderr)
        return 1

    if not rows:
        print("ERROR: NVA returned no theses; leaving the file unchanged.", file=sys.stderr)
        return 1

    level_order = {"M.Sc.": 0, "B.Sc.": 1}
    rows.sort(key=lambda r: (-(r["year"] or 0), level_order[r["level"]], r["name"]))
    for r in rows:
        del r["_tok"]

    header = ("# AUTO-GENERATED by scripts/fetch_students.py from NVA (nva.sikt.no). Do not edit by hand:\n"
              "# changes are overwritten weekly. Add programmes, name spellings and students\n"
              "# missing from NVA in _data/students_uis.yml instead.\n")
    OUT_FILE.write_text(header + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False, width=1000),
                        encoding="utf-8")
    print(f"Wrote {len(rows)} students to {OUT_FILE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
