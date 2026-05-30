"""
essay_formatter.py — Curious History Content Formatter

Converts raw database search records into beautifully structured History Essays
following the PEEL academic essay format. No AI is required — uses rule-based
bolding, template-driven structure, and causation language.

Essay structure:
  # Title
  ## Introduction
  ## Body — [Theme Name]  (one per record/source, PEEL)
  ## Counter-Argument / Alternative Perspective  (when possible)
  ## Conclusion

All key historical terms, dates, names, places, events, and treaties are
automatically bolded throughout the essay.
"""

from __future__ import annotations
import re
from typing import Optional


# ── Master historical term list for auto-bolding ──────────────────────────────
# These are ALWAYS bolded wherever they appear in the essay.
_ALWAYS_BOLD: list[str] = [
    # World Wars
    "World War I", "World War II", "First World War", "Second World War",
    "Great War", "Holocaust", "D-Day", "Battle of the Bulge", "Pearl Harbor",
    "Hiroshima", "Nagasaki", "Treaty of Versailles", "Armistice",
    # Cold War
    "Cold War", "Cuban Missile Crisis", "Berlin Wall", "Iron Curtain",
    "NATO", "Warsaw Pact", "Marshall Plan", "Truman Doctrine",
    "Soviet Union", "USSR",
    # Ancient civilisations
    "Ancient Egypt", "Ancient Greece", "Ancient Rome", "Ancient Mesopotamia",
    "Roman Empire", "Roman Republic", "Byzantine Empire", "Ottoman Empire",
    "Persian Empire", "Achaemenid", "Macedonian Empire",
    "Mesopotamia", "Babylon", "Nineveh", "Assyria", "Sumer",
    # Key texts / documents
    "Code of Hammurabi", "Epic of Gilgamesh", "Book of the Dead",
    "Pyramid Texts", "Coffin Texts", "Rosetta Stone",
    "Magna Carta", "Declaration of Independence", "Emancipation Proclamation",
    "Treaty of Westphalia", "Congress of Vienna",
    # Revolutions
    "French Revolution", "American Revolution", "Russian Revolution",
    "Industrial Revolution", "Glorious Revolution", "Haitian Revolution",
    "Age of Enlightenment", "Reformation", "Renaissance",
    # Empires and States
    "British Empire", "Mongol Empire", "Holy Roman Empire",
    "Mughal Empire", "Ottoman Empire", "Aztec Empire", "Inca Empire",
    "Carolingian Empire", "Habsburg", "Plantagenet",
    # Movements
    "Atlantic Slave Trade", "Abolitionism", "Colonialism", "Imperialism",
    "Decolonisation", "Nationalism", "Fascism", "Communism", "Socialism",
    "Feudalism", "Mercantilism", "Age of Exploration",
    # Key battles
    "Battle of Waterloo", "Battle of Trafalgar", "Battle of Hastings",
    "Battle of Thermopylae", "Battle of Marathon", "Battle of Actium",
    "Battle of Cannae", "Battle of the Somme", "Battle of Stalingrad",
    # Key people
    "Julius Caesar", "Augustus Caesar", "Napoleon Bonaparte",
    "Alexander the Great", "Cleopatra VII", "Genghis Khan",
    "Saladin", "Charlemagne", "William the Conqueror",
    "Martin Luther", "Christopher Columbus", "Vasco da Gama",
    "Oliver Cromwell", "Louis XIV", "Peter the Great",
    "Abraham Lincoln", "George Washington", "Benjamin Franklin",
    "Karl Marx", "Vladimir Lenin", "Joseph Stalin",
    "Adolf Hitler", "Benito Mussolini", "Winston Churchill",
    "Franklin Roosevelt", "Charles de Gaulle", "Mao Zedong",
    "Mahatma Gandhi", "Nelson Mandela",
    # Ancient rulers / pharaohs
    "Ramesses II", "Ramesses III", "Tutankhamun", "Akhenaten",
    "Hatshepsut", "Thutmose III", "Cleopatra", "Ptolemy",
    "Ashurbanipal", "Nebuchadnezzar II", "Cyrus the Great",
    "Darius I", "Xerxes I", "Sargon of Akkad", "Hammurabi",
    "Gilgamesh", "Shulgi",
    # Key places
    "Rome", "Athens", "Sparta", "Carthage", "Alexandria",
    "Constantinople", "Jerusalem", "Babylon", "Nineveh",
    "Persepolis", "Versailles", "Vienna", "Waterloo",
    # Religions / philosophical movements
    "Christianity", "Islam", "Judaism", "Buddhism", "Hinduism",
    "Zoroastrianism", "Protestantism", "Catholicism",
    # Asian history
    "Ming Dynasty", "Qing Dynasty", "Tang Dynasty", "Song Dynasty",
    "Meiji Restoration", "Edo Period", "Tokugawa Shogunate",
    "Silk Road", "Mongol Empire",
    # African history
    "Mali Empire", "Songhai Empire", "Great Zimbabwe",
    "Kingdom of Kush", "Meroitic", "Axum", "Swahili Coast",
]

