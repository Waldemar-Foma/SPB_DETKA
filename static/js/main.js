/**
 * Точка входа фронтенда.
 * Инициализирует тему, вешает обработчики, запускает страницу поиска.
 */
import { initTheme, toggleTheme } from './utils/theme.js';
import { initSearchPage } from './pages/searchPage.js';

document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  const themeButton = document.getElementById('theme-toggle');
  if (themeButton) themeButton.addEventListener('click', toggleTheme);

  if (document.getElementById('supplier-feed')) {
    initSearchPage().catch((error) => {
      console.error('Ошибка инициализации страницы:', error);
    });
  }
});