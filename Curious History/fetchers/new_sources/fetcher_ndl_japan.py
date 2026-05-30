"""
fetcher_ndl_japan.py — National Diet Library Japan (NDL)

Endpoint : https://iss.ndl.go.jp/api/opensearch  (OpenSearch / RSS)
Auth     : None required
License  : NDL Open Data License — commercial use allowed
Docs     : https://iss.ndl.go.jp/information/api/
Coverage : Japan, Japanese history, East Asian history

MANUSCRIPT RULE: Only records with readable English titles and descriptions
are stored. Raw Japanese, Chinese, or Korean text is never stored or shown
to users — non-English records are silently skipped.
"""

import re
import time
import xml.etree.ElementTree as ET
import requests
from db import insert_record

SOURCE_NAME = "National Diet Library Japan"
BASE_URL    = "https://iss.ndl.go.jp/api/opensearch"
HEADERS     = {"User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)"}

DC_NS = "http://purl.org/dc/elements/1.1/"

# (topic, era, region)
TOPICS = [
    ("Japanese feudal history Edo period",       "Japanese History — Edo Period",    "Japan"),
    ("Samurai Japan history warfare",             "Japanese History",                 "Japan"),
    ("Meiji Restoration Japan modernisation",     "Japanese History — Meiji Era",     "Japan"),
    ("Japanese colonial history Korea Taiwan",    "Japanese History — Colonial Era",  "East Asia"),
    ("World War II Japan Pacific theatre",        "Second World War — Pacific",       "Japan"),
    ("Ancient Japan Nara Heian imperial",         "Japanese History — Ancient",       "Japan"),
    ("Tang Song dynasty China history",           "Chinese History",                  "China"),
    ("Korean history Joseon dynasty",             "Korean History",                   "Korea"),
    ("Silk Road East Asia trade history",         "Asian History — Silk Road",        "East Asia"),
    ("Buddhism history Asia spread",              "Asian History — Buddhism",         "Asia"),
    ("Mongol Empire China conquest",              "Medieval History — Mongol Empire", "East Asia"),
    ("Ming dynasty China history",               "Chinese History — Ming Dynasty",   "China"),
    ("Tokugawa Shogunate Japan history",          "Japanese History — Edo Period",    "Japan"),
    ("Hiroshima Nagasaki atomic bomb history",    "Second World War — Pacific",       "Japan"),
    ("Japanese imperialism Manchuria history",    "Japanese History — Imperial Era",  "East Asia"),
]


def _text(el, tag) -> str:
    if el is None:
        return ""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _is_readable_english(text: str) -> bool:
    """
    Return True only if text is readable English prose.
    Rejects Japanese (CJK: U+3000–U+9FFF), Korean, Chinese characters.
    """
    if not text or len(text.strip()) < 10:
        return False
    t = text.strip()
    # CJK Unified Ideographs, Hiragana, Katakana, Hangul
    cjk_count = sum(1 for c in t if (
        0x3000 <= ord(c) <= 0x9FFF or   # CJK / Hiragana / Katakana
        0xAC00 <= ord(c) <= 0xD7AF or   # Hangul Syllables
        0x4E00 <= ord(c) <= 0x9FFF      # CJK Ideographs
    ))
    if cjk_count / max(len(t), 1) > 0.05:
        return False
    # Need at least 3 English words (all-ASCII, >3 chars)
    words = t.split()
    english = sum(1 for w in words if len(w) > 3 and w.isalpha()
                  and all(ord(c) < 128 for c in w))
    return english >= 3


def fetch(conn: dict, source_id: int) -> int:
    inserted = 0
    seen_ids: set = set()

    for (topic, era, region) in TOPICS:
        try:
            resp = requests.get(
                BASE_URL,
                headers=HEADERS,
                params={
                    "q":         topic,
                    "cnt":       20,
                    "type":      1,      # books
                    "mediatype": 1,
                    # NDL language codes: "eng" for English. Using no lang filter
                    # gets broader results; English readability guard below filters.
                },
                timeout=20,
            )
            if resp.status_code != 200:
                time.sleep(1)
                continue

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as e:
                print(f"  [NDL] XML parse error for '{topic}': {e}")
                continue

            channel = root.find("channel")
            if channel is None:
                continue

            for item in channel.findall("item"):
                title   = _text(item, "title")
                link    = _text(item, "link")
                desc    = _text(item, "description")
                date    = _text(item, f"{{{DC_NS}}}date")
                subject = _text(item, f"{{{DC_NS}}}subject")

                if not title or not link:
                    continue

                # English readability guard — skip Japanese-title records
                if not _is_readable_english(title):
                    continue

                ext_id = link.split("/")[-1] if "/" in link else link
                full_id = f"ndl-{ext_id}"
                if full_id in seen_ids:
                    continue
                seen_ids.add(full_id)

                # Filter description: use only if readable English
                summary = None
                if desc and _is_readable_english(desc):
                    summary = desc[:500]
                else:
                    summary = (f"{title}: a scholarly work on {era} "
                               f"from the National Diet Library Japan.")

                tags = [t.strip() for t in subject.split(";") if t.strip()][:8]
                tags += ["National Diet Library Japan", era]

                ok = insert_record(conn, source_id, {
                    "title":       title[:300],
                    "summary":     summary,
                    "date_text":   date[:20],
                    "region":      region,
                    "era":         era,
                    "source_url":  link,
                    "external_id": full_id,
                    "record_type": "document",
                    "tags":        tags,
                })
                if ok:
                    inserted += 1

            time.sleep(0.6)

        except Exception as e:
            print(f"  [NDL] Error for '{topic}': {e}")
            time.sleep(1)

    print(f"  [{SOURCE_NAME}] {inserted} records inserted")
    return inserted
