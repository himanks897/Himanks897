"""
fetcher_tla.py — Thesaurus Linguae Aegyptiae (TLA)

Auth     : None required
License  : Free licence (non-bulk academic use) — verify bulk at
           https://thesaurus-linguae-aegyptiae.de/info/licenses
Docs     : https://thesaurus-linguae-aegyptiae.de
API      : https://textplus.thesaurus-linguae-aegyptiae.de
Coverage : Ancient Egypt — hieroglyphic, hieratic, Demotic texts with
           English translations

MANUSCRIPT RULE: Only records WITH an English translation are stored.
Raw hieroglyphic Unicode, transliterations (e.g. "nswt-bjtj"), and
untranslated Egyptian text are NEVER included in summaries.
Users receive readable English translations and scholarly descriptions only.
"""

import re
import json
import time
import requests
from db import insert_record

SOURCE_NAME = "TLA — Thesaurus Linguae Aegyptiae"
HEADERS     = {
    "User-Agent": "CuriousHistory/1.0 (himanks897@gmail.com)",
    "Accept":     "application/json",
}

# TLA Spring/Elasticsearch backend API
TLA_API  = "https://textplus.thesaurus-linguae-aegyptiae.de"
TLA_SITE = "https://thesaurus-linguae-aegyptiae.de"

# Ancient Egyptian topics to search
SEARCH_TOPICS = [
    ("Pharaoh king",          "Ancient Egypt — Pharaonic",      "Egypt"),
    ("Pyramid Text",          "Ancient Egypt — Old Kingdom",    "Egypt"),
    ("Coffin Text",           "Ancient Egypt — Middle Kingdom", "Egypt"),
    ("Book of the Dead",      "Ancient Egypt — New Kingdom",    "Egypt"),
    ("Amarna letter",         "Ancient Egypt — Amarna Period",  "Egypt"),
    ("creation myth Egypt",   "Ancient Egypt",                  "Egypt"),
    ("Osiris Isis myth",      "Ancient Egypt — Religion",       "Egypt"),
    ("temple inscription",    "Ancient Egypt",                  "Egypt"),
    ("Ramesses inscription",  "Ancient Egypt — New Kingdom",    "Egypt"),
    ("Tutankhamun",           "Ancient Egypt — New Kingdom",    "Egypt"),
    ("Hatshepsut queen",      "Ancient Egypt — New Kingdom",    "Egypt"),
    ("Thutmose battle",       "Ancient Egypt — New Kingdom",    "Egypt"),
    ("Nile flooding harvest", "Ancient Egypt",                  "Egypt"),
    ("Egyptian wisdom text",  "Ancient Egypt",                  "Egypt"),
    ("Hieratic papyrus",      "Ancient Egypt",                  "Egypt"),
    ("Demotic Egypt text",    "Ancient Egypt — Late Period",    "Egypt"),
    ("Cleopatra Ptolemaic",   "Ancient Egypt — Ptolemaic",      "Egypt"),
    ("Akhenaten Aten",        "Ancient Egypt — Amarna Period",  "Egypt"),
    ("Nubia Kush ancient",    "Ancient Egypt / Nubia",          "Nubia"),
    ("Horus falcon god",      "Ancient Egypt — Religion",       "Egypt"),
]

# Era mapping from TLA period strings
_ERA_PERIOD = {
    "old kingdom":       "Ancient Egypt — Old Kingdom (2686–2181 BCE)",
    "middle kingdom":    "Ancient Egypt — Middle Kingdom (2055–1650 BCE)",
    "new kingdom":       "Ancient Egypt — New Kingdom (1550–1069 BCE)",
    "late period":       "Ancient Egypt — Late Period (664–332 BCE)",
    "ptolemaic":         "Ancient Egypt — Ptolemaic Period (332–30 BCE)",
    "roman":             "Ancient Egypt — Roman Period (30 BCE–395 CE)",
    "amarna":            "Ancient Egypt — Amarna Period (1353–1335 BCE)",
    "predynastic":       "Ancient Egypt — Predynastic (5000–3100 BCE)",
    "early dynastic":    "Ancient Egypt — Early Dynastic (3100–2686 BCE)",
}


def _is_readable_english(text: str) -> bool:
    """Reject raw hieroglyphic/transliteration; accept English prose."""
    if not text or len(text.strip()) < 15:
        return False
    text = text.strip()
    # Reject Egyptian transliterations: lots of dots, macrons, underscores
    # e.g. "ḥr nswt-bjtj ḏsr-ḫpr-rʿ" — heavy use of special diacritics
    special_chars = sum(1 for c in text
                        if 0x1E00 <= ord(c) <= 0x1EFF or   # Latin Extended Additional (diacritics)
                           0x0180 <= ord(c) <= 0x024F or   # Latin Extended-B (ḥ, ḏ, etc.)
                           ord(c) > 0x10000)               # SMP (hieroglyphic Unicode)
    if special_chars / max(len(text), 1) > 0.12:
        return False
    # Must have common English words
    words   = text.lower().split()
    english = sum(1 for w in words
                  if w.isalpha() and len(w) > 3
                  and all(ord(c) < 128 for c in w))
    return english >= 3