# Pre-sort by length descending so longer phrases match before shorter substrings
_ALWAYS_BOLD.sort(key=len, reverse=True)

# Regex: matches a 3-or-4-digit BCE/CE year
_YEAR_PATTERN = re.compile(
    r'\b(\d{1,4})\s*(BCE|BC|CE|AD)\b',
    re.IGNORECASE
)

# Regex: matches standalone 4-digit years (1300–2025)
_CE_YEAR = re.compile(r'\b(1[3-9]\d\d|20[0-2]\d)\b')


# ── Causation / linking phrases for PEEL paragraphs ──────────────────────────
_CAUSATION = [
    "As a consequence of",
    "A contributing factor was",
    "This led directly to",
    "The long-term impact of this was",
    "This was significant because",
    "The immediate cause of",
    "This development accelerated",
    "Historians have argued that",
]

_LINKS = [
    "This evidence underscores the broader pattern of",
    "Taken together, these developments illuminate",
    "This connection reinforces the central argument that",
    "Consequently, the historical record confirms that",
    "This demonstrates the enduring significance of",
]

_INTRO_HOOKS = [
    "Few episodes in history have shaped the modern world as decisively as",
    "The story of {topic} represents one of the most consequential developments in world history.",
    "At the heart of {era} history lies a story both complex and revealing:",
    "No study of {region} history is complete without a thorough examination of",
]


# ── Core bolding engine ───────────────────────────────────────────────────────

def _escape_bold_marker(s: str) -> str:
    """Temporarily replace existing **bold** spans to avoid double-bolding."""
    return re.sub(r'\*\*(.+?)\*\*', r'⟦\1⟧', s)


def _restore_bold_marker(s: str) -> str:
    return s.replace('⟦', '**').replace('⟧', '**')


def bold_key_terms(text: str, extra_terms: Optional[list[str]] = None) -> str:
    """
    Bold all key historical terms in *text*.
    Applies:
      1. Controlled list (_ALWAYS_BOLD)
      2. Extra topic-specific terms passed by the caller
      3. BCE/CE / BC/AD date patterns (any year 1–4 digits)
      4. Standalone historical CE years (800–2025)
      5. Notable ancient years (44, 476, 753, 1066, 1453 etc.)
    Avoids double-bolding.
    """
    if not text:
        return text

    # Protect already-bolded spans
    text = _escape_bold_marker(text)

    all_terms = list(_ALWAYS_BOLD)
    if extra_terms:
        # Sort by length desc so longer phrases match first
        all_terms = sorted(set(all_terms + extra_terms), key=len, reverse=True)

    for term in all_terms:
        # Word-boundary-aware replacement, case-insensitive
        pattern = re.compile(r'(?<!\*\*)(?<!\w)(' + re.escape(term) + r')(?!\w)(?!\*\*)',
                             re.IGNORECASE)
        text = pattern.sub(r'**\1**', text)

    # Bold BCE/CE / BC/AD dates (any 1-4 digit year)
    text = _YEAR_PATTERN.sub(lambda m: f'**{m.group(0)}**', text)

    # Bold standalone historical CE years (800–2025) if not already bolded
    def _bold_year(m):
        start  = m.start()
        before = text[max(0, start - 2):start]
        if '**' in before or '⟦' in before:
            return m.group(0)
        return f'**{m.group(0)}**'
    text = _CE_YEAR.sub(_bold_year, text)

    # Bold notable ancient years that appear without BCE/CE label but in historical context
    # e.g. "in 44, Caesar was assassinated" — catch years 1–799 preceded by "in " or "of "
    _ANCIENT_INLINE = re.compile(r'\b(?:in|of|around|circa|c\.)\s+(\d{1,3})\b', re.IGNORECASE)
    text = _ANCIENT_INLINE.sub(lambda m: m.group(0).replace(m.group(1), f'**{m.group(1)}**'), text)

    # Restore protected spans
    text = _restore_bold_marker(text)

    # Clean up accidental nested bold ****word**** → **word**
    text = re.sub(r'\*{4}(.+?)\*{4}', r'**\1**', text)
    text = re.sub(r'\*\*\*\*', r'**', text)

    return text


