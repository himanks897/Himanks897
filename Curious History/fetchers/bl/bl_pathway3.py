"""
bl_pathway3.py — Orchestrator for all 5 British Library Pathway 3 sub-sources.

Runs fetchers in sequence. Uses importlib so one broken import cannot
prevent the others from running.

Sub-source D: bl_wikimedia_commons (replaced bl_flickr — no API key needed)
"""

import importlib
from datetime import datetime
from db import get_source_id, update_last_synced, save


def run_all(conn: dict) -> dict:
    """
    Run all 5 BL sub-source fetchers in sequence.
    Returns dict: {source_name: records_inserted}
    """
    results: dict = {}

    # ── Step 1: Ensure all BL sources are registered ─────────────────────────
    from fetchers.bl.bl_db_setup import insert_bl_sources
    insert_bl_sources(conn)

    # ── Step 2: Run each fetcher ──────────────────────────────────────────────
    fetcher_modules = [
        "fetchers.bl.bl_oai_pmh",
        "fetchers.bl.bl_zenodo",
        "fetchers.bl.bl_github",
        "fetchers.bl.bl_wikimedia_commons",   # replaced bl_flickr
        "fetchers.bl.bl_bnb",
    ]

    for module_path in fetcher_modules:
        try:
            # (a) Import module at runtime so one failure doesn't block others
            module = importlib.import_module(module_path)
            source_name = module.SOURCE_NAME

            # (b) Resolve source_id from the live conn["sources"]
            sid = get_source_id(conn, source_name)
            if sid is None:
                print(f"  [SKIP] Source not registered: {source_name!r}")
                results[source_name] = 0
                continue

            # (c) Print header
            print(f"\n── Running: {source_name}")

            # (d) Run fetcher
            count = module.fetch(conn, sid)

            # (e) Update last_synced
            update_last_synced(conn, sid)

            # (f) Persist after each fetcher so progress isn't lost
            save(conn)

            # (g) Store count
            results[source_name] = count

        except Exception as e:
            import traceback
            print(f"[FATAL] {module_path}: {e}")
            traceback.print_exc()
            # Extract SOURCE_NAME even if fetch() crashed
            try:
                mod = importlib.import_module(module_path)
                results[mod.SOURCE_NAME] = 0
            except Exception:
                results[module_path] = 0

    return results
