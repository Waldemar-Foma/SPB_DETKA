import { h } from '../utils/dom.js';

/** Заготовка одной карточки контрагента. */
export function SkeletonCard() {
  return h('div', { class: 'skeleton-card' },
    h('div', { class: 'skeleton-card__top' },
      h('div', { class: 'skeleton skeleton--badge' }),
      h('div', { class: 'skeleton skeleton--badge' }),
    ),
    h('div', { class: 'skeleton-card__body' },
      h('div', { class: 'skeleton skeleton--avatar' }),
      h('div', { class: 'skeleton-card__lines' },
        h('div', { class: 'skeleton skeleton--title' }),
        h('div', { class: 'skeleton skeleton--subtitle' }),
      ),
    ),
    h('div', { class: 'skeleton-card__footer' },
      h('div', { class: 'skeleton skeleton--metric' }),
      h('div', { class: 'skeleton skeleton--button' }),
    ),
  );
}

/** N скелетон-карточек подряд. */
export function SkeletonFeed(count = 3) {
  return Array.from({ length: count }, SkeletonCard);
}

/** Скелетон для drawer. */
export function SkeletonDrawer() {
  return h('div', { class: 'skeleton-drawer' },
    h('div', { class: 'skeleton skeleton--badge' }),
    h('div', { class: 'skeleton skeleton--title', style: 'width:70%;height:28px' }),
    h('div', { class: 'skeleton skeleton--subtitle' }),
    h('div', { class: 'skeleton-drawer__section' },
      h('div', { class: 'skeleton skeleton--text', style: 'width:40%' }),
      h('div', { class: 'skeleton skeleton--chart' }),
    ),
    h('div', { class: 'skeleton-drawer__section' },
      h('div', { class: 'skeleton skeleton--text', style: 'width:50%' }),
      h('div', { class: 'skeleton skeleton--map' }),
    ),
  );
}