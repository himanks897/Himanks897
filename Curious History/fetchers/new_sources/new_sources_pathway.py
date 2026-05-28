"""
new_sources_pathway.py — Orchestrator for all 8 new global-history sources.

Runs fetchers in sequence using importlib so one broken import cannot
prevent the others from running.  Saves progress after each fetcher.

Sources:
  1  National Library Norway (nb.no)       — NLOD 2.0, commercial OK
  2  National Library Sweden (KB / Libris) — CC0, commercial OK
  3  Finna Finland                          — CC0, commercial OK
  4  Polona Poland                          — Public Domain, commercial OK
  5  Europeana Romania                      — Public Domain / CC, commercial OK
  6  BnF Gallica France                     — Public Domain, commercial OK
  7  Europeana (broad)                      — Public Domain / CC, commercial OK
  8  DPLA                                   — Public Domain / CC0, commercial OK
"""

import importlib
from db import get_source_id, update_last_synced, save


def run_all(conn: dict) -> dict:
    """
    Run all 8 new-source fetchers in sequence.
    Returns dict: {source_name: records_inserted}
    """
    results: dict = {}

    # ── Step 1: Register all new sources ─────────────────────────────────────
    from fetchers.new_sources.new_sources_db_setup import insert_new_sources
    insert_new_sources(conn)
    save(conn)   # persist source registrations before fetching

    # ── Step 2: Run each fetcher ──────────────────────────────────────────────
    fetcher_modules = [
        "fetchers.new_sources.fetcher_norway",
        "fetchers.new_sources.fetcher_sweden",
        "fetchers.new_sources.fetcher_finland",
        "fetchers.new_sources.fetcher_poland",
        "fetchers.new_sources.fetcher_romania",
        "fetchers.new_sources.fetcher_gallica",
        "fetchers.new_sources.fetcher_europeana",
        "fetchers.new_sources.fetcher_dpla",
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
            save(conn)   # persist after each fetcher
            results[source_name] = count

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
