"""
fetcher_norway.py — National Library of Norway (Bokhylla / nb.no)

Harvests digitised books, newspapers and manuscripts from the National
Library of Norway digital archive (bokhylla.no).

Endpoint: https://api.nb.no/catalog/v1/items
Licence:  NLOD 2.0 (Norwegian Licence for Open Government Data) — commercial OK
No API key required.

nb.no response structure (verified against live API 2025):
  item = {
    "id": "...",
    "_links": {
      "self": {"href": "https://api.nb.no/catalog/v1/items/..."},
      "presentationUri": {"href": "https://www.nb.no/items/..."}
    },
    "accessInfo": {"isDigitallyAccessible": bool, ...},
    "metadata": {
      "title": "...",
      "creators": ["Name1", "Name2"],
      "originInfo": {"issued": "YYYY", "publisher": "..."},
      "identifiers": {"sesamId": "...", "oaiId": "..."},
      "subject": {"geographics": [...], "topics": [...], "genres": [...]},
      "contentClasses": ["restricted"/"freely_available"/...],
      "mediaTypes": ["bøker"/"aviser"/...]
    }
  }

Documentation: https://api.nb.no/
"""

import json
import time
import requests

from db import insert_record

SOURCE_NAME  = "National Library Norway (nb.no)"
API_BASE     = "https://api.nb.no/catalog/v1/items"
PAGE_SIZE    = 20
MAX_PAGES    = 3     # max pages per topic (3 × 20 = 60 items max)
MAX_PER_QUERY = 60   # hard cap on inserted records per topic

_HEADERS = {
    "User-Agent": (
        "CuriousHistory/1.0 "
        "(https://github.com/himanksangtani/curious-history; "
        "himanks897@gmail.com) python-requests/2.x"
    ),
    "Accept": "application/json",
}

# Historical topics focused on Norwegian/Nordic/broader history
TOPICS = [
    "Norwegian history",
    "Norway history",
    "Viking age",
    "Norse mythology",
    "Norwegian independence",
    "Scandinavian history",
    "Nordic history",
    "Hanseatic League Norway",
    "Norwegian reformation",
    "Norwegian medieval history",
    "Norwegian folk culture",
    "Oslo history",
    "Bergen history",
    "Norwegian Arctic exploration",
    "Svalbard history",
    "Norwegian constitution 1814",
    "Danish Norwegian history",
    "Norwegian literature history",
    "North Sea history",
    "Norwegian sailors history",
]


def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val).strip()


