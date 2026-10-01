import { initTheme } from './utils/theme.js';
import { initViewMode } from './utils/viewMode.js';
import { initDragWidgets } from './utils/dragWidgets.js';
import { initDashboardPage } from './pages/dashboardPage.js';

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initViewMode();
  initDragWidgets();
  if (document.body.dataset.page === 'dashboard') {
    initDashboardPage().catch((error) => console.error('[dashboard]', error));
  }
});
