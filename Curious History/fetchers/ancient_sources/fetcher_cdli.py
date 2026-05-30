"""
fetcher_cdli.py — Cuneiform Digital Library Initiative (CDLI)

Auth     : Free account — set CDLI_API_TOKEN in .env (get from cdli.earth/account)
           Registered: himanks897@gmail.com
License  : CC BY 4.0 — commercial use allowed
Docs     : https://cdli.earth/docs/api
Coverage : Mesopotamia — Sumerian, Akkadian, Babylonian, Assyrian texts

MANUSCRIPT RULE: Only records WITH an English translation are stored.
Raw cuneiform, transliteration, and Sumerian/Akkadian text are NEVER
included in the summary. Users see readable English only.
"""

import os
import re
import time
import json
import requests
from dotenv import load_dotenv
from db import insert_record

load_dotenv()

SOURCE_NAME = "CDLI — Cuneiform Digital Library"
HEADERS     = {
    "User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/json",
}

# Add Bearer token if available (get from cdli.earth → account settings → API tokens)
_TOKEN = os.getenv("CDLI_API_TOKEN", "")
if _TOKEN:
    HEADERS["Authorization"] = f"Bearer {_TOKEN}"

# CDLI API endpoints — try v2 first (current), fall back to v1 (legacy)
_API_CANDIDATES = [
    "https://cdli.earth/api/v2",
    "https://cdli.earth/api/v1",
]
BASE_URL = _API_CANDIDATES[0]

# Search terms covering Mesopotamian history comprehensively
SEARCH_TOPICS = [
    "Sumerian", "Akkadian", "Babylonian", "Assyrian",
    "Gilgamesh", "Hammurabi", "Ur-Nammu", "Sargon",
    "Mesopotamia", "Nineveh", "Babylon", "Uruk", "Nippur", "Lagash",
    "cuneiform law", "temple hymn", "royal inscription",
    "creation myth", "flood narrative", "administrative text",
    "Neo-Assyrian", "Neo-Babylonian", "Old Babylonian",
    "Sumer", "Akkad", "Elam", "Mari",
]

# Era mapping from CDLI period strings
_ERA_MAP = {
    "early dynastic": "Ancient Mesopotamia (3000–2350 BCE)",
    "akkadian":       "Ancient Mesopotamia — Akkadian Empire (2350–2150 BCE)",
    "ur iii":         "Ancient Mesopotamia — Ur III (2112–2004 BCE)",
    "old babylonian": "Ancient Mesopotamia — Old Babylonian (2000–1600 BCE)",
    "middle assyrian":"Ancient Mesopotamia — Middle Assyrian (1400–1000 BCE)",
    "neo-assyrian":   "Ancient Mesopotamia — Neo-Assyrian Empire (911–612 BCE)",
    "neo-babylonian": "Ancient Mesopotamia — Neo-Babylonian (626–539 BCE)",
    "achaemenid":     "Ancient Persia — Achaemenid Period (550–330 BCE)",
    "hellenistic":    "Ancient Mesopotamia — Hellenistic (330–63 BCE)",
}


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _is_readable_english(text: str) -> bool:
    """
    Returns True only if text is readable English prose —
    NOT raw cuneiform Unicode, transliteration, or Sumerian.
    Rejects: empty strings, single-syllable transliteration patterns,
    text with >20% non-Latin characters.
    """
    if not text or len(text.strip()) < 15:
        return False
    text = text.strip()
    # Reject if mostly non-Latin (cuneiform Unicode block: U+12000–U+123FF)
    non_latin = sum(1 for c in text if ord(c) > 0x2000)
    if non_latin / max(len(text), 1) > 0.15:
        return False
    # Reject obvious transliteration: heavy hyphenation like "a-na i-li2-bi-ra-am"
    words = text.split()
    if not words:
        return False
    hyphenated = sum(1 for w in words if '-' in w and len(w) > 2)
    if len(words) >= 4 and hyphenated / len(words) > 0.5:
        return False
    # Must contain at least one full English word (>3 letters, all Latin)
    has_english = any(
        len(w) > 3 and w.isalpha() and all(ord(c) < 128 for c in w)
        for w in words
    )
    return has_english


