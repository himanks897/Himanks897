"""
fetcher_pleiades.py — Pleiades: A community-built gazetteer of ancient places

Auth     : None required — fully open, no key
License  : CC BY 3.0 — commercial use allowed
Docs     : https://pleiades.stoa.org  |  API: https://api.pleiades.stoa.org
Coverage : All four ancient civilisations — Greece, Rome, Egypt, Mesopotamia
           and the broader ancient Mediterranean / Near East world

Strategy : Search per topic via the Pleiades search endpoint, then enrich
           each result with the place's full description from its JSON page.
           Records are formatted as readable English descriptions of ancient
           places (city, temple, site, river, region) — not raw coordinates.
"""

import re
import time
import requests
from db import insert_record

SOURCE_NAME = "Pleiades — Ancient World Gazetteer"
HEADERS     = {
    "User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/json",
}

# Pleiades endpoints
# @@search  → Plone site search (returns JSON when Accept: application/json)
# /@search  → Plone REST API search (alternative)
SEARCH_BASE  = "https://pleiades.stoa.org/@@search"
PLACE_BASE   = "https://pleiades.stoa.org/places"

# Topics that map to ancient civilisations — ordered by expected result richness
SEARCH_TOPICS = [
    # Ancient Greece
    ("Athens ancient city",         "Ancient Greece", "Greece"),
    ("Sparta Lacedaemon ancient",    "Ancient Greece", "Greece"),
    ("Olympia sanctuary Greece",     "Ancient Greece", "Greece"),
    ("Delphi oracle sanctuary",      "Ancient Greece", "Greece"),
    ("Corinth ancient city",         "Ancient Greece", "Greece"),
    ("Macedon ancient kingdom",      "Ancient Greece / Macedonia", "Greece"),
    ("Troy Ilion ancient city",      "Ancient Greece / Anatolia", "Anatolia"),
    ("Aegean islands ancient",       "Ancient Greece", "Greece"),
    ("Greek colony Sicily",          "Ancient Greece", "Sicily"),
    ("Thessaly ancient region",      "Ancient Greece", "Greece"),
    # Ancient Rome
    ("Rome ancient city Roma",       "Ancient Rome", "Italy"),
    ("Pompeii Herculaneum Vesuvius", "Ancient Rome", "Italy"),
    ("Carthage ancient city",        "Ancient Rome / North Africa", "North Africa"),
    ("Roman Britain province",       "Ancient Rome", "Britain"),
    ("Gaul Roman province",          "Ancient Rome", "France"),
    ("Roman Hispania province",      "Ancient Rome", "Spain"),
    ("Alexandria Egypt Roman",       "Ancient Rome / Egypt", "Egypt"),
    ("Roman Judaea province",        "Ancient Rome", "Levant"),
    ("Ephesus ancient city",         "Ancient Rome / Greece", "Anatolia"),
    ("Antioch ancient city Syria",   "Ancient Rome / Syria", "Syria"),
    # Ancient Egypt
    ("Memphis ancient Egypt city",   "Ancient Egypt", "Egypt"),
    ("Thebes ancient Egypt Luxor",   "Ancient Egypt", "Egypt"),
    ("Amarna Akhetaten Egypt",       "Ancient Egypt", "Egypt"),
    ("Karnak temple ancient Egypt",  "Ancient Egypt", "Egypt"),
    ("Alexandria ancient Egypt",     "Ancient Egypt", "Egypt"),
    ("Giza ancient Egypt pyramid",   "Ancient Egypt", "Egypt"),
    ("Heliopolis ancient Egypt",     "Ancient Egypt", "Egypt"),
    ("Nile Delta ancient",           "Ancient Egypt", "Egypt"),
    ("Nubia ancient kingdom",        "Ancient Egypt / Nubia", "Nubia"),
    ("Elephantine Aswan Egypt",      "Ancient Egypt", "Egypt"),
    # Ancient Mesopotamia
    ("Babylon ancient city",         "Ancient Mesopotamia", "Mesopotamia — Babylon"),
    ("Nineveh ancient Assyria",      "Ancient Mesopotamia", "Mesopotamia — Assyria"),
    ("Uruk Warka ancient Sumer",     "Ancient Mesopotamia", "Mesopotamia — Sumer"),
    ("Ur ancient Sumer city",        "Ancient Mesopotamia", "Mesopotamia — Sumer"),
    ("Nippur ancient Sumer",         "Ancient Mesopotamia", "Mesopotamia — Sumer"),
    ("Lagash ancient Sumer",         "Ancient Mesopotamia", "Mesopotamia — Sumer"),
    ("Persepolis Achaemenid Persia", "Ancient Persia", "Persia"),
    ("Ctesiphon Parthia Persia",     "Ancient Mesopotamia / Persia", "Mesopotamia"),
    ("Mari ancient Syria",           "Ancient Mesopotamia", "Mesopotamia / Syria"),
    ("Assur ancient Assyria",        "Ancient Mesopotamia", "Mesopotamia — Assyria"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _build_place_description(place: dict, search_label: str) -> str:
    """
    Build a readable English description of an ancient place from Pleiades data.
    Format: 'Ancient [name] — [description]. Located in [feature_type]...
    Connections: [connected_places]'
    """
    name        = place.get("title") or place.get("name") or search_label
    description = _strip_html(place.get("description") or "").strip()
    details     = _strip_html(place.get("details") or "").strip()
    feat_type   = place.get("placeType") or place.get("featureTypes") or []
    if isinstance(feat_type, list):
        feat_type = ", ".join(feat_type[:3])

    # Connections to other ancient places
    connections = place.get("connections") or []
    conn_names  = [c.get("title") or "" for c in connections[:5] if c.get("title")]

    parts = []
    if description:
        parts.append(description)
    if details and details != description:
        parts.append(details[:400])
    if feat_type:
        parts.append(f"Site type: {feat_type}.")
    if conn_names:
        parts.append(f"Connected ancient places: {', '.join(conn_names)}.")

    if not parts:
        # Minimal fallback using just the title
        parts.append(f"{name}: an ancient place recorded in the Pleiades gazetteer.")

    return " ".join(parts)[:800]


def _fetch_place_detail(pid: str) -> dict:
    """Fetch full place JSON from Pleiades."""
    try:
        resp = requests.get(
            f"{PLACE_BASE}/{pid}/json",
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _parse_ancient_year(time_periods: list) -> int | None:
    """Extract earliest year from Pleiades time period data."""
    if not time_periods:
        return None
    years = []
    for tp in time_periods:
        start = tp.get("start") or tp.get("timePeriod", {}).get("start")
        if start is not None:
            years.append(int(start))
    return min(years) if years else None


def _search_pleiades(topic: str) -> list:
    """
    Try multiple Pleiades search endpoints/formats in order.
    Returns a list of place items (dicts), or [] on failure.
    """
    # 1. Plone REST @@search with Accept: application/json
    for endpoint, params in [
        (SEARCH_BASE, {
            "SearchableText": topic,
            "review_state":   "published",
            "portal_type":    "Place",
            "batch_size":     20,
        }),
        # 2. Plone REST API endpoint (newer Plone sites)
        ("https://pleiades.stoa.org/@search", {
            "SearchableText": topic,
            "portal_type":    "Place",
            "b_size":         20,
        }),
    ]:
        try:
            r = requests.get(endpoint, headers=HEADERS, params=params, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json()
            items = (data.get("@graph") or data.get("items") or
                     data.get("features") or data.get("results") or
                     data.get("members") or [])
            if items:
                return items
        except Exception:
            continue
    return []


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    for (topic, era, region) in SEARCH_TOPICS:
        items = _search_pleiades(topic)
        if not items:
            time.sleep(0.5)
            continue

        for item in items[:20]:   # max 20 per topic
            # Pleiades items can use "@id", "id", "uid", or "UID" as identifier
            pid_raw = (item.get("@id") or item.get("id") or
                       item.get("uid") or item.get("UID") or "")
            pid = str(pid_raw).rstrip("/").split("/")[-1]
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            title = _strip_html(
                item.get("title") or item.get("label") or
                item.get("name") or topic
            ).strip()
            if not title:
                continue

            # Fetch full place detail for richer description
            detail = _fetch_place_detail(pid)
            if detail:
                place_data = detail
            else:
                place_data = item

            summary = _build_place_description(place_data, title)

            # Time period
            time_periods = place_data.get("timePeriods") or []
            year_start   = _parse_ancient_year(time_periods)
            date_text    = place_data.get("timePeriodRange") or era

            # Better region from place data
            place_region = region
            repr_point   = place_data.get("reprPoint") or []
            modern_countries = place_data.get("modernCountries") or []
            if modern_countries:
                place_region = ", ".join(modern_countries[:2])

            tags = [t for t in [
                "ancient", "geography", era, region, title,
            ] + list(place_data.get("placeType") or [])[:3]
                if t and len(t) > 1]

            ok = insert_record(conn, source_id, {
                "title":           title,
                "summary":         summary,
                "record_type":     "place",
                "region":          place_region,
                "era":             era,
                "date_text":       date_text,
                "date_year_start": year_start,
                "source_url":      f"{PLACE_BASE}/{pid}",
                "external_id":     f"pleiades_{pid}",
                "tags":            tags,
            })
            if ok:
                inserted += 1
                if inserted % 20 == 0:
                    print(f"  [Pleiades] {inserted} records so far…")

            time.sleep(0.3)

        time.sleep(0.5)

    print(f"  [Pleiades] {inserted} place records inserted")
    return inserted
