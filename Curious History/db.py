"""
db.py — JSON-based database for the Curious History data pipeline.

Storage:  curious_history.json  (human-readable, open in VS Code / any editor)
Populated by: python3 main.py --reset
Queried by:   app.py routes

JSON structure:
{
  "meta":    { "version", "last_updated", "total_records" },
  "sources": [ { "id", "name", "base_url", "api_type", "content_type", ... } ],
  "records": [ { "id", "source_id", "title", "summary", "full_text", ... } ]
}
"""

import os
import json
import re
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "curious_history.json")

# ── Source registry ───────────────────────────────────────────────────────────
SOURCES = [
    {"name": "Internet Archive",        "base_url": "https://archive.org",                           "api_type": "REST", "content_type": "full_text"},
    {"name": "Perseus Digital Library", "base_url": "https://gutenberg.org",                         "api_type": "REST", "content_type": "full_text"},
    {"name": "Our World in Data",       "base_url": "https://ourworldindata.org",                    "api_type": "REST", "content_type": "dataset"},
    {"name": "Qatar Digital Library",   "base_url": "https://archive.org",                           "api_type": "REST", "content_type": "metadata_only"},
    {"name": "Cabinet Papers UK",       "base_url": "https://discovery.nationalarchives.gov.uk/API", "api_type": "REST", "content_type": "full_text"},
    {"name": "Wikipedia",               "base_url": "https://en.wikipedia.org",                      "api_type": "REST", "content_type": "full_text"},
    {"name": "Wikidata",                "base_url": "https://www.wikidata.org",                      "api_type": "REST", "content_type": "full_text"},
    {"name": "Wikimedia Commons",       "base_url": "https://commons.wikimedia.org",                 "api_type": "REST", "content_type": "full_text"},
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _empty_db() -> dict:
    return {
        "meta":    {"version": "2.0", "last_updated": None, "total_records": 0},
        "sources": [],
        "records": [],
    }


def _source_content_type(conn: dict, source_id: int) -> str:
    for src in conn["sources"]:
        if src["id"] == source_id:
            return src.get("content_type", "full_text")
    return "full_text"


# ── Public API ────────────────────────────────────────────────────────────────

# ── In-memory cache ───────────────────────────────────────────────────────────
# The JSON is loaded once and kept in RAM.  On every call we check the file's
# mtime; if it hasn't changed (normal during serving) we return the cached dict
# directly — zero disk I/O, effectively instantaneous.
# The cache is invalidated automatically when main.py writes a new DB.

_CACHE: dict = {"data": None, "mtime": 0.0}


def get_connection() -> dict:
    """
    Return the in-memory database dict.
    Reads from disk only when curious_history.json has changed since last load.
    """
    try:
        mtime = os.path.getmtime(DB_PATH)
    except OSError:
        return _empty_db()

    if _CACHE["data"] is None or _CACHE["mtime"] != mtime:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            _CACHE["data"] = json.load(f)
        _CACHE["mtime"] = mtime

    return _CACHE["data"]


def save(conn: dict) -> None:
    """Write the in-memory database back to curious_history.json."""
    conn["meta"]["last_updated"] = datetime.utcnow().isoformat()
    conn["meta"]["total_records"] = len(conn.get("records", []))
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(conn, f, indent=2, ensure_ascii=False)
    # Bust the cache so the next get_connection() reloads the freshly-written file
    _CACHE["data"] = None
    _CACHE["mtime"] = 0.0


def reset_database() -> dict:
    """
    Wipe everything and rebuild from scratch.
    Seeds all sources and returns the empty data dict ready for fetchers.
    """
    data = _empty_db()
    for i, src in enumerate(SOURCES, start=1):
        data["sources"].append({
            "id":           i,
            "name":         src["name"],
            "base_url":     src["base_url"],
            "api_type":     src["api_type"],
            "content_type": src["content_type"],
            "last_synced":  None,
        })
    save(data)
    print("Database reset complete. All previous records and source integrations deleted.")
    return data


def get_source_id(conn: dict, source_name: str):
    for src in conn["sources"]:
        if src["name"] == source_name:
            return src["id"]
    return None


def update_last_synced(conn: dict, source_id: int) -> None:
    for src in conn["sources"]:
        if src["id"] == source_id:
            src["last_synced"] = datetime.utcnow().isoformat()
            return


def insert_record(conn: dict, source_id: int, data: dict) -> bool:
    """
    Insert one record. Returns True if inserted, False if skipped/duplicate.
    Deduplicates on (source_id, external_id).
    """
    title = data.get("title")
    if not title:
        return False

    ext_id  = data.get("external_id")
    records = conn.setdefault("records", [])

    # Deduplication check
    if ext_id:
        for r in records:
            if r.get("source_id") == source_id and r.get("external_id") == ext_id:
                return False

    content_type = _source_content_type(conn, source_id)

    # Normalise tags — keep as list in JSON
    tags = data.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [tags] if tags else []
    elif tags is None:
        tags = []

    record = {
        "id":             len(records) + 1,
        "source_id":      source_id,
        "external_id":    ext_id,
        "title":          title,
        "summary":        data.get("summary"),
        "full_text":      data.get("full_text"),
        "record_type":    data.get("record_type", "document"),
        "content_type":   content_type,
        "region":         data.get("region"),
        "era":            data.get("era"),
        "date_text":      data.get("date_text"),
        "date_year_start": data.get("date_year_start"),
        "image_url":      data.get("image_url"),
        "source_url":     data.get("source_url"),
        "tags":           tags,
        "created_at":     datetime.utcnow().isoformat(),
    }
    records.append(record)
    return True


def get_total_count(conn: dict) -> int:
    return len(conn.get("records", []))


def get_count_by_content_type(conn: dict) -> dict:
    counts = {}
    for r in conn.get("records", []):
        ct = r.get("content_type", "unknown")
        counts[ct] = counts.get(ct, 0) + 1
    return counts


# ── Numeral normalisation ─────────────────────────────────────────────────────
# Maps English number words ↔ Roman numerals so "world war two" matches
# "World War II" and vice versa.

_WORD_TO_ROMAN = {
    'one': 'i', 'two': 'ii', 'three': 'iii', 'four': 'iv', 'five': 'v',
    'six': 'vi', 'seven': 'vii', 'eight': 'viii', 'nine': 'ix', 'ten': 'x',
}
_ROMAN_TO_WORD = {v: k for k, v in _WORD_TO_ROMAN.items()}


def _normalise_numerals(text: str) -> str:
    """Replace number words with Roman numerals (for phrase matching)."""
    words = text.split()
    return ' '.join(_WORD_TO_ROMAN.get(w, w) for w in words)


# ── Keyword extraction ────────────────────────────────────────────────────────

def _extract_keywords(topic: str) -> list:
    """
    Extract meaningful search keywords from a topic string.
    Keeps historically important words (war, world, empire, etc.).
    For words > 8 chars, also adds the first 7 chars for prefix/suffix matching
    (e.g. "colonialism" → also "colonia", matching "colonial" and "decolonization").
    """
    _STOPWORDS = {
        'the', 'and', 'for', 'with', 'from', 'this', 'that', 'was', 'were',
        'in', 'of', 'a', 'an', 'at', 'by', 'on', 'to', 'its', 'or', 'but',
        'not', 'are', 'is', 'it', 'as', 'be', 'do', 'had', 'has', 'have',
        'also', 'when', 'been', 'more', 'into', 'over', 'two', 'one',
        'then', 'than', 'they', 'them', 'their', 'all', 'any', 'how',
    }
    raw = [w.lower() for w in re.split(r'\W+', topic)
           if len(w) >= 3 and w.lower() not in _STOPWORDS]

    expanded: list = []
    seen: set = set()
    for w in raw:
        if w not in seen:
            expanded.append(w)
            seen.add(w)
        if len(w) > 8:
            prefix = w[:7]
            if prefix not in seen:
                expanded.append(prefix)
                seen.add(prefix)
    return expanded


# ── Search ────────────────────────────────────────────────────────────────────

def _record_text(r: dict) -> str:
    """Concatenate all searchable text fields for a record (lowercase)."""
    parts = [
        r.get("title")    or "",
        r.get("summary")  or "",
        r.get("full_text") or "",
        " ".join(r.get("tags") or []),
    ]
    return " ".join(parts).lower()


def search_records_ranked(conn: dict, topic: str,
                          content_types=("full_text",),
                          limit: int = 20,
                          url_pattern: str = None) -> list:
    """
    Multi-keyword relevance-ranked search across all records in memory.

    Scoring is source-neutral — every database competes equally on content:

      Title match bonuses (record title contains the topic/keyword):
        +8   full phrase found in record title
        +2   per matching keyword found in title

      Body-text match bonuses (phrase/keyword found in summary or full_text):
        +10  full phrase found in body text  (rewards long primary-source docs)
        +1   per matching keyword in body text

      Content-depth bonus:
        +3   record has >400 chars of text (rewards IA/Cabinet Papers over
             short Wikipedia summaries; both get the bonus if rich enough)

      Image penalty:
        -4   record_type == "image" (images stay below textual records)

    Higher score → more relevant.
    Ties broken by total body-text length (more content = more useful).
    """
    keywords      = _extract_keywords(topic)
    topic_lower   = topic.lower()
    topic_numeral = _normalise_numerals(topic_lower)   # "world war two" → "world war ii"

    candidates = [
        r for r in conn.get("records", [])
        if r.get("content_type") in content_types
        and r.get("title")
        and (not url_pattern or url_pattern in (r.get("source_url") or ""))
    ]

    scored: dict = {}
    for r in candidates:
        title     = (r.get("title") or "").lower()
        body      = " ".join([
            r.get("summary")   or "",
            r.get("full_text") or "",
            " ".join(r.get("tags") or []),
        ]).lower()
        full_text = " ".join([title, body])  # everything combined
        score = 0

        # ── Exact title match ─────────────────────────────────────────────────
        # A record whose title IS the topic (e.g. "Roman Empire" for query
        # "Roman Empire") should always beat articles that merely contain the
        # phrase (e.g. "Holy Roman Empire").  Also fires on numeral-normalised
        # form so "World War II" matches query "world war two".
        if title == topic_lower or title == topic_numeral:
            score += 15

        # ── Phrase match ──────────────────────────────────────────────────────
        # Check both the original phrase and the numeral-normalised version
        # so "world war two" phrase-matches "world war ii" in title/body.
        phrase_in_title = topic_lower in title or topic_numeral in title
        phrase_in_body  = topic_lower in body  or topic_numeral in body
        if phrase_in_title:
            score += 8
        if phrase_in_body:
            score += 10          # separate from title — both can fire

        # ── Keyword match ─────────────────────────────────────────────────────
        for kw in keywords[:6]:
            if kw in title:
                score += 2
            if kw in body:      # separate from title — both can fire
                score += 1

        # ── Content depth bonus ───────────────────────────────────────────────
        # Rewards primary-source docs (IA, Cabinet Papers) that have rich text;
        # also rewards Wikipedia summaries if they are detailed (>400 chars).
        content_len = len(r.get("full_text") or r.get("summary") or "")
        if content_len > 400:
            score += 3

        # ── Image penalty ─────────────────────────────────────────────────────
        if r.get("record_type") == "image":
            score -= 4

        if score > 0:
            scored[r["id"]] = (r, score)

    # Ties broken by content length (longer = more useful)
    sorted_pairs = sorted(
        scored.values(),
        key=lambda x: (-x[1], -len(x[0].get("full_text") or x[0].get("summary") or ""))
    )
    return [pair[0] for pair in sorted_pairs[:limit]]


# Keep the old name as an alias so existing callers don't break
def search_records(conn: dict, query: str,
                   content_types=("full_text",),
                   limit: int = 20,
                   url_pattern: str = None) -> list:
    """Single-phrase search (alias kept for backward compatibility)."""
    return search_records_ranked(conn, query, content_types, limit, url_pattern)


def get_classical_by_keywords(conn: dict, keywords: list) -> list:
    """
    Return Classical Antiquity records that contain ANY of the given keywords.
    Used as a supplement to ensure primary sources appear for classical topics.
    """
    if not keywords:
        return []
    results = []
    for r in conn.get("records", []):
        if r.get("era") != "Classical Antiquity":
            continue
        text = _record_text(r)
        if any(kw in text for kw in keywords):
            results.append(r)
    return results
