/**
 * main.js — Global JavaScript: nav search, user menu, dropdown logic, toast system.
 * Runs on every page that extends base.html.
 */

// ── Page Loader ────────────────────────────────────────────────────────────
(function () {
  var loader = document.getElementById('page-loader');

  // Track when the loader was last shown so we can enforce a minimum display time
  var _showedAt = Date.now();
  var _MIN_VISIBLE_MS = 350;  // always visible for at least 350 ms

  function _buildLoader() {
    var el = document.createElement('div');
    el.id = 'page-loader';
    el.className = 'page-loader';
    el.setAttribute('aria-hidden', 'true');
    el.innerHTML =
      '<div class="loader-inner">' +
        '<div class="loader-logo">Curious <span>History</span></div>' +
        '<div class="loader-spinner">' +
          '<div class="loader-ring"></div>' +
          '<div class="loader-ring loader-ring-2"></div>' +
        '</div>' +
        '<p class="loader-tagline">Every year. Every country. Every story.</p>' +
      '</div>';
    document.body.appendChild(el);
    return el;
  }

  // Ensure the loader element exists in the page. If base.html already put it
  // there we use it directly; otherwise we create one (e.g. standalone pages).
  if (!loader) {
    loader = _buildLoader();
  }

  // ── Public API (used by results.js for in-page loading) ────────────────
  window.pageLoader = {
    show: function (label) {
      if (!loader || !document.body.contains(loader)) {
        loader = _buildLoader();
      }
      _showedAt = Date.now();
      var tag = loader.querySelector('.loader-tagline');
      if (tag) tag.textContent = label || 'Every year. Every country. Every story.';
      loader.classList.remove('loader-hidden');
    },
    hide: function () {
      if (!loader) return;
      var elapsed  = Date.now() - _showedAt;
      var delay    = Math.max(0, _MIN_VISIBLE_MS - elapsed);
      setTimeout(function () {
        loader && loader.classList.add('loader-hidden');
      }, delay);
    },
  };

  // ── Hide once the page has fully loaded (minimum 350 ms always shown) ─
  // Loader stays in DOM — never removed — so show() is always instant.
  function hideLoader() {
    window.pageLoader.hide();
  }

  if (document.readyState === 'complete') {
    hideLoader();
  } else {
    window.addEventListener('load', hideLoader);
  }

  // ── Intercept internal anchor clicks ─────────────────────────────────
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript') ||
        href.startsWith('mailto') || a.target === '_blank') return;
    try { if (new URL(href, location.href).origin !== location.origin) return; }
    catch (_) { return; }
    window.pageLoader.show();
  }, { capture: true });

  // ── Intercept form submissions (catches topic page Enter press) ───────
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || e.defaultPrevented) return;
    var action = form.action || '';
    try { if (action && new URL(action).origin !== location.origin) return; }
    catch (_) {}
    window.pageLoader.show();
  }, { capture: true });

}());