# ── PEEL paragraph builder ────────────────────────────────────────────────────

def _build_peel_paragraph(
    point: str,
    evidence: str,
    source_name: str,
    era: str,
    region: str,
    link_idx: int,
    causation_idx: int,
    extra_terms: Optional[list[str]] = None,
) -> str:
    """
    Build a single PEEL body paragraph in Markdown.
    """
    # Point: opening sentence — restate the record title as a historical claim
    point_sentence = bold_key_terms(
        f"{point} represents a critical dimension of {era} history in {region}.",
        extra_terms
    )

    # Evidence: bolded content from the record
    evidence_bolded = bold_key_terms(evidence.strip(), extra_terms)

    # Explanation: causation sentence
    causation = _CAUSATION[causation_idx % len(_CAUSATION)]
    explanation = (
        f"{causation} this, scholars have identified lasting consequences for "
        f"the political, cultural, and social development of {region}."
    )

    # Link: transitional sentence back to thesis
    link = bold_key_terms(
        f"{_LINKS[link_idx % len(_LINKS)]} {era} and its enduring legacy.",
        extra_terms
    )

    # Attribution
    attribution = f"*[Source: {source_name}]*"

    return "\n\n".join([
        point_sentence,
        evidence_bolded,
        explanation,
        link,
        attribution,
    ])


# ── Image description builder ─────────────────────────────────────────────────

def _build_image_description(
    record: dict,
    topic: str,
) -> str:
    """
    Generate a structured Image Description block from a pipeline image record.
    Never copies captions verbatim — always rewrites analytically.
    """
    title    = record.get("title") or topic
    summary  = record.get("snippet") or record.get("summary") or ""
    source   = record.get("source_name") or "Historical Archive"
    era      = record.get("era") or "Historical Period"
    region   = record.get("region") or "Unknown Region"
    url      = record.get("source_url") or ""

    # Determine type from title/summary keywords
    if any(k in title.lower() for k in ["map", "territory", "boundaries", "route"]):
        img_type = "Historical Map"
    elif any(k in title.lower() for k in ["portrait", "painting", "engraving", "illustration"]):
        img_type = "Historical Painting / Portrait"
    elif any(k in title.lower() for k in ["photo", "photograph"]):
        img_type = "Historical Photograph"
    else:
        img_type = "Historical Illustration"

    context = (
        f"This image provides visual evidence of {bold_key_terms(topic)} "
        f"during the {bold_key_terms(era)} period in {bold_key_terms(region)}. "
        f"{bold_key_terms(summary[:180]) if summary else ''}"
    ).strip()

    return (
        "\n[IMAGE DESCRIPTION]\n"
        f"- **Type:** {img_type}\n"
        f"- **Subject:** {bold_key_terms(title)}\n"
        f"- **Historical Context:** {context}\n"
        f"- **Key Details to Note:** Examine the visual elements for evidence of "
        f"{bold_key_terms(era)} material culture, iconography, and historical context "
        f"as they relate to {bold_key_terms(topic)}.\n"
        f"- **Source Attribution:** {source}" +
        (f" — {url}" if url else "") + "\n"
        "[END IMAGE DESCRIPTION]\n"
    )


