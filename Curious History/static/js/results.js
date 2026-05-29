/**
 * results.js — Results page logic: action buttons, simplify, reactions,
 *              highlight-to-save, copy citation, more detail.
 * Reads window.RESULT_DATA set by results.html template.
 */

document.addEventListener('DOMContentLoaded', function() {
  const D = window.RESULT_DATA || {};

  // ── Emoji Reactions ────────────────────────────────────────────────────
  initReactions();

  // ── Action Buttons ─────────────────────────────────────────────────────
  initActionButtons();

  // ── Copy Citation ──────────────────────────────────────────────────────
  initCopyCitation();

  // ── Highlight & Save Quote (Feature #4) ───────────────────────────────
  initHighlightSave();

  // ── More Detail Button ─────────────────────────────────────────────────
  initMoreDetail();

  // ── Load reaction counts ───────────────────────────────────────────────
  loadReactionCounts();

  // ── Wire up image strip lightbox ──────────────────────────────────────
  if (window.initLightbox && window.__inlineImages) {
    window.initLightbox(window.__inlineImages);
  }
});

// ── Emoji Reactions ────────────────────────────────────────────────────────
function initReactions() {
  const D = window.RESULT_DATA || {};
  document.querySelectorAll('.reaction-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const type = this.dataset.reaction;
      const wasSelected = this.classList.contains('selected');

      // Deselect all
      document.querySelectorAll('.reaction-btn').forEach(b => {
        b.classList.remove('selected');
        b.setAttribute('aria-pressed', 'false');
      });

      if (!wasSelected) {
        this.classList.add('selected');
        this.setAttribute('aria-pressed', 'true');
        saveReaction(D.eventKey, type);
      }
    });
  });
}

async function saveReaction(eventKey, type) {
  try {
    await fetch('/api/reactions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_key: eventKey, reaction_type: type }),
    });
    // Update local count
    const countEl = document.getElementById(`reaction-${type}`);
    if (countEl) {
      const current = parseInt(countEl.textContent || '0');
      countEl.textContent = current + 1;
    }
  } catch(e) {
    // Guest reaction — store locally
    const localKey = `ch_reaction_${eventKey}`;
    localStorage.setItem(localKey, type);
  }
}

async function loadReactionCounts() {
  const D = window.RESULT_DATA || {};
  if (!D.eventKey) return;
  try {
    const r = await fetch(`/api/reactions?event_key=${encodeURIComponent(D.eventKey)}`);
    const counts = await r.json();
    Object.entries(counts).forEach(([type, count]) => {
      const el = document.getElementById(`reaction-${type}`);
      if (el) el.textContent = count;
    });
  } catch(e) {}
}

// ── Action Buttons ─────────────────────────────────────────────────────────
function initActionButtons() {
  const D = window.RESULT_DATA || {};

  // Timeline
  bindActionBtn('btn-timeline', '📅 Brief Timeline', async () => {
    const r = await fetch('/api/timeline', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ topic: D.topic, year: D.year, country: D.country }),
    });
    const data = await r.json();
    return `<div class="timeline-wrap">${data.html}</div>`;
  });

  // Images — navigate to full gallery page
  const imagesBtn = document.getElementById('btn-images');
  if (imagesBtn) {
    imagesBtn.addEventListener('click', () => {
      window.location.href =
        `/gallery/images?topic=${encodeURIComponent(D.topic)}&year=${D.year}` +
        `&country=${encodeURIComponent(D.country)}&era=${D.era}`;
    });
  }

  // Maps — navigate to full gallery page
  const mapsBtn = document.getElementById('btn-maps');
  if (mapsBtn) {
    mapsBtn.addEventListener('click', () => {
      window.location.href =
        `/gallery/maps?topic=${encodeURIComponent(D.topic)}&year=${D.year}` +
        `&country=${encodeURIComponent(D.country)}&era=${D.era}`;
    });
  }
}

