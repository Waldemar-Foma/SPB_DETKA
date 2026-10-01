/**
 * Перетаскивание плавающих карточек прямо поверх карты.
 *
 * В позиционирование входят и аналитические виджеты, и карточка
 * «Подбор по заявке». Позиции сохраняются локально в браузере.
 */
const STORAGE_KEY = 'procurement-widget-positions-v3';

export function initDragWidgets(containerSelector = '.app-main') {
  if (document.body.dataset.page !== 'dashboard') return;
  const container = document.querySelector(containerSelector);
  if (!container) return;

  const widgets = [
    ...container.querySelectorAll('.dash-widget[data-widget], .dash-context[data-widget]'),
  ];
  const saved = read();

  widgets.forEach((widget) => restore(widget, saved));
  widgets.forEach((widget) => bind(widget, container, widgets));
  sync(widgets);

  document.addEventListener('view:changed', () => sync(widgets));
}

function read() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function restore(widget, saved) {
  const position = saved[widget.dataset.widget];
  if (!position) return;
  widget.style.left = `${position.left}px`;
  widget.style.top = `${position.top}px`;
  widget.style.right = 'auto';
  widget.style.bottom = 'auto';
}

function save(widgets, container) {
  const containerRect = container.getBoundingClientRect();
  const positions = {};
  widgets.forEach((widget) => {
    const rect = widget.getBoundingClientRect();
    positions[widget.dataset.widget] = {
      left: Math.round(rect.left - containerRect.left),
      top: Math.round(rect.top - containerRect.top),
    };
  });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(positions));
}

function sync(widgets) {
  const enabled = document.body.dataset.view === 'map';
  widgets.forEach((widget) => widget.classList.toggle('is-drag-enabled', enabled));
}

function bind(widget, container, widgets) {
  const handle = widget.querySelector('.dash-context__drag-handle')
    || widget.querySelector('.dash-widget__head')
    || widget;

  let dragging = false;
  let startX = 0;
  let startY = 0;
  let startLeft = 0;
  let startTop = 0;

  handle.addEventListener('pointerdown', (event) => {
    if (document.body.dataset.view !== 'map') return;
    if (event.button !== undefined && event.button !== 0) return;
    if (event.target.closest('button, a, input, select, textarea, label')) return;

    dragging = true;
    widget.classList.add('is-dragging');
    document.body.classList.add('is-dragging-widget');
    handle.setPointerCapture?.(event.pointerId);

    const rect = widget.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    startX = event.clientX;
    startY = event.clientY;
    startLeft = rect.left - containerRect.left;
    startTop = rect.top - containerRect.top;
    event.preventDefault();
  });

  handle.addEventListener('pointermove', (event) => {
    if (!dragging) return;

    let left = startLeft + event.clientX - startX;
    let top = startTop + event.clientY - startY;

    left = Math.max(8, Math.min(container.clientWidth - widget.offsetWidth - 8, left));
    top = Math.max(8, Math.min(container.clientHeight - widget.offsetHeight - 8, top));

    widget.style.left = `${left}px`;
    widget.style.top = `${top}px`;
    widget.style.right = 'auto';
    widget.style.bottom = 'auto';
  });

  const stop = () => {
    if (!dragging) return;
    dragging = false;
    widget.classList.remove('is-dragging');
    document.body.classList.remove('is-dragging-widget');
    save(widgets, container);
  };

  handle.addEventListener('pointerup', stop);
  handle.addEventListener('pointercancel', stop);
}