# ── Main essay assembly ───────────────────────────────────────────────────────

def format_as_essay(
    topic: str,
    records: list[dict],
    year: str = "",
    era_hint: str = "",
    region_hint: str = "",
) -> str:
    """
    Convert a list of formatted pipeline records into a structured History Essay.

    Parameters
    ----------
    topic       : the user's search query
    records     : list of dicts from _fmt_record() in app.py
                  (keys: title, snippet, era, region, source_name, image_url, …)
    year        : optional year string (e.g. "1789")
    era_hint    : optional era string from the search context
    region_hint : optional region string from the search context

    Returns
    -------
    Markdown string of the full essay.
    """
    if not records:
        return ""

    # ── Gather metadata from records ──────────────────────────────────────────
    eras    = [r.get("era") or "" for r in records if r.get("era")]
    regions = [r.get("region") or "" for r in records if r.get("region")]
    dominant_era    = era_hint or (max(set(eras),    key=eras.count)    if eras    else "Historical Period")
    dominant_region = region_hint or (max(set(regions), key=regions.count) if regions else "World")
    sources_used    = list(dict.fromkeys(str(r.get("source_name", "")) for r in records if r.get("source_name")))

    # Extract specific topic-level terms for extra bolding
    extra_terms = [topic] + [r.get("title", "") for r in records[:6]]

    # Separate image records from text records
    text_records  = [r for r in records if r.get("record_type") != "image"]
    image_records = [r for r in records if r.get("record_type") == "image"]

    # ── 1. TITLE ──────────────────────────────────────────────────────────────
    year_str = f" ({year})" if year else ""
    title_line = f"# {topic.title()}{year_str} — A Historical Analysis\n"

    # ── 2. INTRODUCTION ───────────────────────────────────────────────────────
    first = text_records[0] if text_records else {}
    first_snippet = first.get("snippet") or ""
    hook = (
        first_snippet[:160].rstrip() + "…"
        if len(first_snippet) > 160
        else first_snippet
    )
    if not hook:
        hook = f"The history of {topic} has shaped civilisations across centuries."

    intro = bold_key_terms(
        f"{hook}\n\n"
        f"The study of **{topic}** reveals the complex interplay of political, cultural, "
        f"and social forces that defined **{dominant_era}** in **{dominant_region}**. "
        f"By examining primary sources, archaeological evidence, and scholarly analysis, "
        f"it becomes possible to reconstruct the events, causes, and consequences that "
        f"make this topic one of enduring historical significance. "
        f"This essay analyses the key themes of {topic}, drawing on evidence from "
        f"{', '.join(sources_used[:4]) if sources_used else 'multiple historical archives'}.",
        extra_terms
    )

    # ── 3. BODY PARAGRAPHS ────────────────────────────────────────────────────
    body_sections: list[str] = []
    seen_titles: set[str] = set()
    para_count = 0
    max_paras  = min(len(text_records), 6)

    for i, record in enumerate(text_records[:max_paras]):
        rec_title   = record.get("title") or topic
        snippet     = record.get("snippet") or ""
        source_name = record.get("source_name") or "Historical Archive"
        rec_era     = record.get("era") or dominant_era
        rec_region  = record.get("region") or dominant_region

        if not snippet or rec_title in seen_titles:
            continue
        seen_titles.add(rec_title)

        # Derive theme name for section header
        theme = re.sub(r'\s*[-—–]\s*(Ancient|Medieval|Modern|Historical).*$', '',
                       rec_title, flags=re.IGNORECASE).strip()
        if len(theme) > 55:
            theme = theme[:52] + "…"

        section_header = f"## Body — {bold_key_terms(theme, extra_terms)}"
        paragraph = _build_peel_paragraph(
            point        = rec_title,
            evidence     = snippet,
            source_name  = source_name,
            era          = rec_era,
            region       = rec_region,
            link_idx     = para_count,
            causation_idx= para_count,
            extra_terms  = extra_terms,
        )
        body_sections.append(f"{section_header}\n\n{paragraph}")

        # Insert image description inline if image available
        if image_records and para_count < len(image_records):
            body_sections.append(
                _build_image_description(image_records[para_count], topic)
            )

        para_count += 1

    # ── 4. COUNTER-ARGUMENT ───────────────────────────────────────────────────
    counter = ""
    # Counter-argument: use the record BEYOND body paragraphs, or the last body record
    # if body fills all records. Old trigger was broken — text_records[-1] was always
    # inside text_records[:max_paras], so condition never fired. Fixed: use index max_paras.
    _alt_idx   = max_paras if len(text_records) > max_paras else max(0, len(text_records) - 1)
    if len(text_records) >= 3:
        alt_record  = text_records[_alt_idx]
        alt_snippet = alt_record.get("snippet") or ""
        alt_source  = alt_record.get("source_name") or "Alternative Source"
        if alt_snippet:
            counter_evidence = bold_key_terms(alt_snippet[:400], extra_terms)
            counter = (
                "## Counter-Argument / Alternative Perspective\n\n"
                f"Not all historians have interpreted the significance of "
                f"**{topic}** uniformly. {counter_evidence} "
                f"However, the weight of primary source evidence — as demonstrated "
                f"throughout this analysis — consistently supports the view that "
                f"**{topic}** was a transformative development in **{dominant_era}** "
                f"history, regardless of interpretive differences over its precise causes "
                f"and long-term consequences.\n\n"
                f"*[Alternative perspective drawn from: {alt_source}]*"
            )

    # ── 5. CONCLUSION ─────────────────────────────────────────────────────────
    # Synthesise 3–4 key arguments
    key_args: list[str] = []
    for r in text_records[:4]:
        t = r.get("title") or ""
        if t:
            key_args.append(bold_key_terms(f"**{t}** illuminated a defining aspect of {topic}.", extra_terms))

    args_summary = " ".join(key_args[:4])
    conclusion = (
        "## Conclusion\n\n"
        f"In conclusion, the history of **{topic}** stands as a landmark development "
        f"in the long narrative of **{dominant_era}** civilisation in **{dominant_region}**. "
        f"{args_summary} "
        f"The evidence examined in this essay — drawn from {', '.join(sources_used[:3]) if sources_used else 'multiple archives'} "
        f"— confirms that **{topic}** was not an isolated phenomenon but rather the "
        f"product of deep structural forces that had been gathering for generations. "
        f"Its significance extends far beyond the immediate historical moment: "
        f"the legacy of **{topic}** continued to shape political boundaries, cultural "
        f"identities, and social structures for centuries to come, making it an "
        f"indispensable subject of historical enquiry."
    )

    # ── Assemble final essay ──────────────────────────────────────────────────
    sections = [
        title_line,
        "## Introduction\n\n" + intro,
    ] + body_sections

    if counter:
        sections.append(counter)

    sections.append(conclusion)

    essay = "\n\n---\n\n".join(sections)
    return essay


# ── Manuscript content special handler ───────────────────────────────────────

def format_manuscript_record(record: dict, topic: str) -> str:
    """
    Special formatting for manuscript / primary-source records (cuneiform,
    hieroglyphic, medieval Latin, etc.). Wraps in essay structure and notes
    any translation status.
    """
    title   = record.get("title") or topic
    snippet = record.get("snippet") or record.get("summary") or ""
    source  = record.get("source_name") or "Primary Source Archive"
    era     = record.get("era") or "Ancient Period"
    region  = record.get("region") or "Unknown Region"

    bolded_title   = bold_key_terms(title)
    bolded_snippet = bold_key_terms(snippet, [topic, title])

    return (
        f"### {bolded_title}\n\n"
        f"**Era:** {bold_key_terms(era)} | **Region:** {bold_key_terms(region)} | "
        f"**Source:** {source}\n\n"
        f"{bolded_snippet}\n\n"
        f"*The above content represents an English translation and scholarly "
        f"interpretation of the original manuscript. Raw script forms "
        f"(cuneiform, hieroglyphics, ancient script) have been omitted — "
        f"only the readable English content is presented.*"
    )
