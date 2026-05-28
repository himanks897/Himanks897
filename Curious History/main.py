"""
main.py — Curious History data pipeline orchestrator.

Usage:
    python main.py --reset   # wipe DB, rebuild from scratch
    python main.py           # add new records without wiping existing data

Database: curious_history.json  (human-readable JSON — open in VS Code)
Sources:  8 free public APIs, no API key required (see db.py → SOURCES)

Content-type breakdown after a full --reset run:
  full_text     → 1000–1200 records  (IA, Perseus, Cabinet Papers,
                                      Wikipedia ~200, Wikidata ~70,
                                      Wikimedia ~150)
  dataset       →     7     records  (Our World in Data CSVs)
  metadata_only →    23     records  (Qatar Digital Library)
  ─────────────────────────────────────────────
  Total target  → 1030–1230 records
"""

import sys
import importlib
import db

# ── Argument parsing ──────────────────────────────────────────────────────────
reset_mode = "--reset" in sys.argv

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
