"""
ancient_sources_db_setup.py — Registers all 9 ancient-world sources
into the JSON pipeline database.

Safe to call multiple times (name-based deduplication).
"""

ANCIENT_SOURCES = [
    {
        "name":         "CDLI — Cuneiform Digital Library",
        "base_url":     "https://cdli.earth/api/v1",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "ORACC — Annotated Cuneiform Corpus",
        "base_url":     "http://oracc.museum.upenn.edu",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Pleiades — Ancient World Gazetteer",
        "base_url":     "https://pleiades.stoa.org",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Open Context — Archaeology Data",
        "base_url":     "https://opencontext.org",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Internet Archive — Ancient History",
        "base_url":     "https://archive.org/advancedsearch.php",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "Nomisma — Ancient Coins",
        "base_url":     "http://nomisma.org",
        "api_type":     "SPARQL",
        "content_type": "full_text",
    },
    {
        "name":         "Project Mercury — Roman Datasets",
        "base_url":     "https://projectmercury.eu",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "TLA — Thesaurus Linguae Aegyptiae",
        "base_url":     "https://thesaurus-linguae-aegyptiae.de",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "ISAC — Oriental Institute Chicago",
        "base_url":     "https://isac.uchicago.edu",
        "api_type":     "REST",
        "content_type": "full_text",
    },
]


def insert_ancient_sources(conn: dict) -> None:
    """
    Register all 9 ancient-world sources. Name-based deduplication —
    safe to call on every pipeline run.
    """
    existing_names = {s["name"] for s in conn.get("sources", [])}
    existing_ids   = [s["id"] for s in conn.get("sources", [])] if conn.get("sources") else [0]
    next_id        = max(existing_ids) + 1

    added = 0
    for src in ANCIENT_SOURCES:
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
        print(f"  [DB] Registered: {src['name']} (id={next_id})")
        existing_names.add(src["name"])
        next_id += 1
        added   += 1

    if added == 0:
        print("  [DB] All ancient sources already registered.")
    else:
        print(f"  [DB] {added} ancient source(s) registered.")