// ── Toast Notification System ──────────────────────────────────────────────
window.showToast = function(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', 'alert');
  toast.innerHTML = `<span class="toast-icon" aria-hidden="true">${icons[type] || 'ℹ️'}</span><span><em>${message}</em></span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, duration);
};

// showError — Accessibility Feature #13
window.showError = function(title, message, suggestion) {
  const full = suggestion ? `${title}: ${message} — ${suggestion}` : `${title}: ${message}`;
  showToast(full, 'error', 5000);
};

// ── Nav: User Menu Dropdown ─────────────────────────────────────────────────
const userMenuBtn = document.getElementById('user-menu-btn');
const userMenu = document.getElementById('user-menu');

if (userMenuBtn && userMenu) {
  userMenuBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    const open = userMenu.classList.toggle('show');
    this.setAttribute('aria-expanded', open);
  });
  document.addEventListener('click', () => {
    userMenu?.classList.remove('show');
    userMenuBtn?.setAttribute('aria-expanded', 'false');
  });
  userMenu.addEventListener('click', e => e.stopPropagation());
}

// ── Nav: Action Buttons in User Menu ───────────────────────────────────────
const surpriseNavBtn = document.getElementById('surprise-btn');
if (surpriseNavBtn) {
  surpriseNavBtn.addEventListener('click', async function() {
    try {
      const r = await fetch('/api/surprise');
      const data = await r.json();
      window.location.href = `/results?topic=${encodeURIComponent(data.topic)}&year=${data.year}&country=${encodeURIComponent(data.country)}&era=${data.era}`;
    } catch(e) {
      showError('Navigation Error', 'Could not load random event.', 'Please try again.');
    }
  });
}

// ── Global Live Search ──────────────────────────────────────────────────────
const navSearch = document.getElementById('nav-search');
const navResults = document.getElementById('nav-search-results');

if (navSearch && navResults) {
  let searchTimeout;

  navSearch.addEventListener('input', function() {
    const q = this.value.trim();
    clearTimeout(searchTimeout);
    if (q.length < 3) {
      navResults.classList.remove('show');
      navResults.innerHTML = '';
      return;
    }
    searchTimeout = setTimeout(() => doNavSearch(q), 350);
  });

  navSearch.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      navResults.classList.remove('show');
      this.value = '';
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const first = navResults.querySelector('[role="option"]');
      first?.focus();
    }
  });

  document.addEventListener('click', e => {
    if (!navSearch.contains(e.target) && !navResults.contains(e.target)) {
      navResults.classList.remove('show');
    }
  });
}

async function doNavSearch(q) {
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await r.json();
    renderNavResults(data.results || []);
  } catch(e) {
    navResults.classList.remove('show');
  }
}

function renderNavResults(results) {
  if (!results.length) {
    navResults.classList.remove('show');
    return;
  }
  navResults.innerHTML = results.map(r => `
    <div
      class="nav-search-result-item"
      role="option"
      tabindex="0"
      aria-label="Search for ${r.title}"
      data-title="${r.title}"
    >
      <strong><em>${r.title}</em></strong>
      <br>
      <span style="font-size:0.78rem;color:var(--color-text-muted);">${(r.snippet || '').substring(0, 80)}…</span>
    </div>
  `).join('');
  navResults.classList.add('show');

  navResults.querySelectorAll('[role="option"]').forEach(item => {
    item.addEventListener('click', function() {
      const title = this.dataset.title;
      const year = new Date().getFullYear();
      window.location.href = `/results?topic=${encodeURIComponent(title)}&year=${year}&country=World&era=ce`;
    });
    item.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') this.click();
      if (e.key === 'ArrowDown') { e.preventDefault(); this.nextElementSibling?.focus(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); this.previousElementSibling?.focus() || navSearch.focus(); }
    });
  });
}

// ── Dropdown Generic Toggle ─────────────────────────────────────────────────
document.querySelectorAll('.dropdown > button[aria-haspopup]').forEach(btn => {
  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    const menu = this.nextElementSibling;
    if (!menu) return;
    const open = menu.classList.toggle('show');
    this.setAttribute('aria-expanded', open);
    // Close other dropdowns
    document.querySelectorAll('.dropdown-menu.show').forEach(m => {
      if (m !== menu) {
        m.classList.remove('show');
        m.previousElementSibling?.setAttribute('aria-expanded', 'false');
      }
    });
  });
});

document.addEventListener('click', () => {
  document.querySelectorAll('.dropdown-menu.show').forEach(m => {
    m.classList.remove('show');
    m.previousElementSibling?.setAttribute('aria-expanded', 'false');
  });
});

// ── Confidence Badge Popover ────────────────────────────────────────────────
const confidenceBtn = document.getElementById('confidence-btn');
const confidencePopover = document.getElementById('confidence-popover');

if (confidenceBtn && confidencePopover) {
  confidenceBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    const open = confidencePopover.classList.toggle('show');
    this.setAttribute('aria-expanded', open);
  });
  document.addEventListener('click', () => {
    confidencePopover?.classList.remove('show');
    confidenceBtn?.setAttribute('aria-expanded', 'false');
  });
}

// ── Share Button ────────────────────────────────────────────────────────────
const shareBtn = document.getElementById('share-btn');
if (shareBtn) {
  shareBtn.addEventListener('click', function() {
    const url = window.location.href;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => {
        showToast('Link copied to clipboard!', 'success');
      });
    } else {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = url;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      showToast('Link copied to clipboard!', 'success');
    }
  });
}

// ── Glossary Toggle ─────────────────────────────────────────────────────────
const glossaryToggle = document.getElementById('glossary-toggle');
const glossaryBody = document.getElementById('glossary-body');

if (glossaryToggle && glossaryBody) {
  glossaryToggle.addEventListener('click', function() {
    const open = glossaryBody.classList.toggle('open');
    this.setAttribute('aria-expanded', open);
  });
  glossaryToggle.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.click(); }
  });
}

// ── Session Timeout (Accessibility Feature #15) ─────────────────────────────
let sessionTimer, warningTimer;

function resetSessionTimer() {
  clearTimeout(sessionTimer);
  clearTimeout(warningTimer);
  const banner = document.getElementById('session-banner');
  if (banner) banner.classList.remove('show');

  warningTimer = setTimeout(() => {
    const b = document.getElementById('session-banner');
    if (b) b.classList.add('show');
  }, 25 * 60 * 1000);

  sessionTimer = setTimeout(() => {
    showToast('You were signed out due to inactivity. Your progress has been saved.', 'info', 6000);
    setTimeout(() => window.location.href = '/', 6000);
  }, 30 * 60 * 1000);
}

['click', 'keydown', 'scroll', 'touchstart'].forEach(ev => {
  document.addEventListener(ev, resetSessionTimer, { passive: true });
});
resetSessionTimer();

// Streak counter init (Feature #12)
(function checkStreak() {
  const today = new Date().toISOString().split('T')[0];
  const lastVisit = localStorage.getItem('ch_last_visit');
  let streak = parseInt(localStorage.getItem('ch_streak') || '0');

  if (lastVisit === today) return;

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yStr = yesterday.toISOString().split('T')[0];

  if (lastVisit === yStr) {
    streak++;
  } else if (lastVisit !== today) {
    streak = 1;
  }

  localStorage.setItem('ch_streak', streak);
  localStorage.setItem('ch_last_visit', today);

  // Update streak badge
  const avatarBtn = document.getElementById('user-menu-btn');
  if (avatarBtn && streak > 1) {
    avatarBtn.title = `🔥 ${streak}-day streak`;
  }
})();