function bindActionBtn(btnId, panelTitle, fetchFn) {
  const btn = document.getElementById(btnId);
  const panel = document.getElementById('action-panel');
  const body = document.getElementById('action-panel-body');
  const titleEl = document.getElementById('action-panel-title');
  const closeBtn = document.getElementById('action-close-btn');

  if (!btn) return;

  btn.addEventListener('click', async function() {
    // Toggle: if already showing this panel, hide it
    if (panel.classList.contains('show') && titleEl.textContent === panelTitle) {
      panel.classList.remove('show');
      return;
    }

    btn.classList.add('loading');
    btn.innerHTML = btn.innerHTML.replace(/[^🖼📍⚡🤝📅🗺️](.*)/, '$0') + ' Loading…';
    window.pageLoader?.show('Loading ' + panelTitle + '…');

    try {
      const html = await fetchFn();
      titleEl.textContent = panelTitle;
      body.innerHTML = `<div class="article-content">${html}</div>`;
      panel.classList.add('show');
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch(e) {
      window.showError?.('Content Error', `Failed to load ${panelTitle}.`, 'Please try again.');
    } finally {
      window.pageLoader?.hide();
      btn.classList.remove('loading');
      // Restore button text
      const icons = { 'btn-places': '📍 Key Places', 'btn-causes': '⚡ Key Causes', 'btn-people': '🤝 Key People', 'btn-timeline': '📅 Timeline', 'btn-images': '🖼️ Images', 'btn-maps': '🗺️ Maps' };
      btn.innerHTML = `<span class="action-btn-icon">${icons[btnId]?.split(' ')[0] || ''}</span> ${icons[btnId]?.split(' ').slice(1).join(' ') || ''}`;
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => panel.classList.remove('show'));
  }
}

// ── More Detail Button ─────────────────────────────────────────────────────
function initMoreDetail() {
  const D = window.RESULT_DATA || {};
  const btn = document.getElementById('btn-detail');
  const detailPanel = document.getElementById('detail-panel');
  const detailBody = document.getElementById('detail-content-body');
  const originalContent = document.getElementById('original-content');
  const backBtn = document.getElementById('btn-back-to-original');
  const closeBtn = document.getElementById('detail-close-btn');

  if (!btn) return;

  let loaded = false; // fetch once, then reuse

  btn.addEventListener('click', async function() {
    if (detailPanel.classList.contains('show')) {
      detailPanel.classList.remove('show');
      if (originalContent) originalContent.style.display = 'block';
      return;
    }

    if (loaded) {
      detailPanel.classList.add('show');
      if (originalContent) originalContent.style.display = 'none';
      detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    btn.classList.add('loading');
    btn.innerHTML = '<span>📖</span> Loading…';
    window.pageLoader?.show('Loading detailed content…');

    try {
      const r = await fetch('/api/more-detail', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: D.topic, year: D.year, country: D.country, era: D.era }),
      });
      const data = await r.json();
      detailBody.innerHTML = `<div class="article-content">${data.html}</div>`;

      loaded = true;
      detailPanel.classList.add('show');
      if (originalContent) originalContent.style.display = 'none';
      detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch(e) {
      window.showError?.('Content Error', 'Failed to load detailed content.', 'Please try again.');
    } finally {
      window.pageLoader?.hide();
      btn.classList.remove('loading');
      btn.innerHTML = '<span class="action-btn-icon">📖</span> More Detail';
    }
  });

  if (backBtn) {
    backBtn.addEventListener('click', () => {
      detailPanel.classList.remove('show');
      if (originalContent) originalContent.style.display = 'block';
      originalContent?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      detailPanel.classList.remove('show');
      if (originalContent) originalContent.style.display = 'block';
    });
  }
}

// ── Summary — opens new page ───────────────────────────────────────────────
window.openSummary = function(words) {
  const D = window.RESULT_DATA || {};
  window.pageLoader?.show('Generating summary…');
  window.location.href = `/summary-page?topic=${encodeURIComponent(D.topic)}&year=${D.year}&country=${encodeURIComponent(D.country)}&era=${D.era}&words=${words}`;
};

// ── Quiz — opens new page ─────────────────────────────────────────────────
window.openQuiz = function(type) {
  const D = window.RESULT_DATA || {};
  window.pageLoader?.show('Preparing quiz…');
  window.location.href = `/quiz?topic=${encodeURIComponent(D.topic)}&year=${D.year}&country=${encodeURIComponent(D.country)}&era=${D.era}&type=${type}`;
};

// ── Copy with Auto-Citation (Feature #11) ─────────────────────────────────
function initCopyCitation() {
  const D = window.RESULT_DATA || {};
  document.addEventListener('copy', function(e) {
    const articleBody = document.getElementById('article-body');
    if (!articleBody) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;

    // Check if selection is inside article body
    const range = selection.getRangeAt(0);
    if (!articleBody.contains(range.commonAncestorContainer)) return;

    const selectedText = selection.toString();
    if (selectedText.length < 5) return;

    const citation = D.citation || `\n\n— Curious History | ${D.topic} (${D.year}, ${D.country}) | curioshistory.com`;
    e.clipboardData.setData('text/plain', selectedText + citation);
    e.preventDefault();
  });
}

// ── Highlight & Save as Quote (Feature #4) ────────────────────────────────
function initHighlightSave() {
  const D = window.RESULT_DATA || {};
  const tooltip = document.getElementById('highlight-tooltip');
  const articleBody = document.getElementById('article-body');
  if (!tooltip || !articleBody) return;

  let savedRange = null;

  function handleSelection() {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) {
      tooltip.classList.remove('show');
      return;
    }

    const text = selection.toString().trim();
    if (text.length < 10 || text.length > 300) {
      tooltip.classList.remove('show');
      return;
    }

    // Only inside article body
    const range = selection.getRangeAt(0);
    if (!articleBody.contains(range.commonAncestorContainer)) {
      tooltip.classList.remove('show');
      return;
    }

    savedRange = range;

    // Position tooltip near selection
    const rect = range.getBoundingClientRect();
    tooltip.style.top = `${rect.top + window.scrollY - 40}px`;
    tooltip.style.left = `${rect.left + window.scrollX}px`;
    tooltip.classList.add('show');
  }

  document.addEventListener('mouseup', handleSelection);
  document.addEventListener('touchend', handleSelection);

  tooltip.addEventListener('click', function() {
    if (!savedRange) return;
    const text = window.getSelection().toString().trim();
    if (!text) return;

    // Save to localStorage (and Supabase for logged-in users)
    let quotes = [];
    try { quotes = JSON.parse(localStorage.getItem('ch_saved_quotes') || '[]'); } catch(e) {}
    quotes.unshift({
      text: text,
      source_topic: D.topic,
      source_year: D.year,
      saved_at: new Date().toISOString(),
    });
    localStorage.setItem('ch_saved_quotes', JSON.stringify(quotes.slice(0, 50)));

    // API save attempt
    fetch('/api/save-quote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, source_topic: D.topic, source_year: D.year }),
    }).catch(() => {});

    tooltip.classList.remove('show');
    window.getSelection()?.removeAllRanges();
    window.showToast?.('Quote saved to your collection! 💬', 'success');
  });

  document.addEventListener('mousedown', function(e) {
    if (!tooltip.contains(e.target)) {
      tooltip.classList.remove('show');
    }
  });
}

// ── Intersperse inline images ─────────────────────────────────────────────
/**
 * Insert images evenly spaced through article content.
 * @param {Element|null} container  - article container element (null = #article-body)
 * @param {Array}        images     - array of image objects from window.__inlineImages
 * @param {number}       maxImages  - maximum number of images to insert
 */
function insertInlineImages(container, images, maxImages) {
  container = container || document.getElementById('article-body');
  images    = images    || window.__inlineImages || [];
  maxImages = maxImages || 3;

  if (!images.length || !container) return;

  // Target both <p> and <ul> so images break up all content types
  const blocks = Array.from(container.querySelectorAll('p, ul, h2, h3'));
  if (blocks.length < 2) return;

  const toInsert = images.filter(img => img && img.url).slice(0, maxImages);
  if (!toInsert.length) return;

  // Distribute evenly: place after block at ~33%, ~60%, ~80% of content
  const step = Math.floor(blocks.length / (toInsert.length + 1));
  toInsert.forEach((img, i) => {
    const blockIdx = step * (i + 1);
    const block = blocks[Math.min(blockIdx, blocks.length - 1)];
    if (!block) return;

    // Don't insert directly after a heading
    if (block.tagName === 'H2' || block.tagName === 'H3') return;

    const label   = (img.caption || img.title || 'Historical image').trim();
    const source  = (img.source || 'Wikimedia Commons').trim();
    const license = img.license ? ` · ${img.license}` : '';

    const figure = document.createElement('figure');
    figure.className = 'article-image';
    figure.innerHTML = `
      <img
        src="${escAttr(img.url)}"
        alt="${escAttr(img.alt || label)}"
        loading="lazy"
        onerror="this.parentElement.style.display='none'"
      >
      <figcaption>
        <strong>${escHtml(label)}</strong>
        <em class="img-source">Source: ${escHtml(source)}${escHtml(license)}</em>
      </figcaption>
    `;
    block.parentNode.insertBefore(figure, block.nextSibling);
  });
}

function escAttr(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;');
}
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Expose images to inline script (set by template)
window.__inlineImages = window.__inlineImages || [];
