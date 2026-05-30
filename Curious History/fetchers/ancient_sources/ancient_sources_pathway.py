"""
ancient_sources_pathway.py — Orchestrator for all 9 ancient-world sources.

Runs fetchers in sequence. One broken import cannot stop the others.
Saves progress after each fetcher.

Sources (all commercial-use OK):
  1  CDLI — Cuneiform Digital Library    CC BY 4.0
  2  ORACC — Annotated Cuneiform         CC BY-SA 3.0
  3  Pleiades — Ancient World Gazetteer  CC BY 3.0
  4  Open Context — Archaeology Data     CC BY
  5  Internet Archive — Ancient History  Public Domain
  6  Nomisma — Ancient Coins             CC0
  7  Project Mercury — Roman Datasets    Open / CC
  8  TLA — Ancient Egyptian Texts        Free licence
  9  ISAC — Oriental Institute Chicago   Open access

MANUSCRIPT RULE (enforced in every fetcher):
  Sources 1, 2, 8 contain manuscript content (cuneiform/hieroglyphic).
  Their fetchers ONLY store records with English translations.
  Raw transliterations, cuneiform Unicode, and hieroglyphic text
  are never stored or returned to users.
"""

import importlib
from db import get_source_id, update_last_synced, save


def run_all(conn: dict) -> dict:
    """
    Register all 9 ancient sources and run their fetchers in sequence.
    Returns dict: {source_name: records_inserted}
    """
    results: dict = {}

    # ── Step 1: Register all 9 sources ───────────────────────────────────────
    from fetchers.ancient_sources.ancient_sources_db_setup import insert_ancient_sources
    insert_ancient_sources(conn)
    save(conn)

    # ── Step 2: Run each fetcher ──────────────────────────────────────────────
    # Order matters: start with richer content sources (ISAC built-ins, Mercury,
    # TLA built-ins) then hit live APIs (CDLI, ORACC, Pleiades, OpenContext, IA).
    fetcher_modules = [
        # Built-in / curated records first (fastest, most reliable)
        "fetchers.ancient_sources.fetcher_mercury",       # Roman provinces + cities (built-in)
        "fetchers.ancient_sources.fetcher_tla",           # Egyptian texts (built-in + API)
        "fetchers.ancient_sources.fetcher_isac",          # ISAC publications (built-in + live)
        # Live API sources
        "fetchers.ancient_sources.fetcher_ia_ancient",    # Internet Archive (no key needed)
        "fetchers.ancient_sources.fetcher_opencontext",   # Open Context (no key needed)
        "fetchers.ancient_sources.fetcher_pleiades",      # Pleiades gazetteer (no key needed)
        "fetchers.ancient_sources.fetcher_nomisma",       # Nomisma SPARQL (no key needed)
        "fetchers.ancient_sources.fetcher_oracc",         # ORACC JSON (no key needed)
        "fetchers.ancient_sources.fetcher_cdli",          # CDLI REST (account key optional)
    ]

    for module_path in fetcher_modules:
        try:
            module      = importlib.import_module(module_path)
            source_name = module.SOURCE_NAME

            sid = get_source_id(conn, source_name)
            if sid is None:
                print(f"  [SKIP] Source not registered: {source_name!r}")
                results[source_name] = 0
                continue

            print(f"\n── Running: {source_name}")
            count = module.fetch(conn, sid)
            update_last_synced(conn, sid)
            save(conn)   # persist after each fetcher so partial runs are saved
            results[source_name] = count
            print(f"  ✓ {source_name}: {count} records")

        except Exception as e:
            import traceback
            print(f"[FATAL] {module_path}: {e}")
            traceback.print_exc()
            try:
                mod = importlib.import_module(module_path)
                results[mod.SOURCE_NAME] = 0
            except Exception:
                results[module_path] = 0

    return results
