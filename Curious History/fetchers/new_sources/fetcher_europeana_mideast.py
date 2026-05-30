"""
fetcher_europeana_mideast.py — Europeana: Middle East, Islamic & Global Expansion

Extends the existing Europeana fetcher with a focused set of queries for the
Middle East, Islamic civilisation, and other under-represented regions.

Endpoint : https://api.europeana.eu/record/v2/search.json
Auth     : Free API key (EUROPEANA_API_KEY env var, default: oadoncen)
License  : CC0 / Public Domain — commercial OK
Coverage : Middle East, Ottoman, Islamic, Central Asia, East Africa
"""

import json
import os
import time
import requests
from db import insert_record
from fetchers.new_sources.era_utils import infer_era as _infer_topic_era

SOURCE_NAME = "Europeana Middle East & Global"
API_BASE    = "https://api.europeana.eu/record/v2/search.json"
PAGE_SIZE   = 100
MAX_PER_QUERY = 200
API_KEY     = os.environ.get("EUROPEANA_API_KEY", "oadoncen")

HEADERS = {
    "User-Agent": (
        "CuriousHistory/1.0 "
        "(https://curioushistory.vercel.app; himanks897@gmail.com)"
    ),
}

# Middle East, Islamic, and global topics missing from base Europeana fetcher
TOPICS = [
    # Middle East core
    "Ottoman history Istanbul",
    "Ottoman Empire Balkans",
    "Ottoman Empire Arabia",
    "Mamluk Egypt history",
    "Fatimid Caliphate",
    "Umayyad Caliphate Damascus",
    "Abbasid Baghdad history",
    "Crusades Jerusalem history",
    "Saladin history",
    "Islamic art manuscripts",
    # Iran / Persia
    "Safavid Iran history",
    "Persian empire Achaemenid",
    "Qajar dynasty Iran",
    # Arabian Peninsula
    "Arabian Peninsula history",
    "Mecca Medina history",
    "Yemen history ancient",
    # Levant
    "Syria Lebanon history Ottoman",
    "Palestine history British Mandate",
    "Phoenicia ancient history",
    # Central Asia
    "Timurid Central Asia history",
    "Mongol Empire Persia",
    "Silk Road Central Asia",
    # East Africa / Horn
    "Ethiopia Abyssinia history",
    "Swahili coast history",
    "Somalia history ancient",
    # North Africa beyond Egypt
    "Maghreb North Africa history",
    "Carthage history ancient",
    "Algeria French colonial",
    # Additional Asia
    "India British Raj history",
    "Indian Ocean trade history",
    "Java Majapahit history",
]


def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val).strip()


def _region(topic: str, country: str) -> str:
    t = (topic + " " + country).lower()
    if any(k in t for k in ["ottoman", "turkey", "iraq", "syria", "arabia",
                             "iran", "persia", "egypt", "levant", "palestine",
                             "crusade", "safavid", "fatimid", "mamluk",
                             "abbasid", "umayyad", "islamic", "yemen",
                             "mecca", "medina", "arab"]):
        return "Middle East"
    if any(k in t for k in ["ethiopia", "swahili", "somalia", "africa",
                             "maghreb", "algeria", "carthage"]):
        return "Africa"
    if any(k in t for k in ["central asia", "timurid", "mongol", "silk road"]):
        return "Central Asia"
    if any(k in t for k in ["india", "mughal", "raj"]):
        return "India"
    if any(k in t for k in ["java", "indonesia", "southeast asia"]):
        return "Southeast Asia"
    return country.title() if country else "Global"


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    seen_ids: set = set()

    for topic in TOPICS:
        query_inserted = 0
        cursor = "*"

        while query_inserted < MAX_PER_QUERY:
            params = {
                "wskey":   API_KEY,
                "query":   topic,
                "rows":    PAGE_SIZE,
                "profile": "minimal",
            }
            if cursor and cursor != "*":
                params["cursor"] = cursor
            else:
                params["start"] = 1

            try:
                resp = requests.get(API_BASE, params=params,
                                    headers=HEADERS, timeout=30)
            except requests.RequestException as e:
                print(f"  [EU-ME] Request error '{topic}': {e}")
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
                item_id = str(item.get("id") or "").strip("/")
                if not item_id or item_id in seen_ids:
                    continue

                title = _safe_str(item.get("title") or item.get("dcTitle") or [])
                if not title:
                    continue

                country_val = _safe_str(item.get("country") or [])
                region = _region(topic, country_val)

                desc    = _safe_str(item.get("dcDescription") or [])[:500]
                date_v  = _safe_str(item.get("year") or item.get("dcDate") or [])[:20]
                preview = item.get("edmPreview") or []
                img_url = str(preview[0]) if preview else ""
                src_url = str(item.get("guid") or f"https://www.europeana.eu/item/{item_id}")
                subj    = item.get("dcSubject") or []
                tags    = json.dumps(["Europeana", topic, region]
                                     + [str(s)[:60] for s in (subj[:4] if isinstance(subj, list) else [])])

                seen_ids.add(item_id)
                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     desc or None,
                    "image_url":   img_url or None,
                    "source_url":  src_url,
                    "external_id": f"eu-me-{item_id.replace('/', '-')}",
                    "date_text":   date_v,
                    "record_type": "image" if item.get("type") == "IMAGE" else "document",
                    "tags":        tags,
                    "region":      region,
                    "era":         _infer_topic_era(f"{topic} {region}"),
                })
                if ok:
                    inserted      += 1
                    query_inserted += 1

            cursor = data.get("nextCursor") or ""
            if not cursor or len(items) < PAGE_SIZE or query_inserted >= MAX_PER_QUERY:
                break
            time.sleep(0.5)

        if query_inserted:
            print(f"  [EU-ME] '{topic[:35]}' +{query_inserted}")
        time.sleep(0.4)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
