import { h } from '../utils/dom.js';

/**
 * Круговой индикатор релевантности на <canvas> через Chart.js.
 * При смене темы цвета обновляются автоматически.
 *
 * @param {number} value — 0..100
 */
export function RadialScore(value) {
  const canvas = h('canvas', { width: 96, height: 96 });
  const wrap = h('div', { class: 'radial' },
    canvas,
    h('div', { class: 'radial__value' },
      String(value),
      h('small', {}, '/100'),
    ),
  );

  requestAnimationFrame(() => {
    if (!window.Chart) return;

    const chart = new window.Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        datasets: [{
          data: [value, 100 - value],
          backgroundColor: [
            pickColor(value),
            readColor('--color-surface-alt', '#26262b'),
          ],
          borderWidth: 0,
        }],
      },
      options: {
        cutout: '82%',
        responsive: false,
        animation: { duration: 400 },
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
    });

    wrap.__chart = chart;

    const onThemeChange = () => {
      chart.data.datasets[0].backgroundColor = [
        pickColor(value),
        readColor('--color-surface-alt', '#26262b'),
      ];
      chart.update('none');
    };
    document.addEventListener('theme:changed', onThemeChange);

    const observer = new MutationObserver(() => {
      if (!document.body.contains(wrap)) {
        document.removeEventListener('theme:changed', onThemeChange);
        chart.destroy();
        observer.disconnect();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });

  return wrap;
}

// --- Утилиты --------------------------------------------------------------

/** Цвет кольца в зависимости от значения — на одной палитре. */
function pickColor(value) {
  if (value >= 90) return readColor('--color-success', '#4ade80');
  if (value >= 70) return readColor('--color-info', '#60a5fa');
  if (value >= 50) return readColor('--color-warning', '#fbbf24');
  return readColor('--color-danger', '#f87171');
}

function readColor(variable, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  return value || fallback;
}