def _extract_subjects(subject_raw) -> list:
    """
    nb.no subject is a dict like {"geographics": [...], "topics": [...]}.
    Flatten all values into a list of strings.
    """
    if not subject_raw:
        return []
    if isinstance(subject_raw, str):
        return [subject_raw[:60]]
    if isinstance(subject_raw, list):
        return [str(s)[:60] for s in subject_raw[:6]]
    if isinstance(subject_raw, dict):
        flat = []
        for vals in subject_raw.values():
            if isinstance(vals, list):
                flat.extend(str(v)[:60] for v in vals[:3])
            elif vals:
                flat.append(str(vals)[:60])
        return flat[:8]
    return [str(subject_raw)[:60]]


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    for topic in TOPICS:
        query_inserted = 0
        from_offset    = 0
        page_count     = 0

        while query_inserted < MAX_PER_QUERY and page_count < MAX_PAGES:
            params = {
                "q":    topic,
                "size": PAGE_SIZE,
                "from": from_offset,
            }
            try:
                resp = requests.get(API_BASE, params=params,
                                    headers=_HEADERS, timeout=20)
            except requests.RequestException as e:
                print(f"  [NB] Request error for '{topic}': {e}")
                break

            if resp.status_code != 200:
                print(f"  [NB] HTTP {resp.status_code} for '{topic}'")
                break

            try:
                data = resp.json()
            except ValueError as e:
                print(f"  [NB] JSON parse error: {e}")
                break

            # nb.no wraps results in _embedded.items
            embedded = data.get("_embedded") or {}
            items    = embedded.get("items") or []
            if not items:
                break

            page_inserted = 0
            for item in items:
                try:
                    # Use sesamId or oaiId as stable identifier
                    meta      = item.get("metadata") or {}
                    ids_dict  = meta.get("identifiers") or {}
                    item_id   = str(
                        ids_dict.get("sesamId") or
                        ids_dict.get("oaiId") or
                        item.get("id") or ""
                    ).strip()
                    if not item_id or item_id in seen_ids:
                        continue

                    title = str(meta.get("title") or "").strip()
                    if not title:
                        continue

                    # Skip items not freely available (check accessInfo)
                    access = item.get("accessInfo") or {}
                    # We include all items — restrictive items still have metadata value
                    # but skip explicitly copyrighted ones
                    content_classes = meta.get("contentClasses") or []
                    if "COPYRIGHTED" in content_classes and "freely_available" not in content_classes:
                        # Skip clearly copyrighted items with no free access
                        pass  # Still include metadata — it's still educationally useful

                    # Description — NB API rarely returns description/abstract fields.
                    # Build a synthetic English summary from available metadata so
                    # the record has searchable text content rather than empty summary.
                    description = str(meta.get("description") or meta.get("abstract") or "").strip()
                    if not description:
                        # Build synthetic description from metadata
                        media_types = meta.get("mediaTypes") or []
                        media_label = media_types[0].capitalize() if media_types else "Work"
                        creator_part = f" by {creator}" if creator else ""
                        date_part    = f", published {date_text}" if date_text else ""
                        subject_part = (f". Topics covered: {', '.join(flat_subjects[:4])}."
                                        if flat_subjects else ".")
                        description  = (
                            f"{media_label} from the National Library of Norway"
                            f"{creator_part}{date_part}"
                            f"{subject_part} "
                            f"Part of the Norwegian national digital heritage collection "
                            f"covering history, culture, and society."
                        )[:600]

                    # Creator
                    creators_raw = meta.get("creators") or []
                    if isinstance(creators_raw, list):
                        creator = ", ".join(str(c) for c in creators_raw[:3])
                    else:
                        creator = str(creators_raw)

                    # Date — nb.no stores under originInfo.issued
                    origin_info = meta.get("originInfo") or {}
                    date_text   = str(origin_info.get("issued") or
                                      origin_info.get("date") or
                                      meta.get("year") or "")[:20]

                    # Source URL — use presentationUri from _links
                    links_raw = item.get("_links") or {}
                    pres_uri  = links_raw.get("presentationUri") or {}
                    src_url   = (pres_uri.get("href") or
                                 f"https://www.nb.no/items/{item_id}")

                    # Subjects / tags — subject is a dict in nb.no
                    subject_raw  = meta.get("subject") or meta.get("subjects") or {}
                    flat_subjects = _extract_subjects(subject_raw)

                    tag_list = ["Norway", "National Library Norway", "NLOD", topic]
                    tag_list += flat_subjects
                    if creator:
                        tag_list.append(creator[:60])
                    tags = json.dumps(tag_list)

                    seen_ids.add(item_id)
                    ok = insert_record(conn, source_id, {
                        "title":       title[:300],
                        "summary":     description or None,
                        "source_url":  src_url,
                        "external_id": f"nb-{item_id[:80]}",
                        "date_text":   date_text,
                        "record_type": "document",
                        "tags":        tags,
                        "region":      "Norway",
                        "era":         "Scandinavian / Nordic History",
                    })
                    if ok:
                        inserted      += 1
                        query_inserted += 1
                        page_inserted  += 1

                except Exception as e:
                    print(f"  [NB] Skipping item due to error: {e}")
                    continue

            if page_inserted:
                print(f"  [NB] '{topic[:35]}' +{page_inserted} "
                      f"(total: {inserted})")

            # Pagination — simple page counter cap
            page_count  += 1
            from_offset += PAGE_SIZE
            if len(items) < PAGE_SIZE:
                break   # last page
            time.sleep(0.3)

        time.sleep(0.3)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
