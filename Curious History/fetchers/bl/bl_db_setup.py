"""
bl_db_setup.py — Inserts the 5 British Library Pathway 3 source rows
into the JSON pipeline database (curious_history.json).

Uses INSERT-OR-IGNORE semantics: safe to call multiple times.
Adapted for the JSON-based db.py architecture (no SQLite).

Sub-source D was originally "BL Flickr Commons"; it has been replaced
by "BL Wikimedia Commons" (no API key, fully public domain).
Any previously registered "BL Flickr Commons" source with 0 records is
migrated in-place to "BL Wikimedia Commons" so the source ID is reused.
"""

# ── The 5 BL sub-sources ──────────────────────────────────────────────────────
BL_SOURCES = [
    {
        "name":         "BL Research Repository (OAI-PMH)",
        "base_url":     "https://bl.iro.bl.uk/catalog/oai",
        "api_type":     "OAI-PMH",
        "content_type": "full_text",
    },
    {
        "name":         "BL Zenodo Datasets",
        "base_url":     "https://zenodo.org",
        "api_type":     "REST",
        "content_type": "full_text",
    },
    {
        "name":         "BL GitHub Georeferencer",
        "base_url":     "https://github.com/britishlibrary/georeferencer_research_repo",
        "api_type":     "Git",
        "content_type": "metadata_only",
    },
    {
        "name":         "BL Wikimedia Commons",
        "base_url":     "https://commons.wikimedia.org",
        "api_type":     "REST",
        "content_type": "supplementary",
    },
    {
        "name":         "BL British National Bibliography",
        "base_url":     "https://ckan.publishing.service.gov.uk",
        "api_type":     "RDF",
        "content_type": "full_text",
    },
]

# Old name → new name migration map
_RENAME_MAP = {
    "BL Flickr Commons": "BL Wikimedia Commons",
}


def _flickr_record_count(conn: dict, flickr_source_id: int) -> int:
    """Count how many records are attributed to the Flickr source."""
    return sum(
        1 for r in conn.get("records", [])
        if r.get("source_id") == flickr_source_id
    )


def _migrate_legacy_sources(conn: dict) -> None:
    """
    Rename any obsolete source names to their replacements.
    Only renames a source when it has 0 records (safe to do so).
    """
    for src in conn.get("sources", []):
        old_name = src.get("name", "")
        new_name = _RENAME_MAP.get(old_name)
        if not new_name:
            continue

        if _flickr_record_count(conn, src["id"]) > 0:
            print(f"  [DB] Kept old source '{old_name}' (has records) — "
                  f"adding '{new_name}' as a separate source.")
            continue

        # Zero records — safe to rename in-place
        src["name"]     = new_name
        src["base_url"] = "https://commons.wikimedia.org"
        src["api_type"] = "REST"
        # content_type stays as "supplementary"
        print(f"  [DB] Migrated source: '{old_name}' → '{new_name}' (id={src['id']})")


def insert_bl_sources(conn: dict) -> None:
    """
    Insert the 5 BL sources into conn["sources"] if not already present.
    Safe to call multiple times — uses name-based deduplication.
    Migrates any legacy source names (Flickr → Wikimedia Commons) first.
    """
    # ── Step 1: Migrate legacy source names ───────────────────────────────────
    _migrate_legacy_sources(conn)

    # ── Step 2: Insert any missing sources ────────────────────────────────────
    existing_names = {s["name"] for s in conn.get("sources", [])}
    existing_ids   = [s["id"] for s in conn.get("sources", [])] if conn.get("sources") else [0]
    next_id        = max(existing_ids) + 1

    added = 0
    for src in BL_SOURCES:
        if src["name"] in existing_names:
            continue  # INSERT OR IGNORE
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

    if added == 0 and not any(
        old in existing_names for old in _RENAME_MAP
    ):
        print("  [DB] All BL sources already registered — nothing to add.")
    elif added > 0:
        print(f"  [DB] {added} new BL source(s) registered.")
