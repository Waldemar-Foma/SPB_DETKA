/**
 * Управление режимом отображения: map | widgets | list.
 * - map     — карта + KPI + AI. Виджеты фиксированы.
 * - widgets — то же, но виджеты можно перетаскивать.
 * - list    — карта и виджеты скрыты, показывается таблица.
 */
const STORAGE_KEY = 'spb-view';
const VALID = ['map', 'widgets', 'list'];
const DEFAULT = 'map';

export function initViewMode() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const initial = VALID.includes(saved) ? saved : DEFAULT;
  setViewMode(initial, { silent: true });
  bindTabs();
}

export function setViewMode(mode, { silent = false } = {}) {
  if (!VALID.includes(mode)) mode = DEFAULT;
  document.body.dataset.view = mode;
  localStorage.setItem(STORAGE_KEY, mode);

  document.querySelectorAll('.view-tab').forEach((tab) => {
    tab.classList.toggle('is-active', tab.dataset.view === mode);
  });

  if (!silent) {
    requestAnimationFrame(() => {
      document.dispatchEvent(new CustomEvent('view:changed', { detail: { mode } }));
    });
  }
}

export function getViewMode() {
  return document.body.dataset.view || DEFAULT;
}

function bindTabs() {
  document.querySelectorAll('.view-tab').forEach((tab) => {
    tab.addEventListener('click', () => setViewMode(tab.dataset.view));
  });
}
