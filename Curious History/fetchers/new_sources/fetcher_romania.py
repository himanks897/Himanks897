"""
fetcher_romania.py — Romanian / Eastern European history via Europeana

Uses the Europeana API filtered by COUNTRY:romania to surface
digitised records from Romanian cultural institutions.
Broadened with Balkan and Eastern European topics for context.

Endpoint: https://api.europeana.eu/record/v2/search.json
API key:  oadoncen  (loaded from .env as EUROPEANA_API_KEY)
Licence:  Public Domain / CC0 — commercial OK
"""

import json
import os
import time
import requests

from db import insert_record

SOURCE_NAME = "Europeana Romania"
API_BASE    = "https://api.europeana.eu/record/v2/search.json"
PAGE_SIZE   = 100
MAX_PER_QUERY = 200

API_KEY = os.environ.get("EUROPEANA_API_KEY", "oadoncen")

_HEADERS = {
    "User-Agent": (
        "CuriousHistory/1.0 "
        "(https://github.com/himanksangtani/curious-history; "
        "himanks897@gmail.com) python-requests/2.x"
    ),
}

TOPICS = [
    "Romanian history",
    "Romania history",
    "Transylvania history",
    "Moldavia history",
    "Wallachia history",
    "Vlad III history",
    "Ottoman Romania",
    "Romanian revolution 1989",
    "communist Romania",
    "Dacian history",
    "Roman Dacia",
    "Romanian independence",
    "Bucharest history",
    "Romanian Orthodox Church history",
    "Carpathian history",
    "World War II Romania",
    "Byzantine influence Romania",
    "Romanian folk culture",
    "Balkan history",
    "Eastern European history",
]

# Country codes for Europeana qf filter
_COUNTRIES = ["romania", "bulgaria", "serbia", "moldova"]


def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val).strip()


def _fetch_country_topic(topic: str, country: str,
                         seen_ids: set, conn: dict,
                         source_id: int) -> int:
    """Fetch one (topic, country) combination from Europeana."""
    inserted = 0
    start    = 1

    while inserted < MAX_PER_QUERY // len(TOPICS) + 10:
        params: dict = {
            "wskey":  API_KEY,
            "query":  topic,
            "qf":     f"COUNTRY:{country}",
            "rows":   PAGE_SIZE,
            "start":  start,
            "profile": "minimal",
        }
        try:
            resp = requests.get(API_BASE, params=params,
                                headers=_HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"  [RO] Request error '{topic}/{country}': {e}")
            break

        if resp.status_code != 200:
            break

        try:
            data = resp.json()
        except ValueError:
            break

        if not data.get("success"):
            break

        items = data.get("items") or []
        if not items:
            break

        for item in items:
            try:
                item_id = str(item.get("id") or "").strip("/")
                if not item_id or item_id in seen_ids:
                    continue

                title = _safe_str(item.get("title") or item.get("dcTitle") or []).strip()
                if not title:
                    continue

                desc      = item.get("dcDescription") or []
                summary   = _safe_str(desc)[:600]
                year_list = item.get("year") or item.get("dcDate") or []
                date_text = _safe_str(year_list)[:20]
                previews  = item.get("edmPreview") or []
                image_url = str(previews[0]) if previews else ""
                guid      = item.get("guid") or ""
                src_url   = str(guid) if guid else f"https://www.europeana.eu/item/{item_id}"
                provider  = _safe_str(item.get("dataProvider") or "")[:60]

                tag_list  = ["Romania", "Europeana Romania", topic, country.title()]
                if provider:
                    tag_list.append(provider)
                tags = json.dumps(tag_list)

                rtype = "image" if item.get("type") == "IMAGE" else "document"

                seen_ids.add(item_id)
                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     summary or None,
                    "image_url":   image_url or None,
                    "source_url":  src_url,
                    "external_id": f"eu-ro-{item_id.replace('/', '-')}",
                    "date_text":   date_text,
                    "record_type": rtype,
                    "tags":        tags,
                    "region":      country.title(),
                    "era":         "Eastern European History",
                })
                if ok:
                    inserted += 1

            except Exception as e:
                print(f"  [RO] Skipping item: {e}")
                continue

        start += PAGE_SIZE
        if len(items) < PAGE_SIZE or start > 500:
            break
        time.sleep(0.3)

    return inserted


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    # Rotate through (topic, country) pairs — primary country = romania
    for topic in TOPICS:
        n = _fetch_country_topic(topic, "romania", seen_ids, conn, source_id)
        if n:
            print(f"  [RO] '{topic[:40]}' +{n} (total: {inserted + n})")
        inserted += n
        time.sleep(0.4)

    # Secondary Balkan countries — one pass with broad query
    broad_topics = ["history", "medieval history", "Ottoman", "Byzantine"]
    for country in _COUNTRIES[1:]:   # skip romania, already done
        for topic in broad_topics:
            n = _fetch_country_topic(topic, country, seen_ids, conn, source_id)
            inserted += n
        time.sleep(0.3)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
