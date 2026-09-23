/**
 * Переключение светлой/тёмной темы с сохранением выбора в localStorage.
 * Иконка кнопки — Line Awesome, меняем только класс la-moon / la-sun.
 */

const STORAGE_KEY = 'spb-theme';

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(saved || (prefersDark ? 'dark' : 'light'));
}

export function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem(STORAGE_KEY, next);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;

  const iconEl = document.getElementById('theme-toggle-icon');
  if (!iconEl) return;

  // Line Awesome: базовый префикс "las" остаётся, меняется только la-*
  iconEl.classList.remove('la-moon', 'la-sun');
  iconEl.classList.add(theme === 'dark' ? 'la-sun' : 'la-moon');
}