def _parse_year(period_str: str):
    """
    Try to extract a representative BCE year from a CDLI period string.
    Returns negative integer for BCE, positive for CE, None if unparseable.
    """
    if not period_str:
        return None
    s = period_str.lower()
    # Patterns like "2100 BC", "ca. 2000 BCE", "3rd millennium BCE"
    m = re.search(r'(\d{3,4})\s*b\.?c', s)
    if m:
        return -int(m.group(1))
    m = re.search(r'(\d{3,4})\s*c\.?e\.?', s)
    if m:
        return int(m.group(1))
    # Millennium patterns: "3rd millennium" = -2500 (mid)
    m = re.search(r'(\d)(st|nd|rd|th)\s+millennium\s+bce?', s)
    if m:
        mill = int(m.group(1))
        return -(mill * 1000 - 500)
    return None


def _build_english_summary(artifact: dict) -> str:
    """
    Build a readable English summary from CDLI artifact data.
    Priority: translationEn → description → title + metadata context.
    Never includes raw cuneiform or transliteration.
    """
    # 1. Look for English translation in translations dict
    translations = artifact.get("translations") or {}
    if isinstance(translations, dict):
        en_trans = translations.get("en") or translations.get("english") or ""
        if _is_readable_english(en_trans):
            # Truncate to 800 chars to keep summaries manageable
            return en_trans.strip()[:800]

    # 2. Check for a direct translationEn field
    direct = (artifact.get("translationEn") or artifact.get("translation_en") or
              artifact.get("translation") or "")
    if isinstance(direct, str) and _is_readable_english(direct):
        return direct.strip()[:800]

    # 3. Use description if readable English
    desc = _strip_html(artifact.get("description") or artifact.get("summary") or "")
    if _is_readable_english(desc):
        return desc[:600]

    return ""  # No readable English available — caller will skip this record


