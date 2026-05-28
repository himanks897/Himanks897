/**
 * features.js — Unique feature implementations: streaks, milestones,
 *               save event, warm mode toggle, search streaks.
 * Runs on pages that extend base.html.
 */

document.addEventListener('DOMContentLoaded', function() {
  checkMilestones();
  initSaveEventBtn();
  initGuestLimit();
});

// ── Guest Search Limit — 3 searches per month for guest users ─────────────
// Stored in localStorage so it persists across tabs/sessions without a server.
// Key: ch_guest_limit  →  { count: N, month: "YYYY-MM" }

var GUEST_MONTHLY_LIMIT = 3;

function _getGuestLimitStore() {
  try {
    return JSON.parse(localStorage.getItem('ch_guest_limit') || '{"count":0,"month":""}');
  } catch(e) { return { count: 0, month: '' }; }
}

function _saveGuestLimitStore(store) {
  try { localStorage.setItem('ch_guest_limit', JSON.stringify(store)); } catch(e) {}
}

function _currentMonth() {
  var d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

/* Returns true if the search is allowed; false if the limit is hit. */
window.checkGuestSearchAllowed = function() {
  /* If the user is signed in (Google), no limit applies */
  var avatarImg = document.querySelector('#user-menu-btn img');
  if (avatarImg) return true;   /* signed-in users have a profile photo in the nav */

  var store  = _getGuestLimitStore();
  var month  = _currentMonth();

  if (store.month !== month) {
    /* New month — reset counter */
    store = { count: 0, month: month };
  }

  if (store.count >= GUEST_MONTHLY_LIMIT) {
    showGuestLimitPopup();
    return false;
  }

  /* Increment and allow */
  store.count += 1;
  _saveGuestLimitStore(store);
  return true;
};

function showGuestLimitPopup() {
  var overlay = document.getElementById('guest-limit-overlay');
  if (!overlay) return;
  overlay.classList.add('show');
  overlay.setAttribute('aria-hidden', 'false');
  /* Focus the CTA for keyboard/screen-reader users */
  var cta = overlay.querySelector('.guest-limit-cta');
  if (cta) setTimeout(function() { cta.focus(); }, 320);
}

function hideGuestLimitPopup() {
  var overlay = document.getElementById('guest-limit-overlay');
  if (!overlay) return;
  overlay.classList.remove('show');
  overlay.setAttribute('aria-hidden', 'true');
}

function initGuestLimit() {
  /* Close button inside the popup */
  var closeBtn = document.getElementById('guest-limit-close');
  if (closeBtn) closeBtn.addEventListener('click', hideGuestLimitPopup);

  /* Click the dark overlay background to dismiss */
  var overlay = document.getElementById('guest-limit-overlay');
  if (overlay) {
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) hideGuestLimitPopup();
    });
  }

  /* Escape key to close */
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') hideGuestLimitPopup();
  });
}

// ── Milestone Celebrations (Feature #20) ──────────────────────────────────
function checkMilestones() {
  const totalSearches = parseInt(localStorage.getItem('ch_total_searches') || '0');
  const milestones = JSON.parse(localStorage.getItem('ch_milestones') || '[]');

  const milestoneMap = {
    1:  "You've made your first search — Welcome to Curious History! 🎉",
    10: "You've explored 10 events — History is yours. 📚",
    25: "25 discoveries! You're becoming a true historian. 🏛️",
    50: "50 events explored! History holds no secrets from you. 🏆",
  };

  for (const [count, msg] of Object.entries(milestoneMap)) {
    if (totalSearches >= parseInt(count) && !milestones.includes(count)) {
      milestones.push(count);
      localStorage.setItem('ch_milestones', JSON.stringify(milestones));
      showMilestone(msg);
      break;
    }
  }

  // Streak milestones
  const streak = parseInt(localStorage.getItem('ch_streak') || '0');
  if (streak >= 7 && !milestones.includes('streak-7')) {
    milestones.push('streak-7');
    localStorage.setItem('ch_milestones', JSON.stringify(milestones));
    showMilestone("🔥 7-day streak! You're on a roll — keep exploring!");
  }
  if (streak >= 30 && !milestones.includes('streak-30')) {
    milestones.push('streak-30');
    localStorage.setItem('ch_milestones', JSON.stringify(milestones));
    showMilestone("🔥 30-day streak! You're a dedicated history scholar!");
  }
}

function showMilestone(message) {
  // Check reduced motion
  const prefs = JSON.parse(localStorage.getItem('ch_a11y') || '{}');
  if (prefs.reducedMotion) return;

  // Golden shimmer on avatar
  const avatarBtn = document.getElementById('user-menu-btn');
  if (avatarBtn) {
    avatarBtn.classList.add('milestone-glow');
    setTimeout(() => avatarBtn.classList.remove('milestone-glow'), 4000);
  }

  // Toast notification (no popup, no sound)
  window.showToast?.(message, 'success', 5000);
}

// ── Save Event (Feature — saves to localStorage + API) ─────────────────────
function initSaveEventBtn() {
  const D = window.RESULT_DATA;
  if (!D) return;

  // Increment search count on results page
  const count = parseInt(localStorage.getItem('ch_total_searches') || '0') + 1;
  localStorage.setItem('ch_total_searches', count);
  checkMilestones();
}

// ── Warm Mode Toggle (Feature #10) ─────────────────────────────────────────
// (Handled by accessibility.js theme toggle — 'warm' theme class)

// ── History Streak Counter (Feature #12) ───────────────────────────────────
// (Handled in main.js checkStreak function)

// ── Export saveEvent for use by results page ────────────────────────────────
window.saveCurrentEvent = function() {
  const D = window.RESULT_DATA;
  if (!D) return;

  let events = [];
  try { events = JSON.parse(localStorage.getItem('ch_saved_events') || '[]'); } catch(e) {}

  // Check not already saved
  if (events.find(e => e.topic === D.topic && String(e.year) === String(D.year))) {
    window.showToast?.('Already saved!', 'info');
    return;
  }

  events.unshift({
    topic: D.topic,
    year: D.year,
    country: D.country,
    era: D.era,
    saved_at: new Date().toISOString(),
  });
  localStorage.setItem('ch_saved_events', JSON.stringify(events.slice(0, 100)));

  // API save
  fetch('/api/save-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic: D.topic, year: D.year, country: D.country }),
  }).catch(() => {});

  window.showToast?.('Event saved to your collection! 📚', 'success');

  // Check first save milestone
  const milestones = JSON.parse(localStorage.getItem('ch_milestones') || '[]');
  if (!milestones.includes('first-save')) {
    milestones.push('first-save');
    localStorage.setItem('ch_milestones', JSON.stringify(milestones));
    showMilestone('You saved your first event! Your collection has begun. 📚');
  }
};
