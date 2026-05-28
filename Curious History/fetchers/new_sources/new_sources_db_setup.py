"""
new_sources_db_setup.py — Registers all 18 global-history sources
into the JSON pipeline database (8 original + 10 new global sources).

Safe to call multiple times (name-based deduplication).
"""

NEW_SOURCES = [
    {
        "name":         "National Library Norway (nb.no)",
        "base_url":     "https://api.nb.no/catalog/v1",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "National Library Sweden (KB)",
        "base_url":     "https://libris.kb.se",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Finna Finland",
        "base_url":     "https://api.finna.fi/v1",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Polona Poland",
        "base_url":     "https://polona.pl/api",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Europeana Romania",
        "base_url":     "https://api.europeana.eu/record/v2",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "BnF Gallica France",
        "base_url":     "https://gallica.bnf.fr/services/engine/search/sru",
        "api_type":     "SRU",
        "content_type": "full_text",
    },
    {
        "name":         "Europeana",
        "base_url":     "https://api.europeana.eu/record/v2",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "DPLA",
        "base_url":     "https://api.dp.la/v2",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    # ── 10 new global sources ──────────────────────────────────────────────────
    {
        "name":         "National Diet Library Japan",
        "base_url":     "https://iss.ndl.go.jp/api/opensearch",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "HathiTrust Digital Library",
        "base_url":     "https://catalog.hathitrust.org",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Internet Archive — India",
        "base_url":     "https://archive.org/advancedsearch.php",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Internet Archive — Africa",
        "base_url":     "https://archive.org/advancedsearch.php",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "SOAS University London",
        "base_url":     "https://eprints.soas.ac.uk/cgi/oai2",
        "api_type":     "OAI-PMH",
        "content_type": "full_text",
    },
    {
        "name":         "OpenITI — Islamic Texts",
        "base_url":     "https://archive.org/advancedsearch.php",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Europeana Middle East & Global",
        "base_url":     "https://api.europeana.eu/record/v2",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Library of Congress",
        "base_url":     "https://www.loc.gov/search/",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Memoria Chilena",
        "base_url":     "http://www.memoriachilena.gob.cl/oai/request",
        "api_type":     "OAI-PMH",
        "content_type": "full_text",
    },
]


def insert_new_sources(conn: dict) -> None:
    """
    Insert all 8 new sources if not already present.
    Safe to call multiple times — uses name-based deduplication.
    """
    existing_names = {s["name"] for s in conn.get("sources", [])}
    existing_ids   = [s["id"] for s in conn.get("sources", [])] if conn.get("sources") else [0]
    next_id        = max(existing_ids) + 1

    added = 0
    for src in NEW_SOURCES:
        if src["name"] in existing_names:
            continue
        conn.setdefault("sources", []).append({
            "id":           next_id,
            "name":         src["name"],
            "base_url":     src["base_url"],
            "api_type":     src["api_type"],
            "content_type": src["content_type"],
            "last_synced":  None,
        })
        print(f"  [DB] Added source: {src['name']} (id={next_id})")
        existing_names.add(src["name"])
        next_id += 1
        added   += 1

    if added == 0:
        print("  [DB] All new sources already registered — nothing to add.")
    else:
        print(f"  [DB] {added} new source(s) registered.")
