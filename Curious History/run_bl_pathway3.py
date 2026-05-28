"""
run_bl_pathway3.py — Entry point for British Library Pathway 3 integration.

Run: python3 run_bl_pathway3.py

This script EXTENDS the existing curious_history.json database by
adding records from 5 British Library open data sub-sources.
It does NOT reset or delete existing records.

Sub-sources:
  A  BL Research Repository (OAI-PMH)   — bl.iro.bl.uk
  B  BL Zenodo Datasets                 — zenodo.org
  C  BL GitHub Georeferencer            — github.com/britishlibrary
  D  BL Wikimedia Commons               — commons.wikimedia.org   [no key needed]
  E  BL British National Bibliography   — Open Library + Zenodo
"""

import os
import sys

# ── STEP 1: Pre-run checklist ─────────────────────────────────────────────────
print("─" * 62)
print("BEFORE RUNNING — CHECKLIST:")
print("  1. curious_history.json exists? (checked below)")
print("  2. Internet connection active? (required for all sources)")
print("  3. All sub-sources require no API key — ready to run.")
print("─" * 62)

# ── STEP 2: Verify database exists ───────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "curious_history.json")
if not os.path.exists(DB_PATH):
    print("\nERROR: curious_history.json not found.")
    print("Run the main pipeline first: python3 main.py --reset")
    sys.exit(1)
print(f"\n✓ Database found: {DB_PATH}")

# ── STEP 3: Load the JSON database (in-memory cache) ─────────────────────────
import db

conn = db.get_connection()
before_count = len(conn.get("records", []))
print(f"Records before BL Pathway 3 run: {before_count:,}")

# ── STEP 4: Run the orchestrator ──────────────────────────────────────────────
print("\nStarting British Library Pathway 3 data pipeline...\n")

from fetchers.bl.bl_pathway3 import run_all
results = run_all(conn)

# ── STEP 5: Reload to get accurate after-count ────────────────────────────────
# bl_pathway3 calls db.save() after each fetcher which busts the cache;
# calling get_connection() re-loads the freshly saved file.
conn         = db.get_connection()
after_count  = len(conn.get("records", []))

# ── STEP 6: Print summary report ──────────────────────────────────────────────
added = after_count - before_count

print("\n")
print("=" * 62)
print("BRITISH LIBRARY PATHWAY 3 — INTEGRATION COMPLETE")
print("=" * 62)
for source_name, count in results.items():
    status = "✓" if count > 0 else "✗"
    short  = (source_name
              .replace("BL ", "")
              .replace("British Library ", ""))
    print(f"  {status}  {short:<42} {count:>5} records")
print("─" * 62)
print(f"  RECORDS ADDED THIS RUN:          {added:>6,}")
print(f"  TOTAL RECORDS IN DATABASE:       {after_count:>6,}")
print("─" * 62)
print("  BREAKDOWN BY CONTENT TYPE:")
from db import get_count_by_content_type
for ctype, cnt in get_count_by_content_type(conn).items():
    print(f"    {ctype:<25} {cnt:>6,} records")
print("=" * 62)

print("\nFrontend query to retrieve BL records:")
print('  db.search_records_ranked(conn, topic)')
print('  — BL records compete equally in the relevance ranking.')
print('  — Filter by source name in app.py if you need BL-only results.\n')

# ── Resumable-run reminders ───────────────────────────────────────────────────
if os.path.exists("./bl_oai_token.txt"):
    print("─" * 62)
    print("  NOTE — OAI-PMH harvest was paused (20-page cap)")
    print("    Re-run to continue:  python3 run_bl_pathway3.py")
    print("    (token in bl_oai_token.txt is loaded automatically)")
    print("─" * 62)

# ── Manual CSV fallback reminder (only shown when BNB got 0 records) ─────────
bnb_count = results.get("BL British National Bibliography", -1)
if bnb_count == 0:
    print("─" * 62)
    print("  NOTE — BNB returned 0 records this run.")
    print("  Manual fallback: Download BNB CSV from bl.iro.bl.uk,")
    print("  save as bl_bnb_manual.csv in the project root, re-run.")
    print("─" * 62)