# ── Built-in CDLI records (guaranteed baseline regardless of API availability) ─
# Key Mesopotamian texts with scholarly English translations.
_BUILTIN_RECORDS = [
    ("The Epic of Gilgamesh (Standard Babylonian Version)",
     "The Epic of Gilgamesh is the oldest surviving great work of literature, originating in ancient Mesopotamia. It tells the story of Gilgamesh, king of Uruk, and his companion Enkidu. After Enkidu's death, Gilgamesh travels to the ends of the earth seeking immortality, eventually learning from Utnapishtim the story of the Great Flood — a tale with striking parallels to the biblical Noah. The text exists on twelve cuneiform tablets and was compiled around 1200 BCE from older Sumerian stories.",
     "Ancient Mesopotamia — Old Babylonian (2000–1600 BCE)", "Mesopotamia", -1200,
     "https://cdli.earth/search"),
    ("Code of Hammurabi — Law Inscription",
     "The Code of Hammurabi (c. 1754 BCE) is one of the oldest deciphered writings of significant length in the world. It is a Babylonian legal text consisting of 282 laws with scaled punishments. Commissioned by Babylonian king Hammurabi, it includes laws on property, trade, family, and slavery. The famous 'eye for an eye' principle appears in this code. The original stele is in the Louvre museum in Paris.",
     "Ancient Mesopotamia — Old Babylonian (2000–1600 BCE)", "Mesopotamia — Babylon", -1754,
     "https://cdli.earth/search"),
    ("Enuma Elish — Babylonian Creation Myth",
     "The Enuma Elish is the Babylonian creation myth, dating to the 18th or 17th century BCE. Written on seven clay tablets, it describes how the god Marduk created the world from the body of the primordial goddess Tiamat. The text was recited during the Babylonian New Year festival (Akitu). It shares themes with other ancient creation narratives including the biblical Genesis account.",
     "Ancient Mesopotamia — Old Babylonian (2000–1600 BCE)", "Mesopotamia — Babylon", -1800,
     "https://cdli.earth/search"),
    ("Atrahasis Epic — Flood Narrative",
     "The Atrahasis Epic is an 18th-century BCE Akkadian epic about the creation of humans and the great flood sent by the gods. It predates and parallels the flood story of Noah in the Bible and the flood episode in the Epic of Gilgamesh. The text describes humans being created to relieve the gods of their labour and then almost destroyed by a divine flood when they became too noisy.",
     "Ancient Mesopotamia — Old Babylonian (2000–1600 BCE)", "Mesopotamia", -1700,
     "https://cdli.earth/search"),
    ("Royal Hymn of Shulgi (Ur III Period)",
     "Shulgi of Ur (c. 2094–2047 BCE) was the second king of the Third Dynasty of Ur and one of the most prolific commissioners of Sumerian literature. The Royal Hymns of Shulgi were composed to celebrate his achievements as warrior, athlete, scholar, and divine king. Shulgi claimed to be the son of the moon god Nanna and boasted of running between Ur and Nippur in a single day. These hymns were preserved in scribal schools as model texts.",
     "Ancient Mesopotamia — Ur III (2112–2004 BCE)", "Mesopotamia — Sumer", -2050,
     "https://cdli.earth/search"),
    ("Lamentation Over the Destruction of Ur",
     "A Sumerian literary composition dating to around 2000 BCE, written shortly after the fall of the Third Dynasty of Ur to the Elamites and Amorites. The text is a lament in the voice of the goddess Ningal, who pleads with the gods to spare Ur from destruction. It describes the city's fall and devastation in vivid terms and is one of the earliest examples of city lament literature.",
     "Ancient Mesopotamia — Ur III (2112–2004 BCE)", "Mesopotamia — Sumer", -2000,
     "https://cdli.earth/search"),
    ("Annals of Tiglath-Pileser I (Neo-Assyrian Royal Inscription)",
     "Tiglath-Pileser I (reigned c. 1115–1077 BCE) was one of the most powerful kings of the Middle Assyrian period. His annals, inscribed on clay prisms and tablets, describe his military campaigns across the ancient Near East — from Babylonia to the Mediterranean coast. He boasted of hunting lions, elephants, and wild bulls. These inscriptions are among the longest and most detailed Assyrian royal texts from this period.",
     "Ancient Mesopotamia — Middle Assyrian (1400–1000 BCE)", "Mesopotamia — Assyria", -1100,
     "https://cdli.earth/search"),
    ("Descent of Inanna to the Underworld",
     "One of the great Sumerian myths, the Descent of Inanna to the Underworld tells how the goddess Inanna (Ishtar in Akkadian) journeys through the seven gates of the underworld, removing a garment at each gate. She is killed by her sister Ereshkigal but eventually resurrected by the god Enki. The myth explores themes of death, rebirth, and the nature of divine power, and shares structural elements with later myths like Persephone and Orpheus.",
     "Ancient Mesopotamia", "Mesopotamia — Sumer", -2000,
     "https://cdli.earth/search"),
    ("Nabonidus Chronicle — Neo-Babylonian Historical Text",
     "The Nabonidus Chronicle is an ancient Babylonian text recording the reign of Nabonidus (556–539 BCE), the last king of the Neo-Babylonian Empire. It describes his extended stay in Tayma (Arabia), his neglect of the Babylonian New Year festival, and the conquest of Babylon by Cyrus the Great of Persia in 539 BCE without major resistance. The chronicle is a key primary source for the fall of the Babylonian Empire.",
     "Ancient Mesopotamia — Neo-Babylonian (626–539 BCE)", "Mesopotamia — Babylon", -539,
     "https://cdli.earth/search"),
    ("Cyrus Cylinder — Persian Conquest of Babylon",
     "The Cyrus Cylinder (539 BCE) is a clay cylinder inscribed with an account of Cyrus the Great's conquest of Babylon. Written in Akkadian cuneiform, it describes how Marduk chose Cyrus to replace Nabonidus and restore order. Cyrus presents himself as a liberating king who allowed deported peoples to return home and restored their temples. It has been called the first declaration of human rights, though this is debated by scholars. Now in the British Museum.",
     "Ancient Mesopotamia — Achaemenid Period (550–330 BCE)", "Persia / Mesopotamia", -539,
     "https://cdli.earth/search"),
]


