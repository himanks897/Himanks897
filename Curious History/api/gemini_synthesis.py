"""
gemini_synthesis.py — Google Gemini AI integration for content synthesis.
Handles: full article generation, summaries, simplification, quizzes,
         related topics, key people/places/causes, timelines, and more.
All prompts enforce structured HTML output with bold/italic formatting.
"""

import os
import re
from google import genai
from google.genai import types
from api import cache
from config import Config

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client

MODEL = "gemini-2.0-flash"


def _call_gemini(prompt: str, cache_key: str = None, ttl: int = 3600) -> str:
    """
    Calls Gemini API with the given prompt. Returns text response.
    Caches the result if cache_key is provided.
    """
    if cache_key:
        cached = cache.get(cache_key)
        if cached:
            return cached
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        text = response.text if response.text else ""
        if cache_key and text:
            cache.set(cache_key, text, ttl=ttl)
        return text
    except Exception as e:
        return f"<p><em>Content generation temporarily unavailable: {str(e)[:100]}. Please try again.</em></p>"


def synthesise_article(topic: str, year: int, country: str, era: str, raw_content: str) -> dict:
    """
    Generates a fully formatted HTML article from raw Wikipedia/source content.
    Returns dict with {html, importance_level, key_terms, sources_used}.
    """
    cache_key = f"article:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""You are a senior academic historian writing a peer-reviewed essay for advanced students and researchers.

Topic: {topic}
Year: {year} {'BCE' if era == 'bce' else 'CE'}
Country/Region: {country}
Era: {era.upper()}

Raw source material:
{raw_content[:4000]}

Write a comprehensive academic essay in HTML following this EXACT structure:

1. INTRODUCTION (10-15% of total length):
   - Hook: 1-2 sentences painting the broad historical landscape
   - Historiography: 2-3 sentences on how historians have debated or framed this topic
   - Pivot: 1 sentence narrowing to the specific event/period
   - Thesis Statement: 1 complex sentence stating the core argument, primary line of reasoning, and roadmap of evidence
   Wrap the entire introduction in <div class="essay-section essay-intro"><div class="essay-section-label">Introduction</div>...</div>
   Use <p class="section-lead"> for the hook. Use <p> for historiography. Use <p><em> for the pivot. Use <p class="section-lead"><strong><em> for the thesis.

2. BODY PARAGRAPHS (70-80% of total length) — for each major section:
   - Sub-Header: use <h2> (bolded), e.g. <h2>Origins and Causes</h2>
   - Topic Sentence: <p class="section-lead"> — directly supports the thesis
   - Historical Contextualization: <p> — 2 sentences covering who/what/where/when
   - Primary Evidence: use <ul><li> for direct quotes, data, or firsthand sources
   - Historical Analysis "So What?": <p> — 3-4 sentences explaining why the evidence matters
   - Counterargument/Nuance: <p><em> — 1-2 sentences on gaps or alternative interpretations
   Wrap all body sections in <div class="essay-section essay-body">...</div>

3. CONCLUSION (10-15% of total length):
   - Restatement of Thesis: <p class="section-lead"><strong><em> — restated in different words, confident tone
   - Synthesis of Main Points: <p> — 2-3 sentences connecting the major themes
   - Broader Historical Significance: <p><em> — 2 sentences on long-term impact and why it matters to modern historians
   Wrap in <div class="essay-section essay-conclusion"><div class="essay-section-label">Conclusion &amp; Historical Significance</div>...</div>

4. BIBLIOGRAPHY (separate section at end):
   - Primary Sources subsection: firsthand documents, diaries, treaties, speeches — alphabetized by author/title
   - Secondary Sources subsection: peer-reviewed books, articles, essays — alphabetized by author's last name
   Wrap in <div class="essay-bibliography"><h2>Bibliography</h2><h3>Primary Sources</h3><ul>...</ul><h3>Secondary Sources</h3><ul>...</ul></div>
   Use plausible/real citations where known; clearly label invented ones with [estimated].

Additional rules:
- Wrap ALL key historical terms, names, dates, and places in <strong> tags
- Use <em> for quotes, foreign words, and nuanced claims
- Minimum 800 words of actual content
- Do NOT include Wikipedia links or raw source URLs in the essay text
- At the end include: <div class="key-terms-data">term1|term2|term3</div>
- At the end include: <div class="importance-level">Global</div> (one of: Local, Regional, National, Continental, Global)

