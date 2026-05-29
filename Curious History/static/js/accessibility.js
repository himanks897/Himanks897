/**
 * accessibility.js — All 15 accessibility features: font size, themes,
 * high contrast, dyslexia font, reduced motion, colour blind, read aloud.
 * All preferences are persisted in localStorage and restored on every page load.
 */

(function() {
  // ── Apply saved preferences immediately (before DOM paint) ─────────────
  const prefs = getPrefs();
  applyAll(prefs);

  document.addEventListener('DOMContentLoaded', function() {
    initPanel();
    restoreUI(prefs);
    initReadAloud();
  });

  function getPrefs() {
    try {
      return JSON.parse(localStorage.getItem('ch_a11y') || '{}');
    } catch(e) { return {}; }
  }

  function savePrefs(updates) {
    const current = getPrefs();
    const merged = Object.assign({}, current, updates);
    localStorage.setItem('ch_a11y', JSON.stringify(merged));
    return merged;
  }

  function applyAll(prefs) {
    const html = document.documentElement;
    // Font size
    html.classList.remove('font-sm', 'font-md', 'font-lg');
    if (prefs.fontSize === 'sm') html.classList.add('font-sm');
    else if (prefs.fontSize === 'lg') html.classList.add('font-lg');

    // Theme
    html.classList.remove('dark', 'warm');
    if (prefs.theme === 'dark') html.classList.add('dark');
    else if (prefs.theme === 'warm') html.classList.add('warm');

    // Toggles
    if (prefs.highContrast) html.classList.add('high-contrast');
    else html.classList.remove('high-contrast');

    if (prefs.dyslexic) html.classList.add('dyslexic');
    else html.classList.remove('dyslexic');

    if (prefs.reducedMotion) html.classList.add('reduced-motion');
    else html.classList.remove('reduced-motion');

    if (prefs.colorBlind) html.classList.add('colorblind');
    else html.classList.remove('colorblind');
  }

  function initPanel() {
    const toggleBtn = document.getElementById('a11y-toggle-btn');
    const panel = document.getElementById('a11y-panel');
    const closeBtn = document.getElementById('a11y-close-btn');

    if (!toggleBtn || !panel) return;

    toggleBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      const open = panel.classList.toggle('show');
      this.setAttribute('aria-expanded', open);
      if (open) {
        closeBtn?.focus();
      }
    });

    if (closeBtn) {
      closeBtn.addEventListener('click', function() {
        panel.classList.remove('show');
        toggleBtn.setAttribute('aria-expanded', 'false');
        toggleBtn.focus();
      });
    }

    // Close on outside click
    document.addEventListener('click', function(e) {
      if (!panel.contains(e.target) && !toggleBtn.contains(e.target)) {
        panel.classList.remove('show');
        toggleBtn.setAttribute('aria-expanded', 'false');
      }
    });

    // Close on Escape
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && panel.classList.contains('show')) {
        panel.classList.remove('show');
        toggleBtn.setAttribute('aria-expanded', 'false');
        toggleBtn.focus();
      }
    });

    // Font size buttons
    bindFontSize();
    // Theme buttons
    bindTheme();
    // Toggle switches
    bindToggle('toggle-contrast', 'highContrast', 'high-contrast');
    bindToggle('toggle-dyslexic', 'dyslexic', 'dyslexic');
    bindToggle('toggle-motion', 'reducedMotion', 'reduced-motion');
    bindToggle('toggle-readaloud', 'readAloud', null);
    bindToggle('toggle-colorblind', 'colorBlind', 'colorblind');
  }

  function restoreUI(prefs) {
    // Font size active button
    const fontBtns = { sm: 'font-sm-btn', md: 'font-md-btn', lg: 'font-lg-btn' };
    Object.entries(fontBtns).forEach(([size, id]) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      const active = (prefs.fontSize === size) || (!prefs.fontSize && size === 'md');
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active);
    });

    // Theme active button
    const themeBtns = { light: 'theme-light-btn', dark: 'theme-dark-btn', warm: 'theme-warm-btn' };
    Object.entries(themeBtns).forEach(([theme, id]) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      const active = (prefs.theme === theme) || (!prefs.theme && theme === 'light');
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-pressed', active);
    });

    // Toggle states
    const toggleMap = {
      'toggle-contrast': 'highContrast',
      'toggle-dyslexic': 'dyslexic',
      'toggle-motion': 'reducedMotion',
      'toggle-readaloud': 'readAloud',
      'toggle-colorblind': 'colorBlind',
    };
    Object.entries(toggleMap).forEach(([id, key]) => {
      const el = document.getElementById(id);
      if (el) el.checked = !!prefs[key];
    });

    // Show read aloud bar if enabled
    if (prefs.readAloud) {
      const bar = document.getElementById('read-aloud-bar');
      if (bar) bar.style.display = 'flex';
    }
  }

  function bindFontSize() {
    const sizes = [
      { id: 'font-sm-btn', size: 'sm' },
      { id: 'font-md-btn', size: 'md' },
      { id: 'font-lg-btn', size: 'lg' },
    ];
    sizes.forEach(({ id, size }) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', function() {
        sizes.forEach(({ id: oid }) => {
          const ob = document.getElementById(oid);
          if (ob) { ob.classList.remove('active'); ob.setAttribute('aria-pressed', 'false'); }
        });
        this.classList.add('active');
        this.setAttribute('aria-pressed', 'true');
        const html = document.documentElement;
        html.classList.remove('font-sm', 'font-lg');
        if (size === 'sm') html.classList.add('font-sm');
        if (size === 'lg') html.classList.add('font-lg');
        savePrefs({ fontSize: size });
      });
    });
  }

  function bindTheme() {
    const themes = [
      { id: 'theme-light-btn', theme: 'light' },
      { id: 'theme-dark-btn', theme: 'dark' },
      { id: 'theme-warm-btn', theme: 'warm' },
    ];
    themes.forEach(({ id, theme }) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', function() {
        themes.forEach(({ id: oid }) => {
          const ob = document.getElementById(oid);
          if (ob) { ob.classList.remove('active'); ob.setAttribute('aria-pressed', 'false'); }
        });
        this.classList.add('active');
        this.setAttribute('aria-pressed', 'true');
        const html = document.documentElement;
        html.classList.remove('dark', 'warm');
        if (theme === 'dark') html.classList.add('dark');
        if (theme === 'warm') html.classList.add('warm');
        savePrefs({ theme });
      });
    });
  }

  function bindToggle(inputId, prefKey, htmlClass) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.addEventListener('change', function() {
      const on = this.checked;
      if (htmlClass) {
        document.documentElement.classList.toggle(htmlClass, on);
      }
      savePrefs({ [prefKey]: on });

      // Special handling for read aloud
      if (prefKey === 'readAloud') {
        const bar = document.getElementById('read-aloud-bar');
        if (bar) bar.style.display = on ? 'flex' : 'none';
        if (!on) stopReadAloud();
      }
    });
  }

  // ── Read Aloud (Accessibility Feature #10) ──────────────────────────────
  let utterance = null;
  let isReading = false;

  // Browsers (especially Chrome) load voices asynchronously.
  // Cache them once available so startReadAloud always gets a good voice.
  let _cachedVoices = [];
  function loadVoices() {
    const v = window.speechSynthesis.getVoices();
    if (v.length) _cachedVoices = v;
  }
  if (window.speechSynthesis) {
    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }

  // Returns the best available voice for Indian English audiences.
  // Priority: Indian English voices → clear British English → any English.
  function getBestVoice() {
    const voices = _cachedVoices.length
      ? _cachedVoices
      : (window.speechSynthesis?.getVoices() || []);

    // 1st priority — Indian English voices (clear and familiar to Indian users)
    const indianPreferred = [
      'Rishi',                    // macOS en-IN — Indian English male, very clear
      'Lekha',                    // macOS en-IN — Indian English female
      'Google Indian English',    // Chrome en-IN — natural Indian English
      'Google हिंदी',              // Chrome hi-IN — fallback if no en-IN
      'Microsoft Heera',          // Windows en-IN — female Indian English
      'Microsoft Ravi',           // Windows en-IN — male Indian English
    ];
    for (const name of indianPreferred) {
      const match = voices.find(v => v.name.includes(name));
      if (match) return match;
    }

    // 2nd priority — any en-IN voice available on device
    const inVoice = voices.find(v => v.lang === 'en-IN');
    if (inVoice) return inVoice;

    // 3rd priority — clear British/Australian English (accent familiar in India)
    const secondaryPreferred = [
      'Daniel',                   // macOS en-GB — clear British male
      'Karen',                    // macOS en-AU
      'Google UK English Female',
      'Google UK English Male',
      'Microsoft George',         // Windows en-GB
      'Microsoft Hazel',          // Windows en-GB
      'Samantha',                 // macOS en-US — clear, last resort
      'Microsoft Zira',
    ];
    for (const name of secondaryPreferred) {
      const match = voices.find(v => v.name.includes(name));
      if (match) return match;
    }

    // Final fallback: any local English voice
    return voices.find(v => v.lang === 'en-GB' && v.localService)
      || voices.find(v => v.lang === 'en-US' && v.localService)
      || voices.find(v => v.lang.startsWith('en-') && v.localService)
      || voices.find(v => v.lang.startsWith('en'))
      || null;
  }

  function initReadAloud() {
    const btn = document.getElementById('read-aloud-btn');
    if (!btn) return;

    btn.addEventListener('click', function() {
      if (isReading) {
        stopReadAloud();
      } else {
        startReadAloud();
      }
    });
  }

  function startReadAloud() {
    if (!window.speechSynthesis) {
      window.showToast?.('Read aloud is not supported in your browser.', 'error');
      return;
    }

    const articleEl = document.getElementById('article-body');
    if (!articleEl) return;

    // Extract clean plain text
    const clone = articleEl.cloneNode(true);
    clone.querySelectorAll('script,style').forEach(el => el.remove());
    const text = (clone.innerText || clone.textContent || '').trim();
    if (!text) return;

    window.speechSynthesis.cancel(); // clear any leftover utterance

    utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;  // slightly slower — easier to follow
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    utterance.lang = 'en-IN'; // prefer Indian English; browser falls back to en if unavailable

    const voice = getBestVoice();
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang; // use the voice's actual lang for correct pronunciation
    }

    utterance.onstart = () => {
      isReading = true;
      const btn = document.getElementById('read-aloud-btn');
      if (btn) btn.innerHTML = '⏸ Pause';
    };
    utterance.onend = utterance.onerror = () => {
      isReading = false;
      const btn = document.getElementById('read-aloud-btn');
      if (btn) btn.innerHTML = '▶ Listen';
    };

    window.speechSynthesis.speak(utterance);
  }

  function stopReadAloud() {
    window.speechSynthesis?.cancel();
    isReading = false;
    const btn = document.getElementById('read-aloud-btn');
    if (btn) btn.innerHTML = '▶ Listen';
  }

  window.stopReadAloud = stopReadAloud;

})();
