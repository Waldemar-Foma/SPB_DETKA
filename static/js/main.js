/**
 * Точка входа. Определяет страницу по data-page и запускает нужный обработчик.
 */
import { initTheme } from './utils/theme.js';
import { initDashboardPage } from './pages/dashboardPage.js';

document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  const pageId = document.body.dataset.page;

  if (pageId === 'dashboard' || pageId === 'suppliers') {
    initDashboardPage().catch((error) => {
      console.error('[main.js] Ошибка инициализации:', error);
    });
  }
});
