"""
collab.py — builds _data/collaborations.json from a list of papers.

fetch_publications.py --collaborations (OpenAlex) converts its records to the
shape below and calls build_collaborations().

Paper shape:
    {
      "title": str, "year": int, "citations": int,
      "authors": [
        {"id": str, "name": "Given Surname",
         "affiliations": [{"id": str, "name": str, "city": str,
                           "country": str, "lat": float|None, "lon": float|None}]}
      ]
    }
"""

import datetime
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
COLLAB_FILE = REPO_ROOT / "_data" / "collaborations.json"
GEO_CACHE = REPO_ROOT / "scripts" / "geo_cache.json"

# Affiliations treated as "home" (not shown as partner institutions).
HOME_PATTERNS = [r"university of stavanger", r"universitetet i stavanger"]
# Papers with more authors than this are left out of collaboration stats
# (large consortia), as in UiS Researcher Atlas.
MAX_AUTHORS = 50
# Co-author <-> co-author links are only drawn for papers up to this size,
# otherwise one big paper turns the graph into a hairball.
MAX_AUTHORS_FOR_LINKS = 20
# OpenStreetMap's usage policy asks for a User-Agent that identifies the application.
USER_AGENT = "florencdemrozi.github.io collaboration map (https://florencdemrozi.github.io)"


def is_home(aff_name: str) -> bool:
    return any(re.search(p, (aff_name or "").lower()) for p in HOME_PATTERNS)


# ── geocoding (city level, cached) ─────────────────────────────
def _load_cache() -> dict:
    if GEO_CACHE.exists():
        return json.loads(GEO_CACHE.read_text(encoding="utf-8"))
    return {}


def geocode(city: str, country: str, cache: dict):
    """City-level coordinates from OpenStreetMap Nominatim, cached on disk."""
    key = f"{city}|{country}".lower()
    if key in cache:
        return cache[key]
    q = ", ".join(x for x in (city, country) if x)
    if not q:
        return None
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
        val = [round(float(res[0]["lat"]), 4), round(float(res[0]["lon"]), 4)] if res else None
    except Exception as e:  # noqa: BLE001
        print(f"  geocode failed for {q}: {e}")
        return None
    cache[key] = val
    time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
    return val


# ── main builder ───────────────────────────────────────────────
def name_key(name: str) -> str:
    """'Graziano  Pravadelli' / 'GRAZIANO PRAVADELLI' -> 'graziano pravadelli' (accents removed)."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]+", " ", n.lower()).strip()


def build_collaborations(papers: list, self_ids: set, source: str, profile: dict) -> dict:
    papers = [p for p in papers if 1 < len(p["authors"]) <= MAX_AUTHORS]
    # One person can appear under several ids (a missing OpenAlex id, or OpenAlex
    # splitting one person into two profiles). Merge co-authors by normalised name;
    # the id seen on most papers wins.
    id_count = Counter(a["id"] for p in papers for a in p["authors"] if a.get("id"))
    canon = {}
    for aid, _ in id_count.most_common():
        name = next(a.get("name", "") for p in papers for a in p["authors"] if a.get("id") == aid)
        canon.setdefault(name_key(name), aid)
    for p in papers:
        seen = set()
        for a in p["authors"]:
            if a.get("id") in self_ids:
                continue
            key = name_key(a.get("name", ""))
            a["id"] = canon.get(key) or a.get("id") or "name:" + key
        # the same person listed twice on one paper counts once
        p["authors"] = [a for a in p["authors"] if not (a["id"] in seen or seen.add(a["id"]))]
    cache = _load_cache()
    cache_before = dict(cache)

    coauthor_papers = Counter()
    coauthor_name = {}
    coauthor_affs = defaultdict(list)      # id -> [(year, aff)]
    inst = {}                              # aff id -> info
    inst_papers = defaultdict(set)
    inst_people = defaultdict(set)
    country_papers = defaultdict(set)
    country_people = defaultdict(set)
    pair_weight = Counter()

    for idx, p in enumerate(papers):
        others = [a for a in p["authors"] if a["id"] not in self_ids]
        for a in others:
            coauthor_papers[a["id"]] += 1
            coauthor_name.setdefault(a["id"], a["name"])
            for aff in a.get("affiliations", []):
                coauthor_affs[a["id"]].append((p.get("year", 0), aff))
                if is_home(aff.get("name")):
                    continue
                aid = aff.get("id") or aff.get("name")
                inst.setdefault(aid, aff)
                inst_papers[aid].add(idx)
                inst_people[aid].add(a["id"])
                if aff.get("country"):
                    country_papers[aff["country"]].add(idx)
                    country_people[aff["country"]].add(a["id"])
        if len(p["authors"]) <= MAX_AUTHORS_FOR_LINKS:
            ids = sorted({a["id"] for a in others})
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pair_weight[(ids[i], ids[j])] += 1

    # each co-author's main affiliation = most recent one
    coauthors = []
    for cid, n in coauthor_papers.most_common():
        affs = sorted(coauthor_affs[cid], key=lambda x: -x[0])
        aff = affs[0][1] if affs else {}
        coauthors.append({
            "id": cid,
            "name": coauthor_name[cid],
            "institution": aff.get("name", ""),
            "country": aff.get("country", ""),
            "home": is_home(aff.get("name")),
            "papers": n,
        })
    names = {c["id"]: c["name"] for c in coauthors}

    institutions = []
    for aid, aff in inst.items():
        lat, lon = aff.get("lat"), aff.get("lon")
        if lat is None or lon is None:
            ll = geocode(aff.get("city", ""), aff.get("country", ""), cache)
            if ll:
                lat, lon = ll
        people = sorted(inst_people[aid], key=lambda c: (-coauthor_papers[c], names[c]))  # stable order
        institutions.append({
            "name": aff.get("name", ""),
            "city": aff.get("city", ""),
            "country": aff.get("country", ""),
            "lat": lat, "lon": lon,
            "papers": len(inst_papers[aid]),
            "people": [names[c] for c in people],
        })
    institutions.sort(key=lambda x: (-x["papers"], x["name"]))

    countries = sorted(
        ({"name": c, "papers": len(v), "people": len(country_people[c])} for c, v in country_papers.items()),
        key=lambda x: (-x["papers"], x["name"]))

    links = [{"source": a, "target": b, "weight": w} for (a, b), w in pair_weight.items()]

    if cache != cache_before:
        GEO_CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return {
        "updated": datetime.date.today().isoformat(),
        "source": source,
        "profile": profile,
        "papers_counted": len(papers),
        "countries": countries,
        "institutions": institutions,
        "coauthors": coauthors,
        "links": links,
    }


def write_collaborations(data: dict):
    summary = (f"{len(data['coauthors'])} co-authors, {len(data['institutions'])} institutions, "
               f"{len(data['countries'])} countries")
    if COLLAB_FILE.exists():  # keep the old date (and file) when nothing else changed
        old = json.loads(COLLAB_FILE.read_text(encoding="utf-8"))
        if {**old, "updated": None} == {**data, "updated": None}:
            print(f"Collaborations unchanged ({summary}).")
            return
    COLLAB_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Updated {COLLAB_FILE}: {summary}")


def h_index(citations: list) -> int:
    c = sorted((x or 0 for x in citations), reverse=True)
    return sum(1 for i, v in enumerate(c, 1) if v >= i)
