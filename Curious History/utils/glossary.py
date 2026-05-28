"""
glossary.py — Extracts bolded terms from HTML content for the glossary section.
Pulls all <strong> tag content and deduplicates them.
Returns a list of unique term strings.
"""

import re


def extract_terms(html: str) -> list:
    """
    Extracts all unique terms wrapped in <strong> tags from HTML content.
    Returns deduplicated list of term strings (max 15 terms).
    """
    matches = re.findall(r"<strong>(.*?)</strong>", html)
    seen = set()
    terms = []
    for m in matches:
        clean = re.sub(r"<[^>]+>", "", m).strip()
        if clean and clean not in seen and len(clean) > 2 and len(clean) < 80:
            seen.add(clean)
            terms.append(clean)
        if len(terms) >= 15:
            break
    return terms
