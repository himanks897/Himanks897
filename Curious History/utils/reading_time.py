"""
reading_time.py — Calculates estimated reading time from word count.
Returns a formatted string like "~6 min read".
"""

import re


def estimate(text: str, wpm: int = 200) -> str:
    """
    Estimates reading time for the given text.
    Strips HTML tags before counting words.
    Returns formatted string like '~4 min read'.
    """
    clean = re.sub(r"<[^>]+>", " ", text)
    words = len(clean.split())
    minutes = max(1, round(words / wpm))
    return f"~{minutes} min read"