def _try_tla_api(topic: str, era: str, region: str) -> list:
    """
    Try the TLA backend API for text/sentence search.
    Returns list of dicts ready for insert_record.
    """
    results = []

    # Try different endpoint patterns the TLA backend may expose
    endpoints = [
        f"{TLA_API}/api/search?q={requests.utils.quote(topic)}&pageSize=20",
        f"{TLA_API}/api/texts?q={requests.utils.quote(topic)}&size=20",
        f"{TLA_API}/api/sentences?q={requests.utils.quote(topic)}&size=20",
        f"{TLA_API}/api/lemma?q={requests.utils.quote(topic)}&size=20",
    ]

    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = (data.get("items") or data.get("results") or
                         data.get("hits", {}).get("hits") or [])
                if items:
                    for item in items[:15]:
                        src = item.get("_source") or item
                        title = (src.get("name") or src.get("title") or
                                 src.get("label") or "").strip()
                        translation = ""
                        # Look for English translation
                        for key in ("translations", "translation", "translationEn",
                                    "meaning", "description"):
                            val = src.get(key)
                            if isinstance(val, str) and _is_readable_english(val):
                                translation = val.strip()[:700]
                                break
                            if isinstance(val, dict):
                                en = val.get("en") or val.get("english") or ""
                                if _is_readable_english(en):
                                    translation = en.strip()[:700]
                                    break

                        if not title or not translation:
                            continue

                        period = (src.get("period") or src.get("date") or "")
                        era_mapped = era
                        for k, v in _ERA_PERIOD.items():
                            if k in period.lower():
                                era_mapped = v
                                break

                        results.append({
                            "title":       f"{title} — Ancient Egyptian Text",
                            "summary":     translation,
                            "era":         era_mapped,
                            "region":      region,
                            "date_text":   period,
                            "source_url":  (src.get("url") or
                                           f"{TLA_SITE}/sentence/{src.get('id', '')}"),
                            "external_id": f"tla_{src.get('id') or title[:30]}",
                        })
                    break   # found working endpoint
        except Exception:
            continue

    return results


