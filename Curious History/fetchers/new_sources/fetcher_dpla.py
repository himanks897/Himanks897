"""
fetcher_dpla.py — DPLA (Digital Public Library of America)

Harvests records from the DPLA, which aggregates millions of primary
sources from US libraries, archives and museums.  Strong coverage of:
  • American history (all eras)
  • African American history
  • Indigenous peoples history
  • Immigration / diaspora communities
  • Women's history

Endpoint: https://api.dp.la/v2/items
API key:  c629af0dca8bf286a311fbd418832320  (loaded from .env as DPLA_API_KEY)
Licence:  Public Domain / CC0 / CC BY — commercial OK

Documentation: https://pro.dp.la/developers/api-codex
"""

import json
import os
import time
import requests

from db import insert_record

SOURCE_NAME  = "DPLA"
API_BASE     = "https://api.dp.la/v2/items"
PAGE_SIZE    = 50
MAX_PER_QUERY = 200

API_KEY = os.environ.get("DPLA_API_KEY", "c629af0dca8bf286a311fbd418832320")

_HEADERS = {
    "User-Agent": (
        "CuriousHistory/1.0 "
        "(https://github.com/himanksangtani/curious-history; "
        "himanks897@gmail.com) python-requests/2.x"
    ),
}

# Topics emphasising underrepresented communities & diverse US history
TOPICS = [
    "American Revolution",
    "Civil War United States",
    "African American history",
    "slavery United States",
    "Reconstruction era",
    "Native American history",
    "Indigenous peoples America",
    "American immigration history",
    "Industrial Revolution America",
    "Great Depression America",
    "Civil Rights Movement",
    "World War II America",
    "Cold War America",
    "American West expansion",
    "Mexican American history",
    "Asian American history",
    "Labor movement America",
    "Womens suffrage America",
    "American colonial history",
    "Harlem Renaissance",
    "Lewis and Clark expedition",
    "American frontier history",
    "Abolitionism America",
    "Underground Railroad",
    "Transcontinental Railroad",
]

# Rights fragments considered open/public domain
_OK_RIGHTS = {
    "publicdomain", "public domain", "no known copyright",
    "creative commons", "creativecommons", "cc0",
    "no copyright", "rights statement", "unrestricted",
}


def _rights_ok(rights: str) -> bool:
    if not rights:
        return True  # no restriction stated — allow
    r = rights.lower()
    # Deny clearly restricted
    if any(d in r for d in ["all rights reserved", "copyright", "©"]):
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
        page           = 1

        while query_inserted < MAX_PER_QUERY:
            params = {
                "api_key":   API_KEY,
                "q":         topic,
                "page_size": PAGE_SIZE,
                "page":      page,
            }
            try:
                resp = requests.get(API_BASE, params=params,
                                    headers=_HEADERS, timeout=25)
            except requests.RequestException as e:
                print(f"  [DPLA] Request error for '{topic}': {e}")
                break

            if resp.status_code == 401:
                print(f"  [DPLA] 401 Unauthorized — check DPLA_API_KEY")
                return inserted
            if resp.status_code != 200:
                print(f"  [DPLA] HTTP {resp.status_code} for '{topic}'")
                break

            try:
                data = resp.json()
            except ValueError as e:
                print(f"  [DPLA] JSON parse error: {e}")
                break

            docs = data.get("docs") or []
            if not docs:
                break

            page_inserted = 0
            for doc in docs:
                try:
                    item_id = str(doc.get("id") or "").strip()
                    if not item_id or item_id in seen_ids:
                        continue

                    sr = doc.get("sourceResource") or {}

                    # Title
                    title = _safe_str(sr.get("title") or "").strip()
                    if not title:
                        continue

                    # Rights
                    rights = _safe_str(sr.get("rights") or "")
                    if not _rights_ok(rights):
                        continue

                    # Description
                    desc    = sr.get("description") or []
                    summary = _safe_str(desc)[:600]

                    # Date — API returns list of dicts or plain string
                    date_raw  = sr.get("date") or []
                    if isinstance(date_raw, list) and date_raw:
                        date_obj  = date_raw[0] if isinstance(date_raw[0], dict) else {}
                        date_text = str(date_obj.get("displayDate") or
                                        date_obj.get("begin") or
                                        date_raw[0] or "")[:20]
                    elif isinstance(date_raw, dict):
                        date_text = str(date_raw.get("displayDate") or
                                        date_raw.get("begin") or "")[:20]
                    else:
                        date_text = str(date_raw)[:20]

                    # Creator
                    creator = _safe_str(sr.get("creator") or "")[:100]

                    # Subjects
                    subjects  = sr.get("subject") or []
                    if isinstance(subjects, list):
                        sub_strs = [str(s.get("name", s) if isinstance(s, dict) else s)[:60]
                                    for s in subjects[:5]]
                    else:
                        sub_strs = [str(subjects)[:60]] if subjects else []

                    # Type
                    types     = sr.get("type") or []
                    type_str  = _safe_str(types).lower()
                    record_type = "image" if "image" in type_str or "photograph" in type_str else "document"

                    # Image URL
                    image_url = str(doc.get("object") or "")

                    # Source URL
                    src_url = str(doc.get("isShownAt") or
                                  f"https://dp.la/item/{item_id}")

                    # Provider
                    prov_obj  = doc.get("provider") or {}
                    provider  = str(prov_obj.get("name") or doc.get("dataProvider") or "")[:60]

                    tag_list  = ["DPLA", "United States", topic]
                    tag_list += sub_strs
                    if provider:
                        tag_list.append(provider)
                    if creator:
                        tag_list.append(creator[:60])
                    tags = json.dumps(tag_list)

                    seen_ids.add(item_id)
                    ok = insert_record(conn, source_id, {
                        "title":       title[:300],
                        "summary":     summary or None,
                        "image_url":   image_url or None,
                        "source_url":  src_url,
                        "external_id": f"dpla-{item_id}",
                        "date_text":   date_text,
                        "record_type": record_type,
                        "tags":        tags,
                        "region":      "United States",
                    })
                    if ok:
                        inserted      += 1
                        query_inserted += 1
                        page_inserted  += 1

                except Exception as e:
                    print(f"  [DPLA] Skipping doc due to error: {e}")
                    continue

            if page_inserted:
                print(f"  [DPLA] '{topic[:35]}' p{page} +{page_inserted} "
                      f"(total: {inserted})")

            total = data.get("count") or 0
            page += 1
            if page * PAGE_SIZE > min(total, MAX_PER_QUERY * 4) or len(docs) < PAGE_SIZE:
                break
            time.sleep(0.5)

        time.sleep(0.4)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
