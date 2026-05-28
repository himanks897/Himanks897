"""
main.py — Curious History data pipeline orchestrator.

Usage:
    python main.py              # add new records without wiping existing data
    python main.py --reset      # wipe DB, rebuild from scratch (takes ~30 min)
    python main.py --new-only   # run only the 10 new global sources

Database : curious_history.json
Sources  : 28+ free public APIs (original 8 + 10 new global sources via
           new_sources_pathway)

New global sources cover:
  Japan (NDL), India (IA DLI), Africa (IA), Middle East (Europeana ME,
  OpenITI), South/SE Asia (SOAS, HathiTrust), Latin America (LOC,
  Memoria Chilena), plus expanded Qatar Digital Library queries.
"""

import sys
import importlib
import db

# ── Argument parsing ──────────────────────────────────────────────────────────
reset_mode    = "--reset"    in sys.argv
new_only_mode = "--new-only" in sys.argv

# ── Database initialisation ───────────────────────────────────────────────────
if reset_mode:
    print("=" * 62)
    print("RESET MODE ACTIVATED")
    print("Deleting ALL existing records and source integrations.")
    print("Rebuilding Curious History database from scratch...")
    print("Sources: Internet Archive, Perseus, Our World in Data,")
    print("         Qatar Digital Library, Cabinet Papers UK")
    print("=" * 62)
    conn = db.reset_database()
else:
    conn = db.get_connection()

# ── Fetcher module list (imported at runtime — one broken import cannot
#    kill the others) ───────────────────────────────────────────────────
# 8 free public API fetchers (no API key required).
# Removed: USHMM Holocaust Encyclopedia, World History Encyclopedia.
# Wikipedia, Wikidata, Wikimedia Commons are BOTH:
#   • pre-fetched here (pipeline) for full-text search coverage
#   • queried live in app.py for real-time article / fact / image results
FETCHER_MODULES = [
    "fetchers.internet_archive",
    "fetchers.perseus",
    "fetchers.our_world_in_data",
    "fetchers.qatar_digital_library",
    "fetchers.cabinet_papers",
    "fetchers.wikipedia_pipeline",
    "fetchers.wikidata_pipeline",
    "fetchers.wikimedia_pipeline",
]


# ── Runner ────────────────────────────────────────────────────────────────────
def run_fetcher(module_path, conn):
    try:
        module      = importlib.import_module(module_path)
        source_name = module.SOURCE_NAME
        source_id   = db.get_source_id(conn, source_name)
        if source_id is None:
            print(f"[SKIP] '{source_name}' not found in sources table.")
            return 0
        print(f"\n{'─' * 62}")
        print(f"Fetching: {source_name}")
        print(f"{'─' * 62}")
        count = module.fetch(conn, source_id)
        db.update_last_synced(conn, source_id)
        return count
    except Exception as e:
        print(f"[FATAL ERROR] {module_path}: {e}")
        import traceback
        traceback.print_exc()
        return 0


# ── Main execution loop ───────────────────────────────────────────────────────
results        = {}
total_inserted = 0

for module_path in FETCHER_MODULES:
    count      = run_fetcher(module_path, conn)
    short_name = module_path.split(".")[-1]
    results[short_name] = count
    total_inserted += count


# ── Final summary report ──────────────────────────────────────────────────────
counts_by_type = db.get_count_by_content_type(conn)

print("\n")
print("=" * 62)
print("CURIOUS HISTORY DATABASE BUILD COMPLETE")
print("=" * 62)
for name, count in results.items():
    status = "✓" if count > 0 else "✗"
    print(f"  {status}  {name:<42} {count:>5} records")
print("─" * 62)
print(f"  TOTAL RECORDS INSERTED THIS RUN:    {total_inserted}")
print(f"  TOTAL RECORDS IN DATABASE:          {db.get_total_count(conn)}")
print("─" * 62)
print("  BREAKDOWN BY CONTENT TYPE:")
for ctype, cnt in counts_by_type.items():
    print(f"    {ctype:<20} {cnt:>5} records")
print("=" * 62)

db.save(conn)
print(f"  Database saved → curious_history.json")

# ── Also run the new global sources (unless --new-only already ran them) ──────
if not new_only_mode:
    print("\n\n" + "=" * 62)
    print("RUNNING NEW GLOBAL SOURCES (Asia, Africa, Middle East, Latin America)")
    print("=" * 62)
    try:
        from fetchers.new_sources.new_sources_pathway import run_all as run_new_sources
        new_results = run_new_sources(conn)
        print("\n" + "─" * 62)
        print("  NEW GLOBAL SOURCES SUMMARY:")
        for name, count in new_results.items():
            status = "✓" if count > 0 else "✗"
            print(f"  {status}  {name:<42} {count:>5} records")
        print(f"  TOTAL RECORDS IN DATABASE: {db.get_total_count(conn)}")
        print("─" * 62)
        db.save(conn)
        print("  Database saved with new global sources.")
    except Exception as e:
        print(f"[WARN] New sources pathway failed: {e}")
        import traceback
        traceback.print_exc()
