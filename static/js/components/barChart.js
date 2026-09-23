import { h } from '../utils/dom.js';

/**
 * Горизонтальная гистограмма количества контрактов по годам.
 *
 * Chart.js читает CSS-переменные через getComputedStyle один раз при
 * создании. При переключении темы нужно явно перерисовать график —
 * подписываемся на событие `theme:changed` и вызываем chart.update().
 */
export function ContractsBarChart(byYears) {
  const canvas = h('canvas');
  const wrapper = h('div', { class: 'chart-box' }, canvas);
  const entries = Object.entries(byYears || {});

  if (!entries.length) {
    return h('div', { class: 'chart-box chart-box--empty' },
      'Нет данных по контрактам');
  }

  requestAnimationFrame(() => {
    if (!window.Chart) return;

    const chart = new window.Chart(canvas.getContext('2d'), buildConfig(entries));
    wrapper.__chart = chart;

    // Перерисовываем при смене темы
    const onThemeChange = () => updateChartTheme(chart);
    document.addEventListener('theme:changed', onThemeChange);

    // Отписываемся, когда панель с графиком удаляется из DOM
    const observer = new MutationObserver(() => {
      if (!document.body.contains(wrapper)) {
        document.removeEventListener('theme:changed', onThemeChange);
        chart.destroy();
        observer.disconnect();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });

  return wrapper;
}

// --- Конфиг графика -------------------------------------------------------

function buildConfig(entries) {
  return {
    type: 'bar',
    data: {
      labels: entries.map(([year]) => year),
      datasets: [{
        data: entries.map(([, count]) => count),
        backgroundColor: readColor('--color-accent', '#ff4e64'),
        hoverBackgroundColor: readColor('--color-accent-hover', '#ff6679'),
        borderRadius: 6,
        barThickness: 14,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      layout: { padding: { top: 4, bottom: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: readColor('--color-surface-deep', '#0e0e10'),
          titleColor: readColor('--color-text-strong', '#fff'),
          bodyColor: readColor('--color-text', '#e5e5e7'),
          borderColor: readColor('--color-border', 'rgba(255,255,255,.08)'),
          borderWidth: 1,
          padding: 10,
          titleFont: { family: 'Inter', size: 12, weight: '600' },
          bodyFont:  { family: 'Inter', size: 12 },
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.x} контрактов`,
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { display: false, drawBorder: false },
          ticks: {
            precision: 0,
            color: readColor('--color-text-muted', '#8b8b93'),
            font: { size: 11 },
          },
        },
        y: {
          grid: { display: false, drawBorder: false },
          ticks: {
            color: readColor('--color-text-muted', '#8b8b93'),
            font: { size: 12, weight: '500' },
          },
        },
      },
    },
  };
}

/** Обновляет цвета графика на текущие из CSS-переменных. */
function updateChartTheme(chart) {
  if (!chart) return;

  chart.data.datasets[0].backgroundColor = readColor('--color-accent', '#ff4e64');
  chart.data.datasets[0].hoverBackgroundColor = readColor('--color-accent-hover', '#ff6679');

  chart.options.plugins.tooltip.backgroundColor = readColor('--color-surface-deep', '#0e0e10');
  chart.options.plugins.tooltip.titleColor = readColor('--color-text-strong', '#fff');
  chart.options.plugins.tooltip.bodyColor = readColor('--color-text', '#e5e5e7');
  chart.options.plugins.tooltip.borderColor = readColor('--color-border', 'rgba(255,255,255,.08)');

  chart.options.scales.x.ticks.color = readColor('--color-text-muted', '#8b8b93');
  chart.options.scales.y.ticks.color = readColor('--color-text-muted', '#8b8b93');

  chart.update('none');  // 'none' — без анимации, мгновенно
}

// --- Утилита: читает CSS-переменную у <html> ------------------------------

function readColor(variable, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  return value || fallback;
}
