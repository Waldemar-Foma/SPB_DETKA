import { h } from '../utils/dom.js';

/**
 * Круговой индикатор релевантности на <canvas> через Chart.js.
 * @param {number} value — 0..100
 */
export function RadialScore(value) {
  const canvas = h('canvas', { width: 96, height: 96 });
  const wrap = h('div', { class: 'radial' },
    canvas,
    h('div', { class: 'radial__value' }, String(value), h('small', {}, '/100')),
  );

  requestAnimationFrame(() => {
    if (!window.Chart) return;

    const styles = getComputedStyle(document.documentElement);
    const success = styles.getPropertyValue('--color-success').trim() || '#10B981';
    const track   = styles.getPropertyValue('--color-surface-alt').trim() || '#F1F5F9';

    new window.Chart(canvas.getContext('2d'), {
      type: 'doughnut',
      data: {
        datasets: [{
          data: [value, 100 - value],
          backgroundColor: [success, track],
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
  });

  return wrap;
}