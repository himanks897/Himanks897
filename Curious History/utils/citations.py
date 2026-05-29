"""
citations.py — Auto-generates citation text for copied content and academic use.
"""

from datetime import date


def build_citation(topic: str, year: int, country: str, sources: list) -> str:
    """Plain-text citation appended to copied content."""
    today = date.today().strftime("%B %d, %Y")
    source_list = ", ".join(sources) if sources else "Wikipedia, World History Encyclopedia"
    return (
        f"\n\n— Curious History | {topic} ({year}, {country}) | "
        f"Sources: {source_list} | Accessed {today} | curioushistory.com"
    )


def build_apa_citation(topic: str, year: int, country: str, sources: list) -> str:
    """
    Generates an APA 7th edition style citation for the article.
    Format: Author. (Year). Title. Source. URL
    """
    today = date.today()
    source_str = sources[0] if sources else "Curious History"
    return (
        f"Curious History. ({today.year}). *{topic}* ({year} {country}). "
        f"{source_str}. Retrieved {today.strftime('%B %d, %Y')}, "
        f"from https://curioushistory.vercel.app"
    )


def build_mla_citation(topic: str, year: int, country: str, sources: list) -> str:
    """
    Generates an MLA 9th edition style citation for the article.
    Format: "Title." Site, Publisher, Date, URL.
    """
    today = date.today()
    source_str = sources[0] if sources else "Curious History"
    return (
        f'"{topic} ({year}, {country})." *Curious History*, {source_str}, '
        f"{today.strftime('%d %b. %Y')}, curioushistory.vercel.app."
    )
