/**
 * Управление темой интерфейса.
 *
 * Тема хранится в localStorage и применяется через data-theme на <html>.
 * После переключения кидает `theme:changed` — на него подписаны графики.
 */
const STORAGE_KEY = 'spb-theme';

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
  const initial = saved || (prefersDark ? 'dark' : 'light');

  applyTheme(initial, { silent: true });
  bindToggle();
}

export function toggleTheme() {
  const current = document.documentElement.dataset.theme || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem(STORAGE_KEY, next);
}

function applyTheme(theme, { silent = false } = {}) {
  document.documentElement.dataset.theme = theme;

  // ARIA для switch
  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.setAttribute('aria-checked', theme === 'dark' ? 'true' : 'false');

  if (!silent) {
    // Даём браузеру применить новые CSS-переменные, затем сообщаем всем
    requestAnimationFrame(() => {
      document.dispatchEvent(new CustomEvent('theme:changed', { detail: { theme } }));
    });
  }
}

function bindToggle() {
  const toggle = document.getElementById('theme-toggle');
  if (!toggle) return;
  toggle.addEventListener('click', toggleTheme);
}
