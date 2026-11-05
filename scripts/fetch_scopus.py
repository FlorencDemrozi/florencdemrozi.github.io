#!/usr/bin/env python3
"""
fetch_scopus.py — main publication + collaboration updater (run locally at UiS).

Fetches all documents of the Scopus author profile and updates:
  _data/publications.yml    publication list (Scopus is authoritative)
  _data/collaborations.json countries, institutions, co-authors, network, metrics

Usage (on the UiS network, so Scopus grants full author/affiliation data):
  set the key once per terminal, then run:
    PowerShell:  $env:SCOPUS_API_KEY = "<your key>"
    Git Bash:    export SCOPUS_API_KEY=<your key>
  python scripts/fetch_scopus.py
  git add _data scripts/geo_cache.json && git commit -m "Update from Scopus" && git push

  Alternatively put the key (one line) in scripts/.scopus_key — that file is
  git-ignored and never published. Off-campus, an institutional token can be
  given in SCOPUS_INSTTOKEN.

Dependencies: pip install pyyaml
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from collab import build_collaborations, h_index, write_collaborations  # noqa: E402
from fetch_publications import (  # noqa: E402
    JUNK_TITLES, PUBS_FILE, SCHOLAR_ID, find_fuzzy, is_curated, norm_doi, norm_title,
)

AUTHOR_ID = "57193860991"
API = "https://api.elsevier.com/content"
KEY_FILE = Path(__file__).parent / ".scopus_key"


def api_key() -> str:
    key = os.environ.get("SCOPUS_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        sys.exit("No Scopus API key: set SCOPUS_API_KEY or create scripts/.scopus_key")
    return key


def get(path: str, params: dict) -> dict:
    headers = {"X-ELS-APIKey": api_key(), "Accept": "application/json"}
    if os.environ.get("SCOPUS_INSTTOKEN"):
        headers["X-ELS-Insttoken"] = os.environ["SCOPUS_INSTTOKEN"]
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            if e.code in (401, 403):
                raise PermissionError(f"Scopus refused the request ({e.code}): {body}") from None
            print(f"  HTTP {e.code}, retrying… {body}")
        except Exception as e:  # noqa: BLE001
            print(f"  {e}, retrying…")
        time.sleep(3 * (attempt + 1))
    sys.exit(f"Could not reach Scopus: {path}")


def fetch_documents() -> list:
    docs, start, total = [], 0, None
    while total is None or start < total:
        res = get("search/scopus", {
            "query": f"AU-ID({AUTHOR_ID})", "view": "COMPLETE",
            "count": 25, "start": start, "sort": "-coverDate"})["search-results"]
        total = int(res.get("opensearch:totalResults", 0))
        entries = [e for e in res.get("entry", []) if "error" not in e]
        if not entries:
            break
        docs += entries
        start += len(entries)
    print(f"  Found {len(docs)} documents on Scopus")
    return docs


def fetch_metrics() -> dict:
    try:
        r = get(f"author/author_id/{AUTHOR_ID}", {"view": "METRICS"})["author-retrieval-response"][0]
        core = r.get("coredata", {})
        return {"h_index": int(r.get("h-index", 0)),
                "citations": int(core.get("citation-count", 0)),
                "documents": int(core.get("document-count", 0))}
    except Exception as e:  # noqa: BLE001
        print(f"  (author metrics not available, computing from documents: {e})")
        return {}


def doc_type(d: dict) -> str:
    sub = (d.get("subtypeDescription") or "").lower()
    agg = (d.get("prism:aggregationType") or "").lower()
    if "conference" in sub or "conference" in agg:
        return "conference"
    if sub in ("book chapter", "book") or agg in ("book",):
        return "book"
    return "journal"


def as_list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def to_pub(d: dict) -> dict:
    year = int((d.get("prism:coverDate") or "2000")[:4])
    authors = ", ".join(a.get("authname", "") for a in as_list(d.get("author")))
    if not authors:
        authors = d.get("dc:creator", "")
    entry = {
        "id": "E" + (d.get("eid") or "").split("-")[-1],
        "type": doc_type(d),
        "year": year,
        "year_str": str(year),
        "title": (d.get("dc:title") or "").strip(),
        "authors": authors,
        "venue": d.get("prism:publicationName", ""),
    }
    if d.get("prism:doi"):
        entry["doi"] = norm_doi(d["prism:doi"])
    if d.get("citedby-count"):
        entry["citations"] = int(d["citedby-count"])
    return entry


def to_paper(d: dict) -> dict:
    affs = {a.get("afid"): {
        "id": a.get("afid"), "name": a.get("affilname", ""),
        "city": a.get("affiliation-city") or "", "country": a.get("affiliation-country") or "",
        "lat": None, "lon": None} for a in as_list(d.get("affiliation"))}
    authors = []
    for a in as_list(d.get("author")):
        name = " ".join(x for x in (a.get("given-name"), a.get("surname")) if x) or a.get("authname", "")
        afids = [x.get("$") for x in as_list(a.get("afid"))]
        authors.append({"id": a.get("authid"), "name": name,
                        "affiliations": [affs[x] for x in afids if x in affs]})
    return {"title": d.get("dc:title", ""), "year": int((d.get("prism:coverDate") or "2000")[:4]),
            "citations": int(d.get("citedby-count") or 0), "authors": authors}


def merge(existing: list, scopus: list) -> list:
    """Scopus entries replace auto-generated ones; hand-curated entries are kept
    (gaining DOI/citations); entries Scopus does not know are kept."""
    by_doi = {e["doi"]: e for e in scopus if e.get("doi")}
    by_title = {norm_title(e["title"]): e for e in scopus}
    used, out, seen = set(), [], set()

    def add(e):
        keys = {norm_title(e.get("title", ""))} | ({norm_doi(e["doi"])} if e.get("doi") else set())
        if keys & seen:
            return
        seen.update(keys)
        out.append(e)

    for e in sorted(existing, key=lambda e: 0 if is_curated(e) and not str(e["id"]).startswith("E") else 1):
        if JUNK_TITLES.search(e.get("title", "")):
            continue
        doi = norm_doi(e.get("doi"))
        sc = (by_doi.get(doi) if doi else None) or by_title.get(norm_title(e.get("title", ""))) \
            or find_fuzzy(e.get("title", ""), [s for s in scopus if id(s) not in used])
        if sc and id(sc) not in used:
            used.add(id(sc))
            if is_curated(e) and not str(e["id"]).startswith("E"):
                e.setdefault("doi", sc.get("doi"))
                if sc.get("citations"):
                    e["citations"] = sc["citations"]
                add(e)
            else:
                keep = {k: e[k] for k in ("award", "url") if e.get(k)}
                add({**sc, **keep})
        elif str(e.get("id", "")).startswith("E"):
            continue  # was from Scopus but no longer in the profile
        else:
            add(e)
    for s in scopus:
        if id(s) not in used:
            add(s)
    out.sort(key=lambda x: (-int(x.get("year", 0)), str(x.get("id", ""))))
    return out


def main():
    try:
        docs = fetch_documents()
    except PermissionError as e:
        sys.exit(f"{e}\nAre you on the UiS network (or VPN)? The key needs institutional access.")

    if docs and not any(as_list(d.get("author")) for d in docs):
        print("WARNING: Scopus returned no author lists (COMPLETE view not granted).\n"
              "         Publications will update, collaborations will not. Run on the UiS network.")

    data = yaml.safe_load(PUBS_FILE.read_text(encoding="utf-8")) if PUBS_FILE.exists() else {}
    pubs = [to_pub(d) for d in docs if (d.get("subtypeDescription") or "") != "Erratum"]
    merged = merge(data.get("items", []), pubs)
    PUBS_FILE.write_text(yaml.dump({
        "last_updated": time.strftime("%Y-%m-%d"),
        "source": "Scopus",
        "scholar_url": f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en",
        "items": merged,
    }, allow_unicode=True, default_flow_style=False, sort_keys=False, width=120), encoding="utf-8")
    print(f"Updated {PUBS_FILE}: {len(merged)} publications")

    papers = [to_paper(d) for d in docs]
    if any(p["authors"] for p in papers):
        metrics = fetch_metrics()
        cites = [p["citations"] for p in papers]
        profile = {
            "scopus_id": AUTHOR_ID,
            "documents": metrics.get("documents") or len(docs),
            "citations": metrics.get("citations") or sum(cites),
            "h_index": metrics.get("h_index") or h_index(cites),
            "first_year": min((p["year"] for p in papers), default=None),
        }
        write_collaborations(build_collaborations(papers, {AUTHOR_ID}, "Scopus", profile))


if __name__ == "__main__":
    main()
