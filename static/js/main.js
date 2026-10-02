import { initTheme } from './utils/theme.js';
import { initViewMode } from './utils/viewMode.js';
import { initDragWidgets } from './utils/dragWidgets.js';
import { initDashboardPage } from './pages/dashboardPage.js';
import { initAdminPage } from './pages/adminPage.js';
import { initApiTestsPage } from './pages/apiTestsPage.js';
import { initSettingsPage } from './pages/settingsPage.js';

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initViewMode();
  initDragWidgets();
  if (document.body.dataset.page === 'dashboard') {
    initDashboardPage().catch((error) => console.error('[dashboard]', error));
  }
  if (document.body.dataset.page === 'admin') {
    initAdminPage();
  }
  if (document.body.dataset.page === 'admin-api-tests') {
    initApiTestsPage();
  }
  if (document.body.dataset.page === 'settings') {
    initSettingsPage();
  }
});
