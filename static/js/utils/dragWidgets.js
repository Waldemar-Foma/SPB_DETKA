/**
 * Перетаскивание плавающих виджетов дашборда.
 *
 * - Позиции хранятся в localStorage: { widget-key: { left, top } }.
 * - Drag активен только в режиме `widgets`.
 * - При сохранении и восстановлении проверяется наложение (collision):
 *   если два виджета пересекаются, «новый» сдвигается вниз до
 *   ближайшего свободного места.
 */
const STORAGE_KEY = 'spb-widget-positions';
const GAP = 16;   // отступ между виджетами при разрешении коллизий

export function initDragWidgets(containerSelector = '.app-main') {
  const container = document.querySelector(containerSelector);
  if (!container) return;

  const widgets = Array.from(container.querySelectorAll('.dash-widget[data-widget]'));
  if (!widgets.length) return;

  // 1. Восстановили сохранённые позиции
  const saved = readPositions();
  widgets.forEach((w) => applySavedPosition(w, saved));

  // 2. Разрешили коллизии (в том числе если пользователь сохранил плохие)
  snapCollisions(widgets);

  // 3. Навесили drag
  widgets.forEach((w) => bindDrag(w, container));

  // 4. Реакция на режим
  syncDragMode(widgets);
  document.addEventListener('view:changed', () => syncDragMode(widgets));
}

// --- Позиции --------------------------------------------------------------

function applySavedPosition(widget, positions) {
  const key = widget.dataset.widget;
  if (!key || !positions[key]) return;

  const { left, top } = positions[key];
  if (typeof left === 'number') widget.style.left = `${left}px`;
  if (typeof top === 'number') widget.style.top = `${top}px`;
  widget.style.right = 'auto';
  widget.style.bottom = 'auto';
}

function readPositions() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function savePositions(widgets) {
  const out = {};
  widgets.forEach((w) => {
    const key = w.dataset.widget;
    if (!key) return;
    const rect = w.getBoundingClientRect();
    const parent = w.offsetParent || document.body;
    const parentRect = parent.getBoundingClientRect();
    out[key] = {
      left: Math.round(rect.left - parentRect.left),
      top:  Math.round(rect.top  - parentRect.top),
    };
  });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(out));
}

// --- Разрешение коллизий --------------------------------------------------

/**
 * Проходит по виджетам и, если они пересекаются, сдвигает нижний вниз.
 * Работает итеративно, пока все не разойдутся.
 */
function snapCollisions(widgets) {
  const container = widgets[0]?.offsetParent;
  if (!container) return;

  // Сортируем по «верхнему левому углу» — те, что выше и левее, фиксируются первыми
  const ordered = [...widgets].sort((a, b) => {
    const ra = a.getBoundingClientRect();
    const rb = b.getBoundingClientRect();
    if (Math.abs(ra.top - rb.top) < 20) return ra.left - rb.left;
    return ra.top - rb.top;
  });

  const placed = [];

  for (const w of ordered) {
    const rect = w.getBoundingClientRect();
    const parentRect = container.getBoundingClientRect();

    let left = rect.left - parentRect.left;
    let top  = rect.top  - parentRect.top;

    // Ищем ближайшее свободное место, двигая вниз
    let safety = 0;
    while (collidesWithAny({ left, top, w: w.offsetWidth, h: w.offsetHeight }, placed) && safety < 50) {
      top += GAP;
      safety++;
    }

    w.style.left = `${left}px`;
    w.style.top  = `${top}px`;
    w.style.right = 'auto';
    w.style.bottom = 'auto';

    placed.push({ left, top, w: w.offsetWidth, h: w.offsetHeight });
  }
}

function collidesWithAny(box, others) {
  return others.some((o) => rectsOverlap(
    { left: box.left, top: box.top, right: box.left + box.w, bottom: box.top + box.h },
    { left: o.left, top: o.top, right: o.left + o.w, bottom: o.top + o.h },
  ));
}

function rectsOverlap(a, b) {
  return !(a.right + GAP <= b.left
        || b.right + GAP <= a.left
        || a.bottom + GAP <= b.top
        || b.bottom + GAP <= a.top);
}

// --- Drag -----------------------------------------------------------------

function bindDrag(widget, container) {
  const handle = widget.querySelector('.dash-widget__head') || widget;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;
  let isDragging = false;

  handle.addEventListener('pointerdown', (e) => {
    if (document.body.dataset.view !== 'widgets') return;
    if (e.target.closest('button')) return;

    isDragging = true;
    widget.classList.add('is-dragging');
    handle.setPointerCapture?.(e.pointerId);

    const rect = widget.getBoundingClientRect();
    const parentRect = container.getBoundingClientRect();

    startX = e.clientX;
    startY = e.clientY;
    startLeft = rect.left - parentRect.left;
    startTop  = rect.top  - parentRect.top;

    e.preventDefault();
  });

  handle.addEventListener('pointermove', (e) => {
    if (!isDragging) return;

    const dx = e.clientX - startX;
    const dy = e.clientY - startY;

    let nextLeft = startLeft + dx;
    let nextTop  = startTop  + dy;

    const cw = container.clientWidth;
    const ch = container.clientHeight;
    const ww = widget.offsetWidth;
    const wh = widget.offsetHeight;

    nextLeft = Math.max(8, Math.min(cw - ww - 8, nextLeft));
    nextTop  = Math.max(8, Math.min(ch - wh - 8, nextTop));

    widget.style.left = `${nextLeft}px`;
    widget.style.top  = `${nextTop}px`;
    widget.style.right = 'auto';
    widget.style.bottom = 'auto';

    // Подсветка, если накладывается на другого
    const overlaps = isOverlappingOthers(widget, container);
    widget.classList.toggle('is-overlapping', overlaps);
  });

  const stop = () => {
    if (!isDragging) return;
    isDragging = false;
    widget.classList.remove('is-dragging');
    widget.classList.remove('is-overlapping');

    // Финальное разрешение коллизий
    const all = Array.from(container.querySelectorAll('.dash-widget[data-widget]'));
    snapCollisions(all);
    savePositions(all);
  };

  handle.addEventListener('pointerup', stop);
  handle.addEventListener('pointercancel', stop);
}

function isOverlappingOthers(widget, container) {
  const all = Array.from(container.querySelectorAll('.dash-widget[data-widget]'))
    .filter((w) => w !== widget);
  const rect = widget.getBoundingClientRect();

  return all.some((other) => {
    const o = other.getBoundingClientRect();
    return !(rect.right + GAP <= o.left
          || o.right + GAP <= rect.left
          || rect.bottom + GAP <= o.top
          || o.bottom + GAP <= rect.top);
  });
}

// --- Режим ---------------------------------------------------------------

function syncDragMode(widgets) {
  const draggable = document.body.dataset.view === 'widgets';
  widgets.forEach((w) => {
    w.classList.toggle('is-drag-enabled', draggable);
  });
}
