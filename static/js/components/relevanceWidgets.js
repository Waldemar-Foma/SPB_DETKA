/**
 * Компактные графики для дашборда.
 * Держим карту инстансов, чтобы гарантированно уничтожать старые
 * при обновлении данных. Chart.js 4 плохо находит их через getChart().
 */

const instances = new Map();   // key -> Chart

export function renderRelevanceChart(items) {
  const canvas = document.getElementById('chart-relevance');
  if (!canvas || !window.Chart) return;

  destroy('relevance');

  const buckets = [
    { label: '90–100', value: 0 },
    { label: '75–89',  value: 0 },
    { label: '50–74',  value: 0 },
    { label: '< 50',   value: 0 },
  ];

  items.forEach((i) => {
    const s = i.score ?? 0;
    if (s >= 90) buckets[0].value++;
    else if (s >= 75) buckets[1].value++;
    else if (s >= 50) buckets[2].value++;
    else buckets[3].value++;
  });

  const chart = new window.Chart(canvas, {
    type: 'bar',
    data: {
      labels: buckets.map((b) => b.label),
      datasets: [{
        data: buckets.map((b) => b.value),
        backgroundColor: readColor('--color-accent', '#ff4e64'),
        borderRadius: 6,
        barThickness: 32,
      }],
    },
    options: baseOptions(),
  });
  instances.set('relevance', chart);
}

export function renderRegionsChart(items) {
  const canvas = document.getElementById('chart-regions');
  if (!canvas || !window.Chart) return;

  destroy('regions');

  const counts = {};
  items.forEach((i) => {
    counts[i.region] = (counts[i.region] || 0) + 1;
  });
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);

  const chart = new window.Chart(canvas, {
    type: 'bar',
    data: {
      labels: sorted.map(([r]) => r),
      datasets: [{
        data: sorted.map(([, c]) => c),
        backgroundColor: readColor('--color-info', '#60a5fa'),
        borderRadius: 6,
        barThickness: 20,
      }],
    },
    options: { ...baseOptions(), indexAxis: 'y' },
  });
  instances.set('regions', chart);
}

export function renderTypesChart(items) {
  const canvas = document.getElementById('chart-types');
  if (!canvas || !window.Chart) return;

  destroy('types');

  const counts = {};
  items.forEach((i) => {
    counts[i.company_type] = (counts[i.company_type] || 0) + 1;
  });

  const palette = [
    readColor('--color-success', '#4ade80'),
    readColor('--color-info', '#60a5fa'),
    readColor('--color-warning', '#fbbf24'),
  ];

  const chart = new window.Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: Object.keys(counts),
      datasets: [{
        data: Object.values(counts),
        backgroundColor: palette,
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      animation: { duration: 400 },
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: readColor('--color-text', '#e5e5e7'),
            font: { family: 'Inter', size: 12 },
            boxWidth: 10,
            padding: 10,
          },
        },
      },
    },
  });
  instances.set('types', chart);
}

/** Уничтожает все активные графики. Использовать при уходе со страницы. */
export function destroyAllCharts() {
  for (const chart of instances.values()) {
    try { chart.destroy(); } catch { /* ignore */ }
  }
  instances.clear();
}

// --- Внутренние утилиты --------------------------------------------------

function destroy(key) {
  const chart = instances.get(key);
  if (chart) {
    try { chart.destroy(); } catch { /* ignore */ }
    instances.delete(key);
  }
}

function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: readColor('--color-surface-deep', '#0e0e10'),
        titleColor: readColor('--color-text-strong', '#fff'),
        bodyColor: readColor('--color-text', '#e5e5e7'),
        borderColor: readColor('--color-border', 'rgba(255,255,255,.08)'),
        borderWidth: 1,
        padding: 8,
      },
    },
    scales: {
      x: {
        grid: { display: false, drawBorder: false },
        ticks: {
          color: readColor('--color-text-muted', '#8b8b93'),
          font: { size: 11 },
        },
      },
      y: {
        beginAtZero: true,
        grid: { display: false, drawBorder: false },
        ticks: {
          precision: 0,
          color: readColor('--color-text-muted', '#8b8b93'),
          font: { size: 11 },
        },
      },
    },
  };
}

function readColor(variable, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  return value || fallback;
}
