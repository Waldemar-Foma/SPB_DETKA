/**
 * Режим «Виджеты»: карточки топ-поставщиков.
 */
import { h, icon } from '../utils/dom.js';
import { formatMln } from '../utils/format.js';

export function renderWidgets(grid, items, onOpen) {
  items.slice(0, 9).forEach((item) => grid.append(WidgetCard(item, onOpen)));
}

function WidgetCard(item, onOpen) {
  return h('article', {
    class: 'widget-card',
    role: 'button',
    tabindex: '0',
    onClick: () => onOpen(item.inn),
    onKeydown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(item.inn); }
    },
  },
    h('div', { class: 'widget-card__head' },
      h('div', {},
        h('div', { class: 'widget-card__name' }, item.name),
        h('div', { class: 'widget-card__meta' },
          `${item.company_type} · ${item.region}`),
      ),
      h('div', { class: 'widget-card__score' },
        h('div', { class: 'widget-card__score-value' }, `${item.score}`),
        h('div', { class: 'widget-card__score-label' }, 'из 100'),
      ),
    ),

    h('div', { class: 'widget-card__progress' },
      h('div', { class: 'widget-card__progress-head' },
        h('span', {}, 'Госконтрактов'),
        h('b', {}, String(item.contracts_count)),
      ),
      h('div', { class: 'progress progress--thin' },
        h('div', {
          class: 'progress__fill progress__fill--accent',
          dataset: { value: Math.min(100, item.contracts_count * 5) },
        }),
      ),
      h('div', { class: 'widget-card__progress-head',
                 style: 'margin-top:4px' },
        h('span', {}, 'Объём'),
        h('b', {}, formatMln(item.contracts_sum_mln)),
      ),
    ),

    h('div', { class: 'widget-card__reason' },
      h('b', {}, icon('sparkles'), 'AI-обоснование:'),
      item.tags.slice(0, 2).join(' · ') || 'Соответствие профилю закупки',
    ),
  );
}

// Анимация прогресс-баров после вставки
document.addEventListener('DOMContentLoaded', () => {
  const observer = new MutationObserver(() => {
    document.querySelectorAll('.widget-card .progress__fill').forEach((el) => {
      if (el.dataset.value && !el.style.width) {
        requestAnimationFrame(() => { el.style.width = `${el.dataset.value}%`; });
      }
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
});
