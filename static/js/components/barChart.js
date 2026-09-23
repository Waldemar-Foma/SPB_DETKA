import { h } from '../utils/dom.js';

/**
 * Горизонтальная гистограмма количества контрактов по годам.
 * @param {Object} byYears — { "2022": 4, "2023": 6, ... }
 */
export function ContractsBarChart(byYears) {
  const canvas = h('canvas', { class: 'chart-canvas' });
  const entries = Object.entries(byYears);
  if (!entries.length) return canvas;

  requestAnimationFrame(() => {
    if (!window.Chart) return;

    const styles = getComputedStyle(document.documentElement);
    const primary = styles.getPropertyValue('--color-primary').trim() || '#2563EB';

    new window.Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: entries.map(([year]) => year),
        datasets: [{
          data: entries.map(([, count]) => count),
          backgroundColor: primary,
          borderRadius: 6,
          barThickness: 14,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { precision: 0 } },
          y: { grid: { display: false } },
        },
      },
    });
  });

  return canvas;
}