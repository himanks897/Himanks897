/**
 * lightbox.js — Full-screen image viewer with zoom +/− controls and prev/next navigation.
 * Call window.initLightbox(images) with [{url, title, caption, alt, wiki_url}] array.
 * Gallery cards with data-lightbox-index are auto-wired on init.
 */
(function () {
  'use strict';

  let _images = [];
  let _current = 0;
  let _scale = 1.0;

  const ZOOM_STEP = 0.25;
  const MIN_ZOOM  = 0.5;
  const MAX_ZOOM  = 4.0;

  // ── DOM creation ────────────────────────────────────────────────────────────
  function _createLightbox() {
    if (document.getElementById('lightbox')) return;

    const lb = document.createElement('div');
    lb.id = 'lightbox';
    lb.className = 'lightbox';
    lb.setAttribute('role', 'dialog');
    lb.setAttribute('aria-modal', 'true');
    lb.setAttribute('aria-label', 'Image viewer');
    lb.style.display = 'none';

    lb.innerHTML = `
      <div class="lb-overlay" id="lb-overlay"></div>
      <div class="lb-container" role="document">
        <div class="lb-header">
          <span class="lb-title" id="lb-title"></span>
          <button class="lb-close" id="lb-close" aria-label="Close image viewer">&#x2715;</button>
        </div>
        <div class="lb-stage">
          <button class="lb-nav lb-prev" id="lb-prev" aria-label="Previous image">&#8249;</button>
          <div class="lb-image-wrap" id="lb-image-wrap">
            <img id="lb-img" src="" alt="" draggable="false">
          </div>
          <button class="lb-nav lb-next" id="lb-next" aria-label="Next image">&#8250;</button>
        </div>
        <div class="lb-footer">
          <p class="lb-caption" id="lb-caption"></p>
          <div class="lb-controls">
            <div class="lb-zoom-group">
              <button class="lb-zoom-btn" id="lb-zoom-out" aria-label="Zoom out" title="Zoom out (−)">&#x2212;</button>
              <span class="lb-zoom-level" id="lb-zoom-level">100%</span>
              <button class="lb-zoom-btn" id="lb-zoom-in"  aria-label="Zoom in"  title="Zoom in (+)">+</button>
            </div>
            <button class="lb-download-btn" id="lb-download-btn" aria-label="Download image" title="Download image">&#x2B07; Download</button>
            <a class="lb-wiki-link" id="lb-wiki-link" href="#" target="_blank" rel="noopener noreferrer" style="display:none;">Wikipedia &#x2192;</a>
            <span class="lb-counter" id="lb-counter"></span>
          </div>
        </div>
      </div>`;

    document.body.appendChild(lb);

    // Bind fixed listeners
    document.getElementById('lb-close').addEventListener('click', close);
    document.getElementById('lb-overlay').addEventListener('click', close);
    document.getElementById('lb-prev').addEventListener('click', prev);
    document.getElementById('lb-next').addEventListener('click', next);
    document.getElementById('lb-zoom-in').addEventListener('click', zoomIn);
    document.getElementById('lb-zoom-out').addEventListener('click', zoomOut);
    document.getElementById('lb-download-btn').addEventListener('click', downloadImage);

    document.addEventListener('keydown', _onKey);

    // Wheel zoom on image area
    document.getElementById('lb-image-wrap').addEventListener('wheel', function (e) {
      e.preventDefault();
      if (e.deltaY < 0) zoomIn(); else zoomOut();
    }, { passive: false });

    // Touch swipe for mobile
    let _touchX = 0;
    const stage = lb.querySelector('.lb-stage');
    stage.addEventListener('touchstart', function (e) {
      _touchX = e.changedTouches[0].clientX;
    }, { passive: true });
    stage.addEventListener('touchend', function (e) {
      const dx = e.changedTouches[0].clientX - _touchX;
      if (Math.abs(dx) > 50) { if (dx > 0) prev(); else next(); }
    }, { passive: true });
  }

  // ── Open / Close ────────────────────────────────────────────────────────────
  function open(index) {
    _current = Math.max(0, Math.min(index, _images.length - 1));
    _scale = 1.0;
    _createLightbox();
    _update();
    const lb = document.getElementById('lightbox');
    lb.style.display = 'flex';
    requestAnimationFrame(() => lb.classList.add('lb-show'));
    document.body.style.overflow = 'hidden';
    document.getElementById('lb-close').focus();
  }

  function close() {
    const lb = document.getElementById('lightbox');
    if (!lb) return;
    lb.classList.remove('lb-show');
    setTimeout(() => { if (lb) lb.style.display = 'none'; }, 280);
    document.body.style.overflow = '';
  }

  // ── Navigate ────────────────────────────────────────────────────────────────
  function prev() {
    if (_current > 0) { _current--; resetZoom(false); _update(); }
  }
  function next() {
    if (_current < _images.length - 1) { _current++; resetZoom(false); _update(); }
  }

  // ── Update display ──────────────────────────────────────────────────────────
  function _update() {
    const img_data = _images[_current];
    if (!img_data) return;

    const img      = document.getElementById('lb-img');
    const title    = document.getElementById('lb-title');
    const caption  = document.getElementById('lb-caption');
    const counter  = document.getElementById('lb-counter');
    const prevBtn  = document.getElementById('lb-prev');
    const nextBtn  = document.getElementById('lb-next');
    const wikiLink = document.getElementById('lb-wiki-link');

    img.src = '';
    img.src = img_data.url || img_data.src || '';
    img.alt = img_data.alt || img_data.title || 'Historical image';

    title.textContent   = img_data.title || '';
    caption.textContent = img_data.caption || img_data.description || '';
    counter.textContent = _images.length > 1 ? `${_current + 1} / ${_images.length}` : '';

    if (img_data.wiki_url) {
      wikiLink.href  = img_data.wiki_url;
      wikiLink.style.display = '';
    } else {
      wikiLink.style.display = 'none';
    }

    prevBtn.disabled = _current === 0;
    nextBtn.disabled = _current === _images.length - 1;
    prevBtn.style.opacity = _current === 0 ? '0.25' : '1';
    nextBtn.style.opacity = _current === _images.length - 1 ? '0.25' : '1';

    _applyZoom();
  }

  // ── Zoom ────────────────────────────────────────────────────────────────────
  function zoomIn()  { _scale = Math.min(MAX_ZOOM, _scale + ZOOM_STEP); _applyZoom(); }
  function zoomOut() { _scale = Math.max(MIN_ZOOM, _scale - ZOOM_STEP); _applyZoom(); }
  function resetZoom(apply) {
    _scale = 1.0;
    if (apply !== false) _applyZoom();
  }
  function _applyZoom() {
    const img   = document.getElementById('lb-img');
    const level = document.getElementById('lb-zoom-level');
    if (img)   img.style.transform   = `scale(${_scale})`;
    if (level) level.textContent     = `${Math.round(_scale * 100)}%`;
  }

  // ── Download ─────────────────────────────────────────────────────────────────
  async function downloadImage() {
    const img_data = _images[_current];
    if (!img_data || !img_data.url) return;

    const btn = document.getElementById('lb-download-btn');
    if (btn) { btn.textContent = '⏳ Saving…'; btn.disabled = true; }

    try {
      // Fetch as blob so the browser saves it instead of opening in a new tab
      const resp = await fetch(img_data.url, { mode: 'cors' });
      const blob = await resp.blob();
      const objectUrl = URL.createObjectURL(blob);

      // Build a clean filename from the image title
      const raw = (img_data.title || 'historical-image')
        .replace(/[^a-zA-Z0-9 _-]/g, '').trim().replace(/\s+/g, '-').slice(0, 60) ||
        'historical-image';
      const ext = (img_data.url.split('?')[0].split('.').pop() || 'jpg').toLowerCase();
      const filename = raw + '.' + (ext.match(/^(jpg|jpeg|png|gif|webp)$/) ? ext : 'jpg');

      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(objectUrl), 8000);
    } catch (_err) {
      // Fallback for images that block CORS: open in a new tab — user can long-press / right-click to save
      window.open(img_data.url, '_blank', 'noopener');
    } finally {
      if (btn) { btn.innerHTML = '&#x2B07; Download'; btn.disabled = false; }
    }
  }

  // ── Keyboard ────────────────────────────────────────────────────────────────
  function _onKey(e) {
    const lb = document.getElementById('lightbox');
    if (!lb || lb.style.display === 'none') return;
    switch (e.key) {
      case 'Escape':      close();     break;
      case 'ArrowLeft':   prev();      break;
      case 'ArrowRight':  next();      break;
      case '+': case '=': zoomIn();    break;
      case '-':           zoomOut();   break;
      case '0':           resetZoom(true); break;
    }
  }

  // ── Auto-wire gallery cards ──────────────────────────────────────────────────
  function _attachCards() {
    document.querySelectorAll('.gallery-card[data-lightbox-index]').forEach(function (card) {
      card.addEventListener('click', function () {
        open(parseInt(this.dataset.lightboxIndex || '0', 10));
      });
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open(parseInt(this.dataset.lightboxIndex || '0', 10));
        }
      });
    });
  }

  // ── Event delegation: person mini-portrait click (works for dynamic content) ─
  document.addEventListener('click', function (e) {
    const portrait = e.target.closest('.person-mini-portrait');
    if (!portrait) return;
    e.stopPropagation();
    _images = [{
      url:     portrait.dataset.lbSrc     || portrait.src || '',
      title:   portrait.dataset.lbTitle   || portrait.alt || '',
      caption: portrait.dataset.lbCaption || '',
      alt:     portrait.alt               || '',
    }];
    _createLightbox();
    open(0);
  });

  // ── Public API ───────────────────────────────────────────────────────────────
  window.initLightbox = function (imageArray) {
    _images = Array.isArray(imageArray) ? imageArray : [];
    _createLightbox();
    _attachCards();
  };

  window.openLightbox = open;
}());
