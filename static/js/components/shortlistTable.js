/**
 * Рендер таблицы шорт-листа.
 * Отвечает только за DOM: строки, аватары, бейджи, прогресс-бары.
 */
import { h, icon } from '../utils/dom.js';
import { formatMln } from '../utils/format.js';

const AVATAR_COLORS = [
  'linear-gradient(135deg,#6366f1,#8b5cf6)',
  'linear-gradient(135deg,#0ea5e9,#22d3ee)',
  'linear-gradient(135deg,#10b981,#34d399)',
  'linear-gradient(135deg,#f59e0b,#fbbf24)',
  'linear-gradient(135deg,#ec4899,#f472b6)',
  'linear-gradient(135deg,#8b5cf6,#a78bfa)',
];

const ROLE_BADGE = {
  'Производитель': 'badge--producer',
  'Дистрибьютор':  'badge--distributor',
  'Поставщик':     'badge--supplier',
};

const LOCAL_REGIONS = new Set(['Санкт-Петербург', 'Ленинградская область']);

/** Отрисовывает строки в tbody. */
export function renderShortlist(tbody, items, onOpen) {
  tbody.innerHTML = '';
  items.forEach((item) => tbody.append(Row(item, onOpen)));
}

/** Заглушка, если ничего не найдено. */
export function renderEmptyTable(tbody) {
  tbody.innerHTML = '';
  tbody.append(h('tr', {},
    h('td', { colspan: 6 },
      h('div', { class: 'table-empty' },
        icon('search'),
        h('p', {}, 'Ничего не найдено. Попробуйте изменить фильтры.'),
      ),
    ),
  ));
}

/** Плейсхолдеры-скелетоны на время загрузки. */
export function renderLoadingRows(tbody, count = 4) {
  tbody.innerHTML = '';
  for (let i = 0; i < count; i++) {
    tbody.append(h('tr', { class: 'skeleton-row' },
      h('td', { colspan: 6 },
        h('div', {
          class: 'skeleton',
          style: 'height:56px;border-radius:12px;',
        }),
      ),
    ));
  }
}

// --- Одна строка ----------------------------------------------------------

function Row(item, onOpen) {
  const initials = getInitials(item.name);
  const color = pickColor(item.inn);

  const tr = h('tr', {
    dataset: { inn: item.inn },
    role: 'button',
    tabindex: '0',
    onClick: () => onOpen(item.inn),
    onKeydown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onOpen(item.inn);
      }
    },
  },
    // Компания
    h('td', {},
      h('div', { class: 'cell-company' },
        h('div', {
          class: 'company-avatar',
          style: `background:${color}`,
        }, initials),
        h('div', { class: 'company-meta' },
          h('span', { class: 'company-name' }, item.name),
          h('span', { class: 'company-inn' }, `ИНН ${item.inn}`),
        ),
      ),
    ),

    // Роль
    h('td', {},
      h('span', {
        class: `badge ${ROLE_BADGE[item.company_type] || 'badge--regional'}`,
      }, item.company_type),
    ),

    // Регион
    h('td', {},
      h('div', { class: 'cell-region' },
        h('span', { class: 'cell-region__name' }, item.region),
        h('span', {
          class: `badge ${LOCAL_REGIONS.has(item.region)
            ? 'badge--local' : 'badge--regional'}`,
        }, LOCAL_REGIONS.has(item.region) ? 'Локальный' : 'Региональный'),
      ),
    ),

    // Объём контрактов
    h('td', {},
      h('div', { class: 'cell-experience' },
        h('div', { class: 'cell-experience__head' },
          h('span', {}, 'контрактов'),
          h('b', {}, String(item.contracts_count)),
        ),
        h('div', { class: 'progress progress--thin' },
          h('div', {
            class: 'progress__fill progress__fill--accent',
            dataset: { value: Math.min(100, (item.contracts_count || 0) * 5) },
          }),
        ),
        h('span', {
          style: 'font-size:11px;color:var(--color-text-subtle);margin-top:2px',
        }, `на ${formatMln(item.contracts_sum_mln)}`),
      ),
    ),

    // Индекс релевантности
    h('td', {},
      h('div', { class: 'cell-score' },
        h('span', { class: `score-badge ${scoreClass(item.score)}` },
          `${item.score}%`),
        h('span', {
          style: 'font-size:11px;color:var(--color-text-subtle)',
        }, item.relevance_label.replace(' релевантность', '')),
      ),
    ),

    // Действие
    h('td', {},
      h('button', {
        class: 'btn btn--ghost btn--sm',
        type: 'button',
        onClick: (e) => { e.stopPropagation(); onOpen(item.inn); },
      }, icon('file-search'), 'Смотреть обоснование'),
    ),
  );

  // Анимация прогресс-баров после вставки в DOM
  requestAnimationFrame(() => {
    tr.querySelectorAll('.progress__fill').forEach((el) => {
      el.style.width = `${el.dataset.value}%`;
    });
  });

  return tr;
}

// --- Утилиты --------------------------------------------------------------

function getInitials(name) {
  const clean = String(name || '').replace(/[«»"]/g, '').trim();
  const words = clean.split(/\s+/).filter(Boolean);
  const meaningful = words.filter((w) =>
    w.length > 1 && !/^(ООО|АО|ЗАО|ИП)$/i.test(w));
  const source = meaningful.length ? meaningful : words;
  return source.slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
}

function pickColor(seed) {
  const n = String(seed).split('')
    .reduce((acc, ch) => acc + ch.charCodeAt(0), 0);
  return AVATAR_COLORS[n % AVATAR_COLORS.length];
}

function scoreClass(score) {
  if (score >= 90) return 'score-badge--high';
  if (score >= 70) return 'score-badge--info';
  if (score >= 50) return 'score-badge--mid';
  return 'score-badge--low';
}
