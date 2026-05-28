"""
run_new_sources_pathway.py — Entry point for 8-source global history integration.

Run: python3 run_new_sources_pathway.py

This script EXTENDS the existing curious_history.json database by adding
records from 8 new open-licence sources covering geographic gaps.

Sources:
  1  National Library Norway (nb.no)       — Nordic/Norwegian history, NLOD 2.0
  2  National Library Sweden (KB / Libris) — Swedish/Nordic history, CC0
  3  Finna Finland                          — Finnish/Nordic history, CC0
  4  Polona Poland                          — Polish/Central European history
  5  Europeana Romania                      — Romanian/Balkan history
  6  BnF Gallica France                     — French/colonial history, Public Domain
  7  Europeana (broad)                      — Global gaps (Africa, Asia, Americas)
  8  DPLA                                   — US/diverse communities history

API keys (already in .env):
  EUROPEANA_API_KEY = oadoncen
  DPLA_API_KEY      = c629af0dca8bf286a311fbd418832320
"""

import os
import sys

# ── Load environment variables from .env ──────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed — try loading .env manually
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

# ── STEP 1: Pre-run checklist ─────────────────────────────────────────────────
print("─" * 66)
print("BEFORE RUNNING — CHECKLIST:")
print("  1. curious_history.json exists?     (checked below)")
print("  2. Internet connection active?       (required for all sources)")
print("  3. EUROPEANA_API_KEY loaded?         (checked below)")
print("  4. DPLA_API_KEY loaded?              (checked below)")
print("─" * 66)

# ── STEP 2: Verify database exists ───────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "curious_history.json")
if not os.path.exists(DB_PATH):
    print("\nERROR: curious_history.json not found.")
    print("Run the main pipeline first: python3 main.py --reset")
    sys.exit(1)
print(f"\n✓ Database found: {DB_PATH}")

# ── STEP 3: Verify API keys ───────────────────────────────────────────────────
eu_key   = os.environ.get("EUROPEANA_API_KEY", "")
dpla_key = os.environ.get("DPLA_API_KEY", "")
print(f"✓ EUROPEANA_API_KEY: {'set (' + eu_key[:6] + '...)' if eu_key else '✗ NOT SET — Europeana/Romania fetchers will fail'}")
print(f"✓ DPLA_API_KEY:      {'set (' + dpla_key[:8] + '...)' if dpla_key else '✗ NOT SET — DPLA fetcher will fail'}")

# ── STEP 4: Load database ────────────────────────────────────────────────────
import db

conn         = db.get_connection()
before_count = len(conn.get("records", []))
print(f"\nRecords before run: {before_count:,}")

# ── STEP 5: Run pipeline ──────────────────────────────────────────────────────
print("\nStarting 8-source global history pipeline...\n")

from fetchers.new_sources.new_sources_pathway import run_all
results = run_all(conn)

# ── STEP 6: Reload for accurate count ────────────────────────────────────────
conn        = db.get_connection()
after_count = len(conn.get("records", []))
added       = after_count - before_count

# ── STEP 7: Summary report ────────────────────────────────────────────────────
print("\n")
print("=" * 66)
print("8-SOURCE GLOBAL HISTORY PIPELINE — INTEGRATION COMPLETE")
print("=" * 66)
for source_name, count in results.items():
    status = "✓" if count > 0 else "✗"
    short  = source_name.replace("National Library ", "NL ").replace("BnF Gallica ", "Gallica ")
    print(f"  {status}  {short:<46} {count:>5} records")
print("─" * 66)
print(f"  RECORDS ADDED THIS RUN:              {added:>6,}")
print(f"  TOTAL RECORDS IN DATABASE:           {after_count:>6,}")
print("─" * 66)
print("  BREAKDOWN BY CONTENT TYPE:")
from db import get_count_by_content_type
for ctype, cnt in get_count_by_content_type(conn).items():
    print(f"    {ctype:<28} {cnt:>6,} records")
print("=" * 66)

# ── STEP 8: Source breakdown ──────────────────────────────────────────────────
print("\n  RECORDS BY SOURCE:")
source_map = {s["id"]: s["name"] for s in conn.get("sources", [])}
source_counts: dict = {}
for r in conn.get("records", []):
    sname = source_map.get(r.get("source_id"), "Unknown")
    source_counts[sname] = source_counts.get(sname, 0) + 1
for sname, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
    print(f"    {sname:<46} {cnt:>6,}")
print("=" * 66)

if added == 0:
    print("\n⚠  No new records were added.")
    print("   Possible causes:")
    print("   • All records already exist (deduplication) — safe to re-run")
    print("   • Network connectivity issue")
    print("   • API endpoint has changed")
    print("   Check the output above for [WARN] / [ERROR] messages.\n")
else:
    print(f"\n✓ {added:,} new records added successfully.\n")
