"""
fetcher_gallica.py — French cultural heritage via Europeana (COUNTRY:france)

Uses the Europeana API filtered by COUNTRY:france to surface records
from French museums, archives and the Bibliothèque nationale de France (BnF).
Over 350,000 records available.

Note: Direct access to gallica.bnf.fr/SRU is IP-blocked; Europeana provides
the same BnF content (and more French institutions) without restrictions.

Endpoint: https://api.europeana.eu/record/v2/search.json
API key:  oadoncen  (from .env EUROPEANA_API_KEY)
Licence:  Public Domain / CC0 / CC BY — commercial OK

Documentation: https://pro.europeana.eu/page/search
"""

import json
import os
import time
import requests

from db import insert_record

SOURCE_NAME   = "BnF Gallica France"
API_BASE      = "https://api.europeana.eu/record/v2/search.json"
PAGE_SIZE     = 100
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
    "French Revolution",
    "Napoleon Bonaparte",
    "French colonial history",
    "Hundred Years War",
    "French Renaissance",
    "French Enlightenment",
    "French medieval history",
    "Paris history",
    "Versailles history",
    "Joan of Arc",
    "French Republic history",
    "Algerian history France",
    "Moroccan history France",
    "Indochina French history",
    "West African history France",
    "Caribbean French history",
    "Franco-Prussian War",
    "World War I France",
    "De Gaulle France",
    "French colonial Africa",
]


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
        start          = 1

        while query_inserted < MAX_PER_QUERY:
            params: dict = {
                "wskey":   API_KEY,
                "query":   topic,
                "qf":      "COUNTRY:france",
                "rows":    PAGE_SIZE,
                "start":   start,
                "profile": "minimal",
            }
            try:
                resp = requests.get(API_BASE, params=params,
                                    headers=_HEADERS, timeout=30)
            except requests.RequestException as e:
                print(f"  [FR] Request error for '{topic}': {e}")
                break

            if resp.status_code != 200:
                print(f"  [FR] HTTP {resp.status_code} for '{topic}'")
                break

            try:
                data = resp.json()
            except ValueError as e:
                print(f"  [FR] JSON parse error: {e}")
                break

            if not data.get("success"):
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

                    tag_list = ["France", "Europeana France", "BnF Gallica", topic]
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
                        "external_id": f"eu-fr-{item_id.replace('/', '-')}",
                        "date_text":   date_text,
                        "record_type": rtype,
                        "tags":        tags,
                        "region":      "France",
                        "era":         "French History",
                    })
                    if ok:
                        inserted      += 1
                        query_inserted += 1
                        page_inserted  += 1

                except Exception as e:
                    print(f"  [FR] Skipping item: {e}")
                    continue

            if page_inserted:
                print(f"  [FR] '{topic[:35]}' s{start} +{page_inserted} "
                      f"(total: {inserted})")

            start += PAGE_SIZE
            if start > 301 or len(items) < PAGE_SIZE or query_inserted >= MAX_PER_QUERY:
                break
            time.sleep(0.4)

        time.sleep(0.3)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
