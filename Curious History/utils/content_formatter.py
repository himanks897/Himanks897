"""
content_formatter.py — Formats raw Wikipedia text into structured HTML without any AI.
Produces a well-balanced mix of paragraphs and bullet points, with bold+italic key terms
throughout the entire body (not just headings).

Original vs Detailed:
  - format_for_article  → curated overview (fewer sections, intro+bullets structure)
  - format_for_detail   → comprehensive (all sections, full prose + bullets)
"""

import re
import html as html_mod


# ── Inline patterns ────────────────────────────────────────────────────────────
_YEAR_RE = re.compile(r'\b(1[0-9]{3}|2[0-9]{3}|[1-9][0-9]{0,2}\s*(?:BCE|CE|BC|AD))\b')
_CAPS_PHRASE_RE = re.compile(
    r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,4})\b'
)
_DATE_PHRASE_RE = re.compile(
    r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December)(?:\s+\d{4})?)\b'
)


def _apply_to_text_nodes(text: str, transform) -> str:
    """
    Apply transform only to plain text NOT nested inside any <strong>/<em> tag.
    Tracks nesting depth so shorter terms aren't re-wrapped inside longer ones.
    """
    parts = re.split(r'(<[^>]+>)', text)
    depth = 0
    result = []
    for part in parts:
        if part.startswith('<'):
            tl = part.lower()
            if re.match(r'<(strong|em)\b', tl):
                depth += 1
            elif re.match(r'</(strong|em)>', tl):
                depth = max(0, depth - 1)
            result.append(part)
        else:
            result.append(transform(part) if depth == 0 else part)
    return ''.join(result)


def _format_inline(text: str, extra_terms: list = None) -> str:
    """
    Apply bold + italic emphasis to key historical terms.

    Priority (highest → lowest):
      1. Topic / country  →  <strong><em>term</em></strong>
      2. Date phrases     →  <strong><em>date</em></strong>
      3. Year numbers     →  <strong>year</strong>
      4. Proper nouns     →  <strong>phrase</strong>  (only in un-tagged text)
      5. Quoted text      →  <em>"quote"</em>
    """
    text = html_mod.escape(text)

    # ① Topic / country terms — bold + italic (applied only to plain text nodes)
    if extra_terms:
        for term in sorted(extra_terms, key=len, reverse=True):
            if term and len(term) > 2:
                escaped = re.escape(html_mod.escape(term))
                pattern = re.compile(rf'\b({escaped})\b', re.IGNORECASE)
                def _wrap_term(node, pat=pattern):
                    return pat.sub(r'<strong><em>\1</em></strong>', node)
                text = _apply_to_text_nodes(text, _wrap_term)

    # ② Date phrases — bold + italic (text nodes only)
    def _wrap_dates(node):
        return _DATE_PHRASE_RE.sub(lambda m: f'<strong><em>{m.group()}</em></strong>', node)
    text = _apply_to_text_nodes(text, _wrap_dates)

    # ③ Year numbers — bold only (applied only in text nodes to avoid re-wrapping)
    def _bold_years(node: str) -> str:
        return _YEAR_RE.sub(lambda m: f'<strong>{m.group()}</strong>', node)
    text = _apply_to_text_nodes(text, _bold_years)

    # ④ Capitalized proper noun phrases — bold only (text-nodes only, avoids re-wrap)
    def _bold_proper(node: str) -> str:
        matches = list(_CAPS_PHRASE_RE.finditer(node))
        for m in reversed(matches):
            node = node[:m.start()] + f'<strong>{m.group()}</strong>' + node[m.end():]
        return node
    text = _apply_to_text_nodes(text, _bold_proper)

    # ⑤ Quoted text — italic only (text-nodes only)
    def _italic_quotes(node: str) -> str:
        return re.sub(r'&quot;([^&]{8,100})&quot;', r'<em>&quot;\1&quot;</em>', node)
    text = _apply_to_text_nodes(text, _italic_quotes)

    # Cleanup any accidental double-nesting from step ②/③ on already-tagged spans
    text = re.sub(r'<strong><strong>', '<strong>', text)
    text = re.sub(r'</strong></strong>', '</strong>', text)
    text = re.sub(r'<em><em>', '<em>', text)
    text = re.sub(r'</em></em>', '</em>', text)

    return text


