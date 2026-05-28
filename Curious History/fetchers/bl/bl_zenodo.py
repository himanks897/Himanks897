"""
bl_zenodo.py — British Library datasets on Zenodo.

Uses the Zenodo public REST API (no key required) to search for
BL-related dataset records and store their metadata as historical content.

IMPORTANT: Does NOT download large files (> 10 MB). Only metadata
and small CSV previews are stored.

Source: https://zenodo.org/api/records
Auth:   None (public Zenodo API)
"""

import re
import json
import time
import requests
from db import insert_record

SOURCE_NAME = "BL Zenodo Datasets"
ZENODO_API  = "https://zenodo.org/api/records"

SEARCH_QUERIES = [
    "British Library newspapers history",
    "British Library digitised books historical",
    "British Library manuscripts medieval",
    "British Library India colonial records",
    "British Library historical maps georeferenced",
    "British Library Africa history digitised",
    "British Library Living with Machines newspaper",
    "British Library 19th century books metadata",
]

# Allowed open licences (no NC or ND)
_BLOCKED_LICENCE = {"cc-by-nc", "cc-by-nc-sa", "cc-by-nc-nd",
                    "cc-by-nd", "cc-nc", "cc-nd"}

_MAX_CSV_BYTES = 10_485_760  # 10 MB


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _licence_ok(record: dict) -> bool:
    """Return True if licence permits commercial / derivative use."""
    try:
        lic_id = record.get("metadata", {}).get("license", {}).get("id", "")
        lic_id = lic_id.lower()
        if not lic_id:
            return True  # unknown → allow
        for blocked in _BLOCKED_LICENCE:
            if blocked in lic_id:
                return False
        return True
    except Exception:
        return True


def _try_download_csv(files: list) -> str:
    """
    Find the first CSV in the files list that is < 10 MB, download it,
    and return its first 3000 characters as a string.
    Returns "" if no suitable CSV found.
    """
    for f in files:
        fmt = (f.get("type") or f.get("key", "")).lower()
        if not (fmt.endswith(".csv") or "csv" in fmt):
            continue
        size = f.get("size") or f.get("filesize") or 0
        if isinstance(size, int) and size > _MAX_CSV_BYTES:
            continue
        url = (f.get("links") or {}).get("self") or f.get("download")
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                return resp.text[:3000]
        except Exception:
            pass
    return ""


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    seen_ids: set = set()

    for query in SEARCH_QUERIES:
        try:
            resp = requests.get(
                ZENODO_API,
                params={"q": query, "type": "dataset", "size": 10},
                timeout=30,   # Zenodo can be slow — 30 s timeout
            )
            time.sleep(0.5)

            if resp.status_code != 200:
                print(f"  [WARN] Zenodo HTTP {resp.status_code} for query: {query[:60]}")
                continue

            hits = resp.json().get("hits", {}).get("hits", [])
            print(f"  [Zenodo] '{query[:50]}': {len(hits)} hits")

            for record in hits:
                try:
                    ext_id = str(record.get("id", ""))
                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)

                    # Licence check
                    if not _licence_ok(record):
                        continue

                    meta      = record.get("metadata", {})
                    title     = meta.get("title", "").strip()
                    if not title:
                        continue

                    desc_raw  = meta.get("description", "") or ""
                    summary   = _strip_html(desc_raw)[:1000]
                    date_text = meta.get("publication_date", "") or ""
                    source_url = (record.get("links") or {}).get("self", "") or ""

                    # Tags: Zenodo keywords + first creator name
                    kw_list   = meta.get("keywords") or []
                    if not isinstance(kw_list, list):
                        kw_list = [str(kw_list)]
                    creators  = meta.get("creators") or []
                    if creators:
                        creator_name = creators[0].get("name", "")
                        if creator_name:
                            kw_list = [creator_name] + kw_list
                    tags = json.dumps(kw_list[:20])

                    # Attempt CSV preview (small files only)
                    files     = record.get("files") or []
                    full_text = _try_download_csv(files)

                    ok = insert_record(conn, source_id, {
                        "title":       title,
                        "summary":     summary,
                        "full_text":   full_text if full_text else None,
                        "date_text":   date_text,
                        "tags":        tags,
                        "source_url":  source_url,
                        "external_id": ext_id,
                        "record_type": "dataset",
                    })
                    if ok:
                        inserted += 1

                except Exception as e:
                    print(f"  [WARN] Zenodo record error: {e}")
                    continue

        except Exception as e:
            print(f"  [ERROR] Zenodo query '{query[:40]}' failed: {e}")
            continue

    if inserted == 0:
        print("  [DIAG] 0 records inserted from Zenodo.")
        print("  Check zenodo.org is reachable.")

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