Return ONLY the HTML content — no markdown, no ```html blocks, no text outside the HTML."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)

    # Extract importance level
    importance_match = re.search(r'<div class="importance-level">(.*?)</div>', result)
    importance = importance_match.group(1) if importance_match else "National"

    # Extract key terms
    terms_match = re.search(r'<div class="key-terms-data">(.*?)</div>', result, re.DOTALL)
    key_terms = []
    if terms_match:
        key_terms = [t.strip() for t in terms_match.group(1).split("|") if t.strip()]

    # Clean up the extraction divs from display content
    clean_html = re.sub(r'<div class="key-terms-data">.*?</div>', '', result, flags=re.DOTALL)
    clean_html = re.sub(r'<div class="importance-level">.*?</div>', '', clean_html, flags=re.DOTALL)

    response_data = {
        "html": clean_html,
        "importance_level": importance,
        "key_terms": key_terms,
        "sources_used": ["Wikipedia", "Wikidata", "World History Encyclopedia"],
    }
    cache.set(cache_key, response_data, ttl=86400)
    return response_data


def generate_detailed_content(topic: str, year: int, country: str, era: str, raw_content: str) -> str:
    """
    Generates an exhaustive, detailed version of the topic article.
    More comprehensive than the standard article — covers every sub-event, cause, consequence.
    Returns HTML string.
    """
    cache_key = f"detailed:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""You are a senior academic historian writing an exhaustive peer-reviewed reference essay.

Topic: {topic}
Year: {year} {'BCE' if era == 'bce' else 'CE'}
Country/Region: {country}

Raw source material:
{raw_content[:5000]}

Write an EXTREMELY detailed academic essay in HTML following this EXACT structure:

1. INTRODUCTION (10-15%):
   - Hook (1-2 sentences, broad historical landscape)
   - Historiography/Debate (2-3 sentences on how historians view this topic)
   - Pivot (1 sentence narrowing to the specific event)
   - Thesis Statement (1 complex sentence with core argument, line of reasoning, roadmap of evidence)
   Wrap in <div class="essay-section essay-intro"><div class="essay-section-label">Introduction</div>...</div>

2. BODY PARAGRAPHS (70-80%) — cover every sub-event, cause, consequence:
   For each major section use <h2> sub-headers, then:
   - Topic Sentence (<p class="section-lead">)
   - Historical Contextualization (<p> — who/what/where/when)
   - Primary Evidence (<ul><li> — direct quotes, data, firsthand sources)
   - Historical Analysis "So What?" (<p> — 3-4 sentences explaining significance)
   - Counterargument/Nuance (<p><em> — gaps or alternative interpretations)
   - Transition Sentence (final sentence bridging to next section)
   Cover: Causes, Events (chronological), Key People, Battles/Turning Points (if applicable),
          International Reactions, Short-term Consequences, Long-term Legacy
   Wrap all body in <div class="essay-section essay-body">...</div>

3. CONCLUSION (10-15%):
   - Restatement of Thesis (<p class="section-lead"><strong><em>)
   - Synthesis of Main Points (<p> — 2-3 sentences connecting major themes)
   - Broader Historical Significance (<p><em> — long-term impact, relevance to modern historians)
   Wrap in <div class="essay-section essay-conclusion"><div class="essay-section-label">Conclusion &amp; Historical Significance</div>...</div>

4. BIBLIOGRAPHY:
   - Primary Sources (alphabetized by author/title)
   - Secondary Sources (peer-reviewed; alphabetized by author's last name)
   Wrap in <div class="essay-bibliography"><h2>Bibliography</h2><h3>Primary Sources</h3><ul>...</ul><h3>Secondary Sources</h3><ul>...</ul></div>

Additional rules:
- Wrap ALL key terms in <strong>, use <em> for quotes/emphasis
- Minimum 1000-1200 words of actual content
- No source URLs or raw Wikipedia links in the essay text
- Write in rigorous academic but accessible prose

Return ONLY HTML content."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    return result


def generate_summary(topic: str, year: int, country: str, era: str, word_count: int, raw_content: str) -> str:
    """
    Generates a summary of exactly the specified word count (±10 words).
    Returns HTML-formatted summary string.
    """
    cache_key = f"summary:{topic}:{year}:{country}:{word_count}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""You are a history educator writing a precise summary.

Topic: {topic}
Year: {year} {'BCE' if era == 'bce' else 'CE'}
Country/Region: {country}

Source material:
{raw_content[:3000]}

Write an HTML summary of EXACTLY {word_count} words (±10 words maximum). This is CRITICAL — count your words carefully.

Rules:
1. The summary MUST be {word_count} words — not {word_count - 50}, not {word_count + 50}. Exactly {word_count} ±10.
2. Use a MIX of short paragraphs and bullet points
3. Cover the most important facts within the word limit
4. Wrap key terms in <strong>, use <em> for emphasis
5. Structure: Brief background → Main events → Key outcome
6. Do NOT include source URLs
7. After the HTML, on a new line write: WORD_COUNT: [actual count]

Return ONLY the HTML summary followed by the word count line."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    cache.set(cache_key, result, ttl=86400)
    return result


def simplify_paragraph(paragraph: str, topic: str) -> str:
    """
    Rewrites a paragraph in simple English for a Class 8 student.
    Returns plain HTML paragraph string.
    """
    prompt = f"""Rewrite this paragraph in simple English for a Class 8 student studying {topic}.
Keep ALL facts. Maximum 4 sentences. Use <strong> for key terms.

Original: {paragraph}

Return ONLY the simplified HTML paragraph."""
    return _call_gemini(prompt, ttl=3600)


def generate_key_places(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Lists all geographically important locations for the event.
    Returns HTML with location cards.
    """
    cache_key = f"places:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""For the historical event: {topic} ({year}, {country})

Source: {raw_content[:2000]}

List ALL geographically important locations related to this event.
For each location provide an HTML card like this:
<div class="place-card">
  <h4><strong>[Location Name]</strong></h4>
  <p>[One sentence explaining its significance to this event]</p>
</div>

Include at least 4-6 locations. Return ONLY the HTML cards."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    cache.set(cache_key, result, ttl=86400)
    return result


def generate_key_causes(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Lists the major causes of a war, revolution, famine, or crisis.
    Returns numbered HTML cause cards.
    """
    cache_key = f"causes:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""For the historical event: {topic} ({year}, {country})

Source: {raw_content[:2000]}

List each major cause with 2-3 sentences of explanation.
Format as HTML:
<div class="cause-card">
  <div class="cause-number">1</div>
  <h4><strong>[Cause Title]</strong></h4>
  <p>[2-3 sentences explaining this cause]</p>
</div>

Number them sequentially. Include at least 4-5 causes. Return ONLY the HTML."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    cache.set(cache_key, result, ttl=86400)
    return result


def generate_key_people(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Lists every significant person involved in the historical event.
    Returns HTML person cards.
    """
    cache_key = f"people:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""For the historical event: {topic} ({year}, {country})

Source: {raw_content[:2000]}

List every significant person involved. For each person:
<div class="person-card">
  <h4><strong>[Full Name]</strong></h4>
  <p class="person-role"><em>[Role/Title]</em> · [Nationality]</p>
  <p>[Their significance to this event in 2-3 sentences]</p>
</div>

Include at least 4-6 people. Return ONLY the HTML."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    cache.set(cache_key, result, ttl=86400)
    return result


def generate_timeline(topic: str, year: int, country: str, raw_content: str) -> str:
    """
    Generates a chronological mini-timeline of the event.
    Returns HTML vertical timeline component.
    """
    cache_key = f"timeline:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""For the historical event: {topic} ({year}, {country})

Source: {raw_content[:2000]}

Create a chronological timeline. For each entry:
<div class="timeline-entry">
  <div class="timeline-date"><strong>[Date or Period]</strong></div>
  <div class="timeline-content">
    <p>[1-2 sentences describing what happened]</p>
  </div>
</div>

Include 6-8 timeline entries in strict chronological order. Return ONLY the HTML."""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    cache.set(cache_key, result, ttl=86400)
    return result


def generate_related_topics(topic: str, year: int, country: str) -> list:
    """
    Generates 4 related topics the user might explore next.
    Returns a list of topic strings.
    """
    cache_key = f"related:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""For a student who just read about: {topic} ({year}, {country})

Suggest 4 related historical topics they might explore next.
Return ONLY a JSON array of strings, e.g.: ["Topic 1", "Topic 2", "Topic 3", "Topic 4"]
Make them specific and historically relevant. No explanations."""

    result = _call_gemini(prompt, ttl=86400)
    try:
        import json
        # Extract JSON array from response
        match = re.search(r'\[.*?\]', result, re.DOTALL)
        if match:
            topics = json.loads(match.group())
            cache.set(cache_key, topics, ttl=86400)
            return topics[:4]
    except Exception:
        pass
    return [f"History of {country}", f"{year} World Events", f"Related events in {topic}", "Global History"]


def generate_mcq_quiz(topic: str, year: int, country: str, content: str) -> dict:
    """
    Generates 5 multiple-choice questions about the topic (mix of text and image-based).
    Returns dict with {questions: [{question, options, correct, image_hint}]}.
    """
    cache_key = f"mcq:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""You are a history quiz creator for students (Class 6-12).

Topic: {topic} ({year}, {country})
Content: {content[:3000]}

Create EXACTLY 5 multiple-choice questions. Mix text-based and description-based questions.
Each question must be uniformly structured.

Return a JSON object with this EXACT structure:
{{
  "questions": [
    {{
      "id": 1,
      "question": "<strong>[Question text with bold key terms]</strong>",
      "options": {{
        "A": "[Option A]",
        "B": "[Option B]",
        "C": "[Option C]",
        "D": "[Option D]"
      }},
      "correct": "A",
      "explanation": "[Brief explanation of why this is correct]",
      "type": "text"
    }}
  ]
}}

Rules:
- Questions must be about factual content from the topic
- Distribute correct answers evenly (don't always make it A)
- Options must be plausible — no obviously wrong answers
- Keep questions clear and unambiguous
- Use <strong> and <em> tags in question text for formatting
- Return ONLY valid JSON — no extra text"""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    try:
        import json
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            cache.set(cache_key, data, ttl=86400)
            return data
    except Exception:
        pass
    return {"questions": []}


def generate_fill_blanks_quiz(topic: str, year: int, country: str, content: str) -> dict:
    """
    Generates 5 fill-in-the-blank questions about the topic.
    Returns dict with {questions: [{sentence, blank_word, hint}]}.
    """
    cache_key = f"fitb:{topic}:{year}:{country}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    prompt = f"""You are a history quiz creator for students (Class 6-12).

Topic: {topic} ({year}, {country})
Content: {content[:3000]}

Create EXACTLY 5 fill-in-the-blank questions with UNIFORM structure.

Return a JSON object with this EXACT structure:
{{
  "questions": [
    {{
      "id": 1,
      "sentence": "The __________ of [year] was caused by <strong>[key term]</strong>.",
      "blank_word": "exact word that fills the blank",
      "hint": "A brief hint to help the student",
      "explanation": "Full sentence with the answer filled in"
    }}
  ]
}}

Rules:
- The blank should always be represented by exactly __________ (10 underscores)
- Blanks should test important facts: dates, names, places, terms
- Sentences should be historically accurate
- Use <strong> and <em> formatting in sentences
- Keep sentences readable and natural
- Return ONLY valid JSON — no extra text"""

    result = _call_gemini(prompt, cache_key=cache_key, ttl=86400)
    try:
        import json
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            cache.set(cache_key, data, ttl=86400)
            return data
    except Exception:
        pass
    return {"questions": []}


def define_terms(terms: list, context: str) -> dict:
    """
    Defines a list of historical terms in one sentence each, in context.
    Returns dict of {term: definition}.
    """
    if not terms:
        return {}
    cache_key = f"terms:{':'.join(terms[:5])}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    terms_list = "\n".join([f"- {t}" for t in terms[:10]])
    prompt = f"""Define each of these historical terms in ONE sentence each, in the context of: {context}

Terms:
{terms_list}

Return a JSON object: {{"term": "one-sentence definition", ...}}
Return ONLY valid JSON."""

    result = _call_gemini(prompt, ttl=86400)
    try:
        import json
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            cache.set(cache_key, data, ttl=86400)
            return data
    except Exception:
        pass
    return {}