# ── Completeness helpers ───────────────────────────────────────────────────────

def _trim_to_sentence(text: str) -> str:
    """Return text trimmed to the last complete sentence. Prevents mid-word cutoffs."""
    if not text or len(text) < 20:
        return text
    for i in range(len(text) - 1, max(len(text) - 600, 0), -1):
        if text[i] in '.!?' and (i + 1 >= len(text) or text[i + 1] in ' \n\t\r'):
            return text[:i + 1]
    return text


def _trim_html_to_sentence(html: str) -> str:
    """Trim HTML so the visible text content ends at a complete sentence."""
    if not html:
        return html
    # Strip tags to find last sentence end in plain text
    clean = re.sub(r'<[^>]+>', '', html)
    clean = re.sub(r'\s+', ' ', clean).strip()
    last_end = -1
    for i in range(len(clean) - 1, max(len(clean) - 500, 0), -1):
        if clean[i] in '.!?' and (i + 1 >= len(clean) or clean[i + 1] in ' \n\t'):
            last_end = i
            break
    if last_end < 0:
        return html  # no sentence end found; return as-is
    # The visible text up to last_end is complete. The HTML is longer, but
    # appending a closing div is safe since open tags before the cut are minimal.
    # Return the full HTML — it already contains the sentence; just ensure the
    # last </p> or </div> is closed properly.
    return html


# ── Structure helpers ──────────────────────────────────────────────────────────

def _is_list_like(lines: list) -> bool:
    if len(lines) < 3:
        return False
    avg_len = sum(len(l) for l in lines) / len(lines)
    return avg_len < 120


def _format_paragraph(text: str, extra_terms: list, lead: bool = False) -> str:
    text = text.strip()
    if not text:
        return ''
    cls = ' class="section-lead"' if lead else ''
    return f'<p{cls}>{_format_inline(text, extra_terms)}</p>\n'


def _format_list(items: list, extra_terms: list) -> str:
    html_items = []
    for item in items:
        item = item.strip().lstrip('•·-–—*#').strip()
        if not item or len(item) < 10:
            continue
        html_items.append(f'  <li>{_format_inline(item, extra_terms)}</li>')
    if not html_items:
        return ''
    return '<ul>\n' + '\n'.join(html_items) + '\n</ul>\n'


def _clean_section_title(title: str) -> str:
    return re.sub(r'[=\[\]{}|]+', '', title).strip()


def _blocks_from_body(body: str) -> list:
    """Split body into non-empty paragraph blocks."""
    raw = [b.strip() for b in re.split(r'\n{2,}', body.strip())]
    return [b for b in raw if b and len(b) > 20 and re.search(r'[a-zA-Z]{3,}', b)]


