"""
fix_database_quality.py — One-time database quality pass.

Applies:
  1. Era back-fill  — infer_era() for all 26,795 records missing the era field
  2. Title cleaning — truncate titles >200 chars at natural phrase boundary
  3. Norway summaries — replace empty summaries with synthetic descriptions
  4. Remove truly empty records from National Library Norway (titles-only, no tags)

Run: python fix_database_quality.py
"""

import re, json, sys, os, time
from pathlib import Path

# Make sure project root is on path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from db import get_connection, save, DB_PATH
from fetchers.new_sources.era_utils import infer_era

# ── helpers ───────────────────────────────────────────────────────────────────

_TITLE_BREAK = re.compile(r'[,;:]|\s+[-–—]\s+|\.\s+(?=[A-Z])')

def _clean_title(title: str, max_len: int = 200) -> str:
    """Truncate title at the first natural phrase boundary ≤ max_len chars."""
    if not title or len(title) <= max_len:
        return title
    # Find the first natural break within the allowed range
    for m in _TITLE_BREAK.finditer(title[:max_len + 30]):
        if m.start() <= max_len:
            candidate = title[:m.start()].strip()
            if len(candidate) >= 15:   # don't truncate to something too short
                return candidate
    # Hard-truncate as fallback
    return title[:max_len].strip()


def _is_readable_latin(text: str, threshold: float = 0.15) -> bool:
    if not text:
        return True
    non_latin = sum(1 for c in text if ord(c) > 0x024F)
    return non_latin / max(len(text), 1) < threshold


# ── main pass ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("CURIOUS HISTORY — DATABASE QUALITY FIX")
    print("=" * 62)
    print(f"  Database: {DB_PATH}")

    conn    = get_connection()
    records = conn.get("records", [])
    source_map = {s["id"]: s["name"] for s in conn.get("sources", [])}
    total   = len(records)
    print(f"  Total records: {total}\n")

    era_filled     = 0
    titles_cleaned = 0
    norway_fixed   = 0
    empty_removed  = 0

    norway_id = next(
        (s["id"] for s in conn["sources"]
         if "norway" in s["name"].lower() and "nb.no" in s.get("base_url", "")),
        None
    )

    surviving = []
    for r in records:

        # ── 1. Era back-fill ──────────────────────────────────────────────────
        if not r.get("era"):
            hint = " ".join(filter(None, [
                r.get("title", ""),
                r.get("region", ""),
                " ".join(r.get("tags") or [])[:120],
            ]))
            inferred = infer_era(hint.lower(), fallback="")
            if inferred:
                r["era"] = inferred
                era_filled += 1

        # ── 2. Title cleaning ─────────────────────────────────────────────────
        title = r.get("title") or ""
        if len(title) > 200:
            new_title = _clean_title(title)
            if new_title != title:
                r["title"] = new_title
                titles_cleaned += 1

        # ── 3. Norway synthetic summary ───────────────────────────────────────
        if r.get("source_id") == norway_id:
            summary = r.get("summary") or ""
            if not summary or len(summary.strip()) < 40:
                # Build from tags + title
                tags_text = ", ".join(
                    t for t in (r.get("tags") or [])
                    if t and t not in ["Norway", "National Library Norway", "NLOD"]
                )[:200]
                r["summary"] = (
                    f"A work from the National Library of Norway: {r.get('title', '')}. "
                    + (f"Topics: {tags_text}." if tags_text else "")
                    + " Part of the Norwegian national digital heritage collection."
                )[:500]
                norway_fixed += 1

        # ── 4. Remove truly useless records ───────────────────────────────────
        # A record is useless if: no summary, no full_text, AND title is
        # non-Latin (transliterated, e.g. Persian, Arabic titles from BL).
        has_text  = bool((r.get("summary") or "").strip() or
                         (r.get("full_text") or "").strip())
        has_latin_title = _is_readable_latin(r.get("title") or "")

        if not has_text and not has_latin_title:
            empty_removed += 1
            continue   # drop the record

        surviving.append(r)

    conn["records"] = surviving
    removed_total   = total - len(surviving)

    print(f"  Era back-filled:      {era_filled:>6} records")
    print(f"  Titles cleaned:       {titles_cleaned:>6} records (were >200 chars)")
    print(f"  Norway summaries:     {norway_fixed:>6} synthetic summaries generated")
    print(f"  Records removed:      {removed_total:>6} (non-Latin, no text)")
    print(f"  Surviving records:    {len(surviving):>6}")
    print()

    # Re-number IDs sequentially to keep the DB consistent
    for i, r in enumerate(surviving, 1):
        r["id"] = i
    conn["meta"]["total_records"] = len(surviving)

    print("  Saving database…", end="", flush=True)
    save(conn)
    print(" done.")
    print("=" * 62)


if __name__ == "__main__":
    main()
