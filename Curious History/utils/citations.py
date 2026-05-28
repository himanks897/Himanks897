"""
citations.py — Auto-generates citation text for copied content.
Appended to clipboard content via JavaScript on the frontend.
"""

from datetime import date


def build_citation(topic: str, year: int, country: str, sources: list) -> str:
    """
    Builds a citation string for the given event.
    Returns plain text citation appended to copied content.
    """
    today = date.today().strftime("%B %d, %Y")
    source_list = ", ".join(sources) if sources else "Wikipedia, World History Encyclopedia"
    return (
        f"\n\n— Curious History | {topic} ({year}, {country}) | "
        f"Sources: {source_list} | Accessed {today} | curioushistory.com"
    )