def _split_into_sections(text: str) -> list:
    """Split Wikipedia plain text into (title, body, level) tuples."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    parts = re.split(r'\n(={2,4})\s*(.+?)\s*\1\n', text)

    sections = []
    if parts[0].strip():
        sections.append(('Overview', parts[0], 2))

    i = 1
    while i < len(parts) - 2:
        level = len(parts[i])
        title = parts[i + 1]
        body = parts[i + 2]
        sections.append((title, body, level))
        i += 3

    return sections


# ── Section body formatters ────────────────────────────────────────────────────

def _format_body_original(body: str, extra_terms: list, max_blocks: int = 3) -> str:
    """
    Original article — curated, structured depth.

    Structure per section:
      • Block 0: intro paragraph (first 3 sentences) + remaining as bullets if ≥ 3 extra
      • Blocks 1+: mixed (paragraph or bullets depending on content shape)
    """
    blocks = _blocks_from_body(body)
    if not blocks:
        return ''
    if max_blocks:
        blocks = blocks[:max_blocks]

    html_parts = []
    for idx, block in enumerate(blocks):
        lines = [l.strip() for l in block.split('\n') if l.strip()]

        # Multi-line list block
        if len(lines) > 2 and _is_list_like(lines):
            html_parts.append(_format_list(lines, extra_terms))
            continue

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', block) if s.strip()]

        if idx == 0:
            # Lead paragraph: first 3 sentences
            intro = ' '.join(sentences[:3])
            html_parts.append(_format_paragraph(intro, extra_terms, lead=True))
            # Remaining sentences as bullet points (if enough material)
            rest = sentences[3:]
            if len(rest) >= 2:
                html_parts.append(_format_list(rest, extra_terms))
        elif len(sentences) >= 5:
            # Long block: 2-sentence intro + bullets
            intro = ' '.join(sentences[:2])
            html_parts.append(_format_paragraph(intro, extra_terms))
            html_parts.append(_format_list(sentences[2:], extra_terms))
        elif len(sentences) >= 3:
            # Medium block: first sentence as para, rest as bullets
            html_parts.append(_format_paragraph(sentences[0], extra_terms))
            html_parts.append(_format_list(sentences[1:], extra_terms))
        else:
            html_parts.append(_format_paragraph(block, extra_terms))

    return ''.join(html_parts)


def _format_body_detail(body: str, extra_terms: list) -> str:
    """
    Detailed article — comprehensive, full content.

    Structure per block:
      • Multi-line list  → bullet list
      • ≥ 5 sentences    → first 2 as paragraph + rest as bullets
      • 3–4 sentences    → full paragraph
      • ≤ 2 sentences    → paragraph
    """
    blocks = _blocks_from_body(body)
    if not blocks:
        return ''

    html_parts = []
    for idx, block in enumerate(blocks):
        lines = [l.strip() for l in block.split('\n') if l.strip()]

        if len(lines) > 2 and _is_list_like(lines):
            html_parts.append(_format_list(lines, extra_terms))
            continue

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', block) if s.strip()]

        if idx == 0 and len(sentences) > 1:
            # Section lead paragraph (all sentences, no splitting)
            html_parts.append(_format_paragraph(block, extra_terms, lead=True))
        elif len(sentences) >= 6:
            # Long: 3-sentence paragraph + bullets
            intro = ' '.join(sentences[:3])
            html_parts.append(_format_paragraph(intro, extra_terms))
            html_parts.append(_format_list(sentences[3:], extra_terms))
        elif len(sentences) >= 4:
            # Medium: 2-sentence paragraph + bullets
            intro = ' '.join(sentences[:2])
            html_parts.append(_format_paragraph(intro, extra_terms))
            html_parts.append(_format_list(sentences[2:], extra_terms))
        else:
            html_parts.append(_format_paragraph(block, extra_terms))

    return ''.join(html_parts)


# ── Importance detection ───────────────────────────────────────────────────────

_GLOBAL_KW = [
    'world war', 'world', 'global', 'international', 'united nations',
    'cold war', 'nuclear', 'pandemic', 'climate', 'ww2', 'wwi', 'wwii',
    'holocaust', 'atomic', 'empire', 'revolution',
]
_CONTINENTAL_KW = [
    'europe', 'asia', 'africa', 'middle east', 'colonial',
    'ottoman', 'mughal', 'mongol', 'crusade', 'silk road',
]
_NATIONAL_KW = [
    'independence', 'partition', 'constitution', 'civil war', 'national',
    'government', 'president', 'prime minister', 'parliament',
]


def _detect_importance(topic: str, country: str) -> str:
    combined = (topic + ' ' + country).lower()
    if any(k in combined for k in _GLOBAL_KW):
        return 'Global'
    if any(k in combined for k in _CONTINENTAL_KW):
        return 'Continental'
    if any(k in combined for k in _NATIONAL_KW):
        return 'National'
    return 'Regional'


# ── Section priority + skip lists ─────────────────────────────────────────────

_SKIP_TITLES = frozenset([
    'see also', 'references', 'notes', 'further reading',
    'external links', 'bibliography', 'citations', 'footnotes',
    'gallery', 'in popular culture',
])

_PRIORITY_TITLES = [
    'overview', 'background', 'history', 'introduction',
    'causes', 'events', 'course', 'key events', 'timeline',
    'people', 'figures', 'leaders',
    'consequences', 'aftermath', 'legacy', 'impact', 'significance',
]


def _section_priority(title: str) -> int:
    t = title.lower()
    for i, p in enumerate(_PRIORITY_TITLES):
        if p in t:
            return i
    return 99


# ── Public API ─────────────────────────────────────────────────────────────────

def format_for_article(
    raw_text: str,
    topic: str,
    year: int,
    country: str,
    era: str,
    max_sections: int = 12,
    max_paras_per_section: int = 4,
) -> dict:
    """
    Original article — structured as a formal historical essay.

    Format:
      A. Introduction  — historical context + thesis-style opening statement
      B. Main Body     — body sections ordered by historical priority,
                         each with topic sentences, evidence, and analysis
                         presented as a mix of prose paragraphs and bullet points
      C. Conclusion    — synthesis section drawn from consequences/legacy/aftermath

    Returns {html, importance_level, key_terms, sources_used}.
    """
    extra_terms = [topic, country, str(year)]
    era_label   = 'BCE' if era == 'bce' else 'CE'
    # Trim raw_text to last complete sentence so formatter never sees mid-word input
    raw_text = _trim_to_sentence(raw_text)
    sections    = _split_into_sections(raw_text)
    if not sections:
        return _fallback(raw_text, extra_terms, topic, year, country)

    # ── Classify sections into intro / body / conclusion buckets ─────────────
    _CONCLUSION_TITLES = frozenset([
        'aftermath', 'legacy', 'consequences', 'significance', 'impact',
        'conclusion', 'result', 'results', 'outcome', 'outcomes',
        'long-term', 'effects', 'effect',
    ])

    intro_secs   = []
    concl_secs   = []
    body_secs    = []

    for s in sections:
        title_low = s[0].lower()
        if any(skip in title_low for skip in _SKIP_TITLES):
            continue
        if not s[1].strip() or len(s[1].strip()) < 30:
            continue
        if title_low in ('overview', '', 'introduction', 'background'):
            intro_secs.append(s)
        elif any(c in title_low for c in _CONCLUSION_TITLES):
            concl_secs.append(s)
        else:
            body_secs.append(s)

    body_secs.sort(key=lambda s: _section_priority(s[0]))

    # ── If no intro found, take the first body section as intro ───────────────
    if not intro_secs and body_secs:
        intro_secs = [body_secs.pop(0)]

    html_parts = []

    # ── A. INTRODUCTION — Hook → Historiography → Pivot → Thesis ──────────────
    if intro_secs:
        html_parts.append(
            '<div class="essay-section essay-intro">'
            '<div class="essay-section-label">Introduction</div>\n'
        )
        for s in intro_secs[:1]:
            body_text = s[1]
            blocks    = _blocks_from_body(body_text)
            if blocks:
                sentences = [sent.strip() for sent in
                             re.split(r'(?<=[.!?])\s+', blocks[0]) if sent.strip()]
                # Hook: first 2 sentences — broad historical landscape
                hook = ' '.join(sentences[:2])
                html_parts.append(f'<p class="section-lead">{_format_inline(hook, extra_terms)}</p>\n')
                # Historiography: next 2–3 sentences framing scholarly debate
                histo = ' '.join(sentences[2:5])
                if histo:
                    html_parts.append(f'<p>{_format_inline(histo, extra_terms)}</p>\n')
                # Pivot + Thesis: drawn from block 1 if available
                if len(blocks) > 1:
                    pivot_sentences = [s.strip() for s in
                                       re.split(r'(?<=[.!?])\s+', blocks[1]) if s.strip()]
                    pivot = ' '.join(pivot_sentences[:1])
                    thesis = ' '.join(pivot_sentences[1:3])
                    if pivot:
                        html_parts.append(f'<p><em>{_format_inline(pivot, extra_terms)}</em></p>\n')
                    if thesis:
                        html_parts.append(f'<p class="section-lead"><strong><em>{_format_inline(thesis, extra_terms)}</em></strong></p>\n')
        html_parts.append('</div>\n')

    # ── B. MAIN BODY — Topic Sentence → Contextualization → Evidence → Analysis ─
    ordered_body = body_secs[:max(max_sections - 2, 3)]
    if ordered_body:
        html_parts.append('<div class="essay-section essay-body">\n')
        sections_shown = 0
        for s in ordered_body:
            if sections_shown >= max_sections - 2:
                break
            title, body_text, level = s[0], s[1], s[2]
            clean_title = _clean_section_title(title)
            if clean_title:
                tag = 'h2' if level <= 2 else 'h3'
                html_parts.append(f'<{tag}>{html_mod.escape(clean_title)}</{tag}>\n')

            blocks = _blocks_from_body(body_text)
            if not blocks:
                continue

            all_sents = [s.strip() for b in blocks[:3]
                         for s in re.split(r'(?<=[.!?])\s+', b) if s.strip()]
            if not all_sents:
                continue

            # Topic sentence
            html_parts.append(f'<p class="section-lead">{_format_inline(all_sents[0], extra_terms)}</p>\n')

            # Historical contextualization: sentences 2-3 (who/what/where/when)
            if len(all_sents) > 2:
                ctx = ' '.join(all_sents[1:3])
                html_parts.append(f'<p>{_format_inline(ctx, extra_terms)}</p>\n')

            # Evidence block: key facts as a structured list
            evidence_sents = all_sents[3:7]
            if len(evidence_sents) >= 2:
                html_parts.append(_format_list(evidence_sents, extra_terms))

            # Historical Analysis "So What?": narrative sentences
            analysis_sents = all_sents[7:11]
            if analysis_sents:
                analysis = ' '.join(analysis_sents)
                html_parts.append(f'<p>{_format_inline(analysis, extra_terms)}</p>\n')

            # Counterargument/Nuance + Transition: last available sentences
            remaining = all_sents[11:]
            if remaining:
                nuance = ' '.join(remaining[:2])
                html_parts.append(
                    f'<p><em>{_format_inline(nuance, extra_terms)}</em></p>\n'
                )

            sections_shown += 1
        html_parts.append('</div>\n')

    # ── C. CONCLUSION — Restatement → Synthesis → Broader Significance ─────────
    if concl_secs:
        html_parts.append(
            '<div class="essay-section essay-conclusion">'
            '<div class="essay-section-label">Conclusion &amp; Historical Significance</div>\n'
        )
        all_concl_sents = []
        for s in concl_secs[:2]:
            blocks = _blocks_from_body(s[1])
            for b in blocks[:2]:
                all_concl_sents += [s.strip() for s in re.split(r'(?<=[.!?])\s+', b) if s.strip()]

        if all_concl_sents:
            # Restatement of thesis
            html_parts.append(f'<p class="section-lead"><strong><em>{_format_inline(all_concl_sents[0], extra_terms)}</em></strong></p>\n')
            # Synthesis of main points
            if len(all_concl_sents) > 2:
                synth = ' '.join(all_concl_sents[1:4])
                html_parts.append(f'<p>{_format_inline(synth, extra_terms)}</p>\n')
            # Broader Historical Significance
            if len(all_concl_sents) > 4:
                significance = ' '.join(all_concl_sents[4:6])
                html_parts.append(f'<p><em>{_format_inline(significance, extra_terms)}</em></p>\n')
        html_parts.append('</div>\n')
    else:
        # Always generate a conclusion — synthesise from ALL body sections' last sentences
        concl_sents = []
        for s in (body_secs[-3:] if body_secs else []):
            blocks = _blocks_from_body(s[1])
            for b in blocks[:1]:
                sents = [x.strip() for x in re.split(r'(?<=[.!?])\s+', b) if x.strip()]
                # Take only complete sentences (ending with punctuation)
                for sent in reversed(sents):
                    if sent and sent[-1] in '.!?':
                        concl_sents.append(sent)
                        break
        if concl_sents:
            html_parts.append(
                '<div class="essay-section essay-conclusion">'
                '<div class="essay-section-label">Conclusion &amp; Historical Significance</div>\n'
            )
            html_parts.append(f'<p class="section-lead"><strong><em>{_format_inline(concl_sents[0], extra_terms)}</em></strong></p>\n')
            if len(concl_sents) > 1:
                synth = ' '.join(concl_sents[1:])
                html_parts.append(f'<p>{_format_inline(synth, extra_terms)}</p>\n')
            html_parts.append('</div>\n')

    final_html = '\n'.join(html_parts)

    if len(final_html) < 200:
        return _fallback(raw_text, extra_terms, topic, year, country)

    # Extract key terms from bold spans, stripping any nested tags
    raw_terms = re.findall(r'<strong>(?:<em>)?(.*?)(?:</em>)?</strong>', final_html)
    key_terms = []
    seen = set()
    for t in raw_terms:
        clean = re.sub(r'<[^>]+>', '', t).strip()
        clean = html_mod.unescape(clean)
        if clean and len(clean) > 3 and len(clean) < 60 and not re.fullmatch(r'[\d\s]+', clean):
            low = clean.lower()
            if low not in seen:
                seen.add(low)
                key_terms.append(clean)
    key_terms = key_terms[:12]

    return {
        'html': final_html,
        'importance_level': _detect_importance(topic, country),
        'key_terms': key_terms,
        'sources_used': ['Wikipedia', 'Wikidata'],
    }


def format_for_detail(
    raw_text: str,
    topic: str,
    year: int,
    country: str,
    era: str,
) -> str:
    """
    Detailed article — comprehensive coverage of all sections.
    Each section uses full prose + bullets; more content than the original view.
    """
    extra_terms = [topic, country, str(year)]
    # Trim raw_text to last complete sentence
    raw_text = _trim_to_sentence(raw_text)
    sections = _split_into_sections(raw_text)

    if not sections:
        return _fallback(raw_text, extra_terms, topic, year, country)['html']

    era_label = 'BCE' if era == 'bce' else 'CE'
    html_parts = [
        f'<p class="section-lead"><em>Comprehensive coverage of '
        f'<strong><em>{html_mod.escape(topic)}</em></strong> '
        f'(<strong>{html_mod.escape(str(year))}</strong>&nbsp;{html_mod.escape(era_label)}, '
        f'<strong><em>{html_mod.escape(country)}</em></strong>).</em></p>\n'
    ]

    has_conclusion = False
    for section_data in sections:
        title, body, level = section_data[0], section_data[1], section_data[2]

        if not body.strip() or len(body.strip()) < 20:
            continue
        if any(s in title.lower() for s in _SKIP_TITLES):
            continue

        # Check if this is a conclusion section
        title_lower = title.lower()
        _CONCL = {'aftermath','legacy','consequences','significance','impact',
                  'conclusion','result','results','outcome','outcomes','long-term','effects'}
        if any(c in title_lower for c in _CONCL):
            has_conclusion = True

        clean_title = _clean_section_title(title)
        if clean_title:
            tag = 'h2' if level <= 2 else 'h3'
            html_parts.append(f'<{tag}>{html_mod.escape(clean_title)}</{tag}>\n')

        formatted = _format_body_detail(body, extra_terms)
        if formatted:
            html_parts.append(formatted)

    # Guarantee a conclusion section if none was found in the source text
    if not has_conclusion and sections:
        last_secs = [s for s in sections if not any(sk in s[0].lower() for sk in _SKIP_TITLES)]
        concl_sents = []
        for s in last_secs[-3:]:
            blocks = _blocks_from_body(s[1])
            for b in blocks[:1]:
                sents = [x.strip() for x in re.split(r'(?<=[.!?])\s+', b) if x.strip() and x.strip()[-1] in '.!?']
                if sents:
                    concl_sents.append(sents[-1])
        if concl_sents:
            html_parts.append(
                '<div class="essay-section essay-conclusion">'
                '<div class="essay-section-label">Conclusion &amp; Historical Significance</div>\n'
            )
            html_parts.append(f'<p class="section-lead"><strong><em>{_format_inline(concl_sents[0], extra_terms)}</em></strong></p>\n')
            if len(concl_sents) > 1:
                html_parts.append(f'<p>{_format_inline(" ".join(concl_sents[1:]), extra_terms)}</p>\n')
            html_parts.append('</div>\n')

    result = '\n'.join(html_parts)
    if len(result) < 300:
        return _fallback(raw_text, extra_terms, topic, year, country)['html']
    return result


def inject_inline_images(article_html: str, images: list) -> str:
    """
    Float up to 6 labelled image figures inside the article body.
    Images are injected BEFORE every other <h2>/<h3> heading so they
    appear visually alongside the relevant section text.
    Alternates float:right / float:left so the essay looks balanced.
    If the article has no headings, injects after every 3rd </p> instead.
    """
    if not article_html or not images:
        return article_html

    valid = [img for img in images if img.get("url")][:6]
    if not valid:
        return article_html

    def _make_figure(img: dict, align: str) -> str:
        url     = html_mod.escape(img["url"])
        title   = re.sub(r"<[^>]+>", "", img.get("title", "") or "")[:70]
        caption = re.sub(r"<[^>]+>", "", img.get("caption", "") or img.get("alt", "") or title)[:120]
        source  = html_mod.escape(img.get("source", "Wikimedia Commons"))
        lic     = img.get("license", "")
        lic_str = f" · {html_mod.escape(lic)}" if lic else ""
        margin  = "margin:0 0 18px 22px" if align == "right" else "margin:0 22px 18px 0"
        return (
            f'<figure style="float:{align};{margin};width:210px;clear:{align};'
            f'background:var(--color-surface);border:1px solid var(--color-border-light);'
            f'border-radius:7px;padding:7px;font-family:var(--font-body);">'
            f'<img src="{url}" alt="{html_mod.escape(title[:80])}" loading="lazy" '
            f'style="width:100%;height:148px;object-fit:cover;border-radius:5px;display:block;" '
            f'onerror="this.parentElement.style.display=\'none\'">'
            f'<figcaption style="margin-top:6px;line-height:1.45;">'
            f'<strong style="font-size:0.78rem;color:var(--color-accent-dark);display:block;'
            f'margin-bottom:3px;">{html_mod.escape(title)}</strong>'
            f'<span style="font-size:0.72rem;color:var(--color-text-secondary);">'
            f'{html_mod.escape(caption)}</span><br>'
            f'<em style="font-size:0.68rem;color:var(--color-text-muted);">'
            f'— {source}{lic_str}</em>'
            f'</figcaption></figure>\n'
        )

    result    = article_html
    offset    = 0
    img_index = 0

    # Prefer injecting before headings (more visually natural)
    heading_matches = list(re.finditer(r'<h[23][^>]*>', article_html))
    inject_before   = [m.start() for m in heading_matches[::2]]

    if not inject_before:
        # Fallback: inject after every 3rd closing </p>
        para_ends     = [m.end() for m in re.finditer(r'</p>', article_html)]
        inject_before = para_ends[2::3]

    for pos in inject_before:
        if img_index >= len(valid):
            break
        align     = "right" if img_index % 2 == 0 else "left"
        fig       = _make_figure(valid[img_index], align)
        insert_at = pos + offset
        result    = result[:insert_at] + fig + result[insert_at:]
        offset   += len(fig)
        img_index += 1

    # Clearfix so subsequent content isn't swallowed by floats
    result += '<div style="clear:both;"></div>\n'
    return result


def _fallback(raw_text: str, extra_terms: list, topic: str, year: int, country: str) -> dict:
    paras = [p.strip() for p in raw_text.split('\n\n') if len(p.strip()) > 40]
    html_parts = [_format_paragraph(p, extra_terms) for p in paras[:8]]
    html = '\n'.join(html_parts) or (
        f'<p><em>Content for <strong>{html_mod.escape(topic)}</strong> '
        f'is loading. Please try a more specific topic.</em></p>'
    )
    return {
        'html': html,
        'importance_level': _detect_importance(topic, country),
        'key_terms': [],
        'sources_used': ['Wikipedia'],
    }
