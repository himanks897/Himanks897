"""
fetcher_hathitrust.py — HathiTrust Digital Library

Uses the HathiTrust catalog search to find public-domain historical texts.
Focus: South Asian, East Asian, and multilingual global history texts that
are absent from other sources in the pipeline.

Endpoint : https://catalog.hathitrust.org/Search/Home (JSON output)
Auth     : None required
License  : Public Domain / CC0 for pre-1928 texts — commercial OK
Docs     : https://www.hathitrust.org/data
"""

import time
import requests
from db import insert_record
from fetchers.new_sources.era_utils import infer_era as _infer_topic_era

SOURCE_NAME = "HathiTrust Digital Library"
# HathiTrust Catalog API — correct JSON endpoint
BASE_URL    = "https://catalog.hathitrust.org/Search/Home"
# Alternative: the Bibliographic API returns cleaner JSON
_BIBLIO_API = "https://catalog.hathitrust.org/api/volumes/brief/json/"
HEADERS     = {
    "User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/json, */*",
}

# Focus on regions with weak coverage in our pipeline
QUERIES = [
    # South Asia
    "India history British colonial",
    "Mughal Empire India history",
    "Bengal history partition",
    "Indian independence Gandhi",
    "Ceylon Sri Lanka history",
    "Punjab history Sikh",
    # East Asia
    "China history Ming dynasty",
    "China Qing dynasty history",
    "Japan Meiji history",
    "Korea history Joseon",
    # Southeast Asia
    "Burma Myanmar history colonial",
    "Malaya Singapore history British",
    "Vietnam history French colonial",
    "Indonesia history Dutch colonial",
    # Middle East / Islamic
    "Ottoman Empire history",
    "Persia Iran history",
    "Egypt history ancient modern",
    "Islamic caliphate history",
    # Africa
    "Africa history colonialism",
    "West Africa history kingdoms",
    "Ethiopia Abyssinia history",
    # Latin America
    "Mexico history Aztec Spanish",
    "Peru history Inca Spanish",
    "Argentina history colonial",
]


def _safe_str(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v).strip()
    return str(val).strip()


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0

    for query in QUERIES:
        try:
            # HathiTrust Catalog Search — correct parameter format
            params = {
                "lookfor":  query,
                "type":     "AllFields",
                "filter[]": "language:English",
                "limit":    20,
                "view":     "list",
                "format":   "json",
            }
            resp = requests.get(
                BASE_URL, headers=HEADERS, params=params, timeout=25
            )

            if resp.status_code != 200:
                time.sleep(1)
                continue

            try:
                data = resp.json()
            except ValueError:
                time.sleep(0.5)
                continue

            # HathiTrust returns {"resultCount": N, "records": {...}, "items": [...]}
            # The "records" key is a dict keyed by record ID, not a list
            records_dict = data.get("records") or {}
            records_list = list(records_dict.values()) if isinstance(records_dict, dict) else []
            # Also try list-form keys
            if not records_list:
                records_list = data.get("items") or data.get("results") or []
            if not isinstance(records_list, list):
                records_list = []

            for rec in records_list:
                title    = _safe_str(rec.get("title"))
                desc     = _safe_str(rec.get("description") or rec.get("fullTitle") or "")
                pub_date = _safe_str(rec.get("publishDate") or rec.get("date") or "")
                author   = _safe_str(rec.get("author") or rec.get("creator") or "")
                rec_id   = _safe_str(rec.get("id") or rec.get("recordId") or "")
                subjects = rec.get("subject") or rec.get("topics") or []
                if isinstance(subjects, str):
                    subjects = [subjects]

                if not title or not rec_id:
                    continue

                url = f"https://catalog.hathitrust.org/Record/{rec_id}"

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     (f"{author} — {desc}"[:500]) if author else desc[:500],
                    "date_text":   pub_date[:20],
                    "source_url":  url,
                    "external_id": f"ht-{rec_id}",
                    "record_type": "document",
                    "era":         _infer_topic_era(query),
                    "tags":        [str(s)[:60] for s in subjects[:6]]
                                   + ["HathiTrust", query[:40]],
                })
                if ok:
                    inserted += 1

            time.sleep(0.7)

        except requests.RequestException as e:
            print(f"  [HT] Request error for '{query}': {e}")
            time.sleep(2)
        except Exception as e:
            print(f"  [HT] Error for '{query}': {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
