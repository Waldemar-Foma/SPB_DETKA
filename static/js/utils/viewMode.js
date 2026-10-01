const STORAGE_KEY = 'procurement-view';
const VALID = ['map', 'list'];
const DEFAULT = 'map';

export function initViewMode() {
  if (document.body.dataset.page !== 'dashboard') return;
  const saved = localStorage.getItem(STORAGE_KEY);
  setViewMode(VALID.includes(saved) ? saved : DEFAULT, { silent: true });
  document.querySelectorAll('.view-tab').forEach((tab) => {
    tab.addEventListener('click', () => setViewMode(tab.dataset.view));
  });
}

export function setViewMode(mode, { silent = false } = {}) {
  if (!VALID.includes(mode)) mode = DEFAULT;
  document.body.dataset.view = mode;
  localStorage.setItem(STORAGE_KEY, mode);
  document.querySelectorAll('.view-tab').forEach((tab) => tab.classList.toggle('is-active', tab.dataset.view === mode));
  if (!silent) requestAnimationFrame(() => document.dispatchEvent(new CustomEvent('view:changed', { detail: { mode } })));
}
