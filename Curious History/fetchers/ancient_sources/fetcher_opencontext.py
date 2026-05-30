"""
fetcher_opencontext.py — Open Context: Archaeological Research Data

Auth     : None required — set User-Agent header
License  : CC BY — commercial use allowed
Docs     : https://opencontext.org/about/services
Coverage : Mediterranean, Near East, Egypt, Mesopotamia — archaeological data

Results are formatted as readable English descriptions of excavation sites,
artefacts, and archaeological finds. No raw data codes are exposed to users.
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Open Context — Archaeology Data"
HEADERS     = {
    "User-Agent": "oc-api-client CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/json",
}

OC_BASE = "https://opencontext.org/query/"

# Search queries paired with era/region metadata
SEARCH_QUERIES = [
    # Mesopotamia
    ("Mesopotamia ancient",         "Ancient Mesopotamia",            "Mesopotamia"),
    ("Babylon Babylonian",          "Ancient Mesopotamia",            "Mesopotamia — Babylon"),
    ("Assyrian cuneiform",          "Ancient Mesopotamia",            "Mesopotamia — Assyria"),
    ("Sumerian Sumer",              "Ancient Mesopotamia",            "Mesopotamia — Sumer"),
    ("Iraq ancient excavation",     "Ancient Mesopotamia",            "Mesopotamia"),
    ("Near East Bronze Age",        "Ancient Near East",              "Near East"),
    ("Ur excavation",               "Ancient Mesopotamia",            "Mesopotamia — Ur"),
    # Ancient Egypt
    ("Egypt pharaoh ancient",       "Ancient Egypt",                  "Egypt"),
    ("Egyptian mummy tomb",         "Ancient Egypt",                  "Egypt"),
    ("Nile Egypt excavation",       "Ancient Egypt",                  "Egypt"),
    ("Amarna Akhenaten",            "Ancient Egypt",                  "Egypt"),
    ("Nubia Kerma excavation",      "Ancient Egypt / Nubia",          "Nubia"),
    # Ancient Greece
    ("Greece ancient Archaic",      "Ancient Greece",                 "Greece"),
    ("Athens acropolis",            "Ancient Greece",                 "Greece"),
    ("Greek pottery vase",          "Ancient Greece",                 "Greece"),
    ("Bronze Age Aegean",           "Ancient Greece — Bronze Age",    "Greece"),
    ("Mycenae Mycenaean",           "Ancient Greece — Bronze Age",    "Greece"),
    ("Minoan Crete",                "Ancient Greece — Minoan",        "Crete"),
    # Ancient Rome
    ("Roman Empire excavation",     "Ancient Rome",                   "Italy"),
    ("Pompeii Roman site",          "Ancient Rome",                   "Italy"),
    ("Roman amphora ceramic",       "Ancient Rome",                   "Mediterranean"),
    ("Roman Britain",               "Ancient Rome",                   "Britain"),
    ("Roman Syria Levant",          "Ancient Rome",                   "Levant"),
    # General Ancient
    ("Iron Age Mediterranean",      "Ancient Mediterranean",          "Mediterranean"),
    ("Neolithic ancient settlement","Prehistoric / Neolithic",        "Mediterranean"),
    ("Chalcolithic ancient",        "Prehistoric — Chalcolithic",     "Near East"),
    ("Phoenician Carthage",         "Ancient Phoenicia",              "Lebanon / North Africa"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _build_summary(item: dict, query_label: str, era: str) -> str:
    """
    Build readable English summary from Open Context item metadata.
    """
    label       = _strip_html(item.get("label") or item.get("title") or query_label)
    description = _strip_html(item.get("description") or "")
    context     = _strip_html(item.get("context_label") or item.get("context") or "")
    category    = item.get("category") or ""
    if isinstance(category, dict):
        category = category.get("label") or ""
    project     = item.get("project_label") or item.get("project") or ""

    parts = []
    if description and len(description) > 20:
        parts.append(description)
    if context:
        parts.append(f"Archaeological context: {context}.")
    if category:
        parts.append(f"Type: {category}.")
    if project:
        parts.append(f"Research project: {project}.")
    if not parts:
        parts.append(f"{label}: archaeological find from the {era} period.")

    return " ".join(parts)[:700]


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    for (query, era, region) in SEARCH_QUERIES:
        try:
            resp = requests.get(
                OC_BASE,
                headers=HEADERS,
                params={
                    "q":             query,
                    "type":          "subjects",
                    "format":        "json",
                    "rows":          30,
                    "start":         0,
                },
                timeout=20,
            )
        except Exception as e:
            print(f"  [OpenContext] Request error for '{query}': {e}")
            time.sleep(1)
            continue

        if resp.status_code != 200:
            time.sleep(0.5)
            continue

        try:
            data = resp.json()
        except Exception:
            continue

        # Open Context returns {"features": [...]} or {"results": [...]}
        features = (data.get("features") or data.get("results") or
                    data.get("oc-api:has-results") or [])

        for item in features[:25]:
            # OC uses "@id" or "id" as the unique identifier
            item_id = (item.get("@id") or item.get("id") or "").rstrip("/").split("/")[-1]
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            props    = item.get("properties") or item
            title    = _strip_html(
                props.get("label") or props.get("title") or
                item.get("label") or query
            ).strip()
            if not title or len(title) < 3:
                continue

            summary = _build_summary(props, query, era)

            # Date information
            date_start = (props.get("early_bce") or props.get("date_start") or
                          item.get("when", {}).get("start") if isinstance(item.get("when"), dict) else None)
            if date_start is not None:
                try:
                    date_start = int(date_start)
                except (TypeError, ValueError):
                    date_start = None

            # Coordinates for geographic context
            geo = item.get("geometry") or {}
            coords = geo.get("coordinates") or []

            tags = [t for t in [
                "archaeology", "ancient", era, region, query,
                props.get("category") if isinstance(props.get("category"), str) else "",
            ] if t and len(t) > 1]

            source_url = (props.get("uri") or item.get("@id") or
                          f"https://opencontext.org/subjects/{item_id}")

            ok = insert_record(conn, source_id, {
                "title":           title,
                "summary":         summary,
                "record_type":     "artefact",
                "region":          region,
                "era":             era,
                "date_year_start": date_start,
                "source_url":      source_url,
                "external_id":     f"oc_{item_id}",
                "tags":            tags,
            })
            if ok:
                inserted += 1
                if inserted % 30 == 0:
                    print(f"  [OpenContext] {inserted} records so far…")

        time.sleep(0.6)

    print(f"  [OpenContext] {inserted} records inserted")
    return inserted