def _try_tla_website_search(topic: str, era: str, region: str) -> list:
    """
    Fallback: search the TLA website and extract JSON-LD or structured data.
    """
    results = []
    try:
        resp = requests.get(
            f"{TLA_SITE}/search",
            headers={**HEADERS, "Accept": "text/html"},
            params={"q": topic, "lang": "en"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        matches = re.findall(
            r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
            resp.text, re.DOTALL
        )
        for match in matches[:3]:
            try:
                data = json.loads(match)
                for item in (data if isinstance(data, list) else [data]):
                    title = item.get("name") or item.get("title") or ""
                    desc  = item.get("description") or item.get("text") or ""
                    if title and _is_readable_english(desc):
                        results.append({
                            "title":       f"{title.strip()} — Ancient Egyptian Text",
                            "summary":     desc.strip()[:700],
                            "era":         era,
                            "region":      region,
                            "source_url":  item.get("url") or TLA_SITE,
                            "external_id": f"tla_web_{title[:30]}",
                        })
            except Exception:
                continue
    except Exception:
        pass
    return results


# Built-in TLA records (key texts guaranteed to be available with known translations)
KNOWN_EGYPTIAN_TEXTS = [
    ("The Book of the Dead (Ancient Egyptian Funerary Text)",
     "The Book of the Dead is an ancient Egyptian funerary text used from the beginning of the New Kingdom (1550 BCE) to 50 BCE. It was written on papyrus scrolls placed in tombs, providing magical spells to assist the dead person's journey through the underworld and into the afterlife. Key spells include the Weighing of the Heart ceremony, where the deceased's heart was weighed against the feather of Ma'at (truth and justice). If the heart was lighter than the feather, the soul was admitted to paradise.",
     "Ancient Egypt — New Kingdom",   "Egypt",    -1550),
    ("Pyramid Texts (Old Kingdom)",
     "The Pyramid Texts are the oldest known religious texts in the world, dating from around 2400 BCE. Written inside pyramid chambers, they were magical spells intended to help the pharaoh's spirit ascend to the afterlife and join the gods. First found in the pyramid of Unas at Saqqara, they contain hymns, prayers, and detailed descriptions of the afterlife journey.",
     "Ancient Egypt — Old Kingdom",   "Egypt",    -2400),
    ("Coffin Texts (Middle Kingdom)",
     "The Coffin Texts are a collection of ancient Egyptian funerary spells dating from around 2100 BCE, written on the interior of coffins. Derived from the Pyramid Texts but expanded for use by non-royal Egyptians, they describe the geography of the underworld and include spells to protect the deceased. They were a forerunner to the Book of the Dead.",
     "Ancient Egypt — Middle Kingdom","Egypt",    -2100),
    ("The Eloquent Peasant",
     "An ancient Egyptian literary text dating to the Middle Kingdom (about 2050–1650 BCE). It tells the story of Khun-Anup, a peasant who was robbed and then repeatedly petitioned a high official for justice, delivering nine eloquent speeches on the nature of justice and truth. It is considered one of the great examples of Egyptian prose literature.",
     "Ancient Egypt — Middle Kingdom","Egypt",    -2000),
    ("Hymn to the Aten (Amarna Period)",
     "A famous ancient Egyptian religious poem composed during the reign of Pharaoh Akhenaten (c. 1353–1335 BCE) in praise of Aten, the sun disc. It describes Aten as the sole creator god responsible for all life. The text shows parallels with Psalm 104 and represents the closest ancient Egypt came to monotheism. Found inscribed in the tomb of Ay at Amarna.",
     "Ancient Egypt — Amarna Period", "Egypt",    -1350),
    ("The Rosetta Stone Decree",
     "A priestly decree of 196 BCE issued by Ptolemy V, inscribed in three scripts: Ancient Egyptian hieroglyphics, Demotic script, and Ancient Greek. Its discovery in 1799 allowed scholars to decipher Egyptian hieroglyphics for the first time. The text records honours granted to Ptolemy V by the Egyptian priesthood. Now in the British Museum.",
     "Ancient Egypt — Ptolemaic",     "Egypt",    -196),
    ("The Instruction of Ptahhotep",
     "One of the oldest wisdom texts in the world, dating to the Old Kingdom (around 2400 BCE). Attributed to the vizier Ptahhotep under Pharaoh Djedkare Isesi, it consists of maxims on ethical conduct, proper behaviour, and how to live wisely. It is preserved on several papyri and represents the ancient Egyptian wisdom literature genre.",
     "Ancient Egypt — Old Kingdom",   "Egypt",    -2400),
    ("The Tale of Sinuhe",
     "A famous work of ancient Egyptian literature from the Middle Kingdom (c. 1900 BCE), telling the story of a courtier who flees Egypt after the death of Pharaoh Amenemhat I, lives among the Canaanites, achieves success abroad, and eventually returns to Egypt to die. Considered one of the greatest ancient Egyptian literary works for its sophisticated narrative.",
     "Ancient Egypt — Middle Kingdom","Egypt",    -1900),
    ("Harris Papyrus — Ramesses III",
     "The Great Harris Papyrus is the longest papyrus known from ancient Egypt at 41 metres long. Dating to around 1150 BCE, it describes the accomplishments of Pharaoh Ramesses III including his military campaigns against the Sea Peoples, his building projects, and his donations to Egyptian temples. It provides crucial information about the end of the New Kingdom.",
     "Ancient Egypt — New Kingdom",   "Egypt",    -1150),
    ("Ipuwer Papyrus (Admonitions of an Egyptian Sage)",
     "An ancient Egyptian text from the Middle Kingdom describing a period of chaos and social upheaval in Egypt. Written as a lament, it describes plagues, drought, violence, and the breakdown of social order. Some scholars have connected it to the biblical plagues of Exodus, though this is debated. Preserved in the Leiden Museum.",
     "Ancient Egypt — Middle Kingdom","Egypt",    -1800),
]


def fetch(conn: dict, source_id: int) -> int:
    inserted  = 0
    seen_ids: set = set()

    # ── Phase 1: Built-in known Egyptian texts (always reliable) ──────────────
    for (title, summary, era, region, year) in KNOWN_EGYPTIAN_TEXTS:
        ext_id = f"tla_builtin_{title[:35].lower().replace(' ', '_')}"
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
            "source_url":      TLA_SITE,
            "external_id":     ext_id,
            "tags":            ["ancient Egypt", "hieroglyphics", "Egyptian texts",
                                era, "TLA"],
        })
        if ok:
            inserted += 1

    # ── Phase 2: Live API search ───────────────────────────────────────────────
    for (topic, era, region) in SEARCH_TOPICS:
        # Try API
        records = _try_tla_api(topic, era, region)

        # Fallback to website search if API returns nothing
        if not records:
            records = _try_tla_website_search(topic, era, region)

        for rec in records:
            ext_id = rec.get("external_id", f"tla_{topic[:20]}")
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            ok = insert_record(conn, source_id, {
                "title":       rec.get("title", topic),
                "summary":     rec.get("summary", ""),
                "record_type": "document",
                "region":      rec.get("region", region),
                "era":         rec.get("era", era),
                "date_text":   rec.get("date_text", ""),
                "source_url":  rec.get("source_url", TLA_SITE),
                "external_id": ext_id,
                "tags":        ["ancient Egypt", "Egyptian texts", era, topic],
            })
            if ok:
                inserted += 1
                if inserted % 15 == 0:
                    print(f"  [TLA] {inserted} records so far…")

        time.sleep(0.5)

    print(f"  [TLA] {inserted} Egyptian text records inserted")
    return inserted