def _probe_api_base() -> str:
    """Test which CDLI API version responds successfully."""
    for base in _API_CANDIDATES:
        try:
            r = requests.get(
                f"{base}/artifacts",
                headers=HEADERS,
                params={"search": "Gilgamesh", "limit": 1, "page": 1},
                timeout=12,
            )
            if r.status_code in (200, 201, 204):
                print(f"  [CDLI] API base confirmed: {base}")
                return base
        except Exception:
            continue
    print("  [CDLI] No live API available — using built-in records only")
    return ""


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    # ── Phase 1: Built-in records (guaranteed baseline) ───────────────────────
    for (title, summary, era, region, year, url) in _BUILTIN_RECORDS:
        ext_id = f"cdli_builtin_{title[:40].lower().replace(' ', '_')}"
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        ok = insert_record(conn, source_id, {
            "title":           title,
            "summary":         summary,
            "record_type":     "document",
            "region":          region,
            "era":             era,
            "date_year_start": year,
            "source_url":      url,
            "external_id":     ext_id,
            "tags":            ["Mesopotamia", "cuneiform", "ancient",
                                "CDLI", era, region],
        })
        if ok:
            inserted += 1
    print(f"  [CDLI] {inserted} built-in records loaded")

    # ── Phase 2: Live API search ───────────────────────────────────────────────
    api_base = _probe_api_base()
    if not api_base:
        print(f"  [CDLI] {inserted} English-translated records inserted (API offline)")
        return inserted

    for topic in SEARCH_TOPICS:
        page = 1
        while page <= 3:   # max 3 pages per topic to stay within rate limits
            try:
                resp = requests.get(
                    f"{api_base}/artifacts",
                    headers=HEADERS,
                    params={
                        "search": topic,
                        "q":      topic,   # some endpoints use 'q'
                        "limit":  50,
                        "page":   page,
                    },
                    timeout=20,
                )
            except Exception as e:
                print(f"  [CDLI] Network error for '{topic}' p{page}: {e}")
                break

            if resp.status_code == 429:
                print("  [CDLI] Rate limit hit — sleeping 60s")
                time.sleep(60)
                continue
            if resp.status_code == 401:
                print("  [CDLI] Unauthorised — set CDLI_API_TOKEN in .env")
                break
            if resp.status_code not in (200, 201):
                break

            try:
                payload = resp.json()
            except Exception:
                break

            # CDLI API may return list directly or wrapped in {"data": [...]}
            if isinstance(payload, list):
                artifacts = payload
            elif isinstance(payload, dict):
                artifacts = (payload.get("data") or payload.get("artifacts")
                             or payload.get("results") or [])
            else:
                artifacts = []

            if not artifacts:
                break   # no more pages

            for art in artifacts:
                ext_id = str(art.get("id") or art.get("cdli_id") or
                             art.get("designation") or "")
                if not ext_id or f"cdli_{ext_id}" in seen_ids:
                    continue
                seen_ids.add(f"cdli_{ext_id}")

                title = (art.get("title") or art.get("designation") or
                         art.get("name") or "").strip()
                if not title:
                    continue

                # Build English summary — SKIP if no readable English
                summary = _build_english_summary(art)
                if not summary:
                    continue   # enforces manuscript → English rule

                period   = (art.get("period") or art.get("period_specific") or "").strip()
                era_key  = period.lower()
                era      = next((v for k, v in _ERA_MAP.items() if k in era_key),
                                "Ancient Mesopotamia")
                year     = _parse_year(period)

                region   = "Mesopotamia"
                findspot = art.get("findspot_ancient") or art.get("provenience") or ""
                if findspot:
                    region = f"Mesopotamia — {findspot}"

                genre    = art.get("genre") or art.get("text_type") or ""
                subgenre = art.get("subgenre") or ""
                tags     = [t for t in ["Mesopotamia", "cuneiform", "ancient",
                                        period, genre, subgenre, topic]
                            if t and len(t) > 1]

                source_url = (art.get("url") or
                              f"https://cdli.earth/artifacts/{ext_id}")

                ok = insert_record(conn, source_id, {
                    "title":           title,
                    "summary":         summary,
                    "record_type":     "document",
                    "region":          region,
                    "era":             era,
                    "date_text":       period,
                    "date_year_start": year,
                    "source_url":      source_url,
                    "external_id":     f"cdli_{ext_id}",
                    "tags":            tags,
                })
                if ok:
                    inserted += 1
                    if inserted % 25 == 0:
                        print(f"  [CDLI] {inserted} records so far…")

            page += 1
            time.sleep(0.6)   # respect rate limit

        time.sleep(0.4)

    print(f"  [CDLI] {inserted} English-translated records inserted")
    return inserted
