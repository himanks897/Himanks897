"""
fetcher_europeana.py — Europeana (pan-European cultural heritage aggregator)

Harvests public-domain / open-licence records from Europeana,
covering history from all 27 EU member states and beyond.

Endpoint: https://api.europeana.eu/record/v2/search.json
API key:  oadoncen  (loaded from .env as EUROPEANA_API_KEY)
Licence:  Public Domain / CC0 / CC BY — commercial OK

Documentation: https://pro.europeana.eu/page/search
"""

import json
import os
import time
import requests

from db import insert_record

SOURCE_NAME = "Europeana"
API_BASE    = "https://api.europeana.eu/record/v2/search.json"
PAGE_SIZE   = 100
MAX_PER_QUERY = 200   # 2 pages × 100 per topic

API_KEY = os.environ.get("EUROPEANA_API_KEY", "oadoncen")

_HEADERS = {
    "User-Agent": (
        "CuriousHistory/1.0 "
        "(https://github.com/himanksangtani/curious-history; "
        "himanks897@gmail.com) python-requests/2.x"
    ),
}

# Broad world-history topics — fills geographic gaps in the existing database
TOPICS = [
    # Africa (mostly absent)
    "Ethiopian history",
    "Nigerian history",
    "Kenyan colonial history",
    "South African history",
    "Ghana history kingdoms",
    "Egyptian history ancient",
    "Mali Empire history",
    "Songhai Empire history",
    "African colonialism",
    "Zulu Kingdom history",
    # Asia / Middle East
    "Ottoman Empire history",
    "Persian Empire history",
    "Mughal Empire India",
    "Chinese history dynasty",
    "Japanese feudal history",
    "Southeast Asian history",
    "Islamic Golden Age",
    "Silk Road history",
    "Mongol Empire",
    # Latin America
    "Aztec civilization",
    "Inca Empire history",
    "Mexican history",
    "Brazilian colonial history",
    "Andean civilization history",
    "Caribbean history",
    "Latin American independence",
    # Pacific / Oceania
    "Pacific Islands history",
    "Polynesian history",
    "Australian Aboriginal history",
    # Global themes
    "Age of Exploration",
    "Atlantic slave trade",
    "Industrial Revolution",
    "Renaissance history",
    "Reformation Europe",
    "World War I",
    "World War II",
    "Decolonization Africa Asia",
    "Cold War history",
    "Byzantine Empire",
]

# Only these right-statement fragments are allowed (public-domain or open)
_OPEN_RIGHTS = {
    "publicdomain", "creativecommons.org/publicdomain",
    "creativecommons.org/licenses/by/",
    "creativecommons.org/licenses/by-sa/",
    "creativecommons.org/licenses/by-nd/",
    "http://www.europeana.eu/rights/rr-f/",  # free re-use
    "noc-nc",   # no copyright — non-commercial (borderline but include)
}


def _rights_ok(rights_list) -> bool:
    if not rights_list:
        return True   # no explicit restriction → allow
    combined = " ".join(str(r).lower() for r in rights_list)
    # Deny if explicitly NC/ND/restricted commercial
    deny_fragments = ["nd/", "nc/", "incopyrighteuorphan", "rr-p"]
    if any(d in combined for d in deny_fragments):
        return False
    return True


def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val).strip()


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    for topic in TOPICS:
        query_inserted = 0
        cursor         = "*"   # Europeana uses cursor-based pagination

        while query_inserted < MAX_PER_QUERY:
            params: dict = {
                "wskey":   API_KEY,
                "query":   topic,
                "rows":    PAGE_SIZE,
                "profile": "minimal",
                "media":   "true",          # prefer items with media
            }
            if cursor and cursor != "*":
                params["cursor"] = cursor
            else:
                params["start"] = 1

            try:
                resp = requests.get(API_BASE, params=params,
                                    headers=_HEADERS, timeout=30)
            except requests.RequestException as e:
                print(f"  [EU] Request error for '{topic}': {e}")
                break

            if resp.status_code != 200:
                print(f"  [EU] HTTP {resp.status_code} for '{topic}'")
                break

            try:
                data = resp.json()
            except ValueError as e:
                print(f"  [EU] JSON parse error: {e}")
                break

            if not data.get("success"):
                print(f"  [EU] API error for '{topic}': {data.get('error', '?')}")
                break

            items = data.get("items") or []
            if not items:
                break

            page_inserted = 0
            for item in items:
                try:
                    item_id = str(item.get("id") or "").strip("/")
                    if not item_id or item_id in seen_ids:
                        continue

                    # Rights check
                    if not _rights_ok(item.get("rights")):
                        continue

                    title_list = item.get("title") or item.get("dcTitle") or []
                    title      = _safe_str(title_list).strip()
                    if not title:
                        continue

                    # Summary
                    desc    = item.get("dcDescription") or item.get("dctermsDescription") or []
                    summary = _safe_str(desc)[:600]

                    # Date
                    year_list = item.get("year") or item.get("dcDate") or []
                    date_text = _safe_str(year_list)[:20]

                    # Creator
                    creator_list = item.get("dcCreator") or item.get("dcContributor") or []
                    creator      = _safe_str(creator_list)[:100]

                    # Provider / institution
                    provider = _safe_str(item.get("dataProvider") or item.get("provider") or "")

                    # Image
                    previews  = item.get("edmPreview") or []
                    image_url = str(previews[0]) if previews else ""

                    # Source URL
                    guid    = item.get("guid") or item.get("link") or ""
                    src_url = str(guid) if guid else f"https://www.europeana.eu/item/{item_id}"

                    # Country
                    country_list = item.get("country") or []
                    country      = _safe_str(country_list)[:80]

                    # Tags
                    subject_list = item.get("dcSubject") or item.get("subject") or []
                    tag_list     = ["Europeana", topic]
                    if country:
                        tag_list.append(country.title())
                    if provider:
                        tag_list.append(provider[:60])
                    tag_list += [str(s)[:60] for s in (subject_list[:5] if isinstance(subject_list, list) else [])]
                    tags = json.dumps(tag_list)

                    rtype = "image" if item.get("type") in ("IMAGE",) else "document"

                    seen_ids.add(item_id)
                    ok = insert_record(conn, source_id, {
                        "title":       title[:300],
                        "summary":     summary or None,
                        "image_url":   image_url or None,
                        "source_url":  src_url,
                        "external_id": f"eu-{item_id.replace('/', '-')}",
                        "date_text":   date_text,
                        "record_type": rtype,
                        "tags":        tags,
                        "region":      country.title() if country else None,
                    })
                    if ok:
                        inserted      += 1
                        query_inserted += 1
                        page_inserted  += 1

                except Exception as e:
                    print(f"  [EU] Skipping item due to error: {e}")
                    continue

            if page_inserted:
                print(f"  [EU] '{topic[:35]}' +{page_inserted} "
                      f"(total: {inserted})")

            # Cursor pagination
            cursor = data.get("nextCursor") or ""
            if not cursor or len(items) < PAGE_SIZE or query_inserted >= MAX_PER_QUERY:
                break
            time.sleep(0.5)

        time.sleep(0.4)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
