#!/usr/bin/env python3
"""
run_fix_gallica_dpla.py — Re-run the two sources that failed in the main pipeline:
  - BnF Gallica France (was IP-blocked; now uses Europeana COUNTRY:france)
  - DPLA              (was HTTP 400 due to bad 'fields' param; now fixed)
"""

import importlib
import os
import sys
import time

# ── Load .env ────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

# ── Ensure project root is on path ───────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from db import get_connection, save
from fetchers.new_sources.new_sources_db_setup import insert_new_sources

DB_PATH = os.path.join(BASE_DIR, "curious_history.json")
assert os.path.isfile(DB_PATH), f"DB not found: {DB_PATH}"

EUROPEANA_KEY = os.environ.get("EUROPEANA_API_KEY", "")
DPLA_KEY      = os.environ.get("DPLA_API_KEY", "")
print(f"✓ EUROPEANA_API_KEY: {'set' if EUROPEANA_KEY else 'MISSING!'}")
print(f"✓ DPLA_API_KEY:      {'set' if DPLA_KEY else 'MISSING!'}")

conn = get_connection()

# Ensure source IDs exist
insert_new_sources(conn)
save(conn)

import json as _json
before = len(conn.get("records", []))
print(f"\nRecords before run: {before:,}\n")

FETCHERS = [
    ("BnF Gallica France",   "fetchers.new_sources.fetcher_gallica"),
    ("DPLA",                 "fetchers.new_sources.fetcher_dpla"),
]


def _get_source_id(conn, name):
    for s in conn.get("sources", []):
        if s["name"] == name:
            return s["id"]
    return None


total_added = 0
for label, module_path in FETCHERS:
    print(f"── Running: {label}")
    source_id = _get_source_id(conn, label)
    if source_id is None:
        print(f"  [!] Source '{label}' not found in DB — skipping")
        continue
    try:
        mod     = importlib.import_module(module_path)
        added   = mod.fetch(conn, source_id)
        total_added += added
        save(conn)
        print(f"  ✓ {label}: {added:,} records added, DB saved\n")
    except Exception as e:
        print(f"  ✗ {label} FAILED: {e}\n")
        import traceback; traceback.print_exc()
    time.sleep(1)

after = len(conn.get("records", []))
print("=" * 60)
print(f"  Records added this run : {total_added:,}")
print(f"  Total records in DB    : {after:,}")
print("=" * 60)
