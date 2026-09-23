import { h, icon } from '../utils/dom.js';
import { formatMln, formatMrd } from '../utils/format.js';
import { isFavorite, toggleFavorite } from '../utils/favorites.js';
import { toast } from './toast.js';

/**
 * Карточка контрагента для центральной ленты.
 * @param {Object} item — данные из /procurement/:id/suppliers
 * @param {(inn:string)=>void} onOpen — обработчик клика
 */
export function SupplierCard(item, onOpen) {
  const initial = (item.name.replace(/[«»"]/g, '').trim()[0] || '?').toUpperCase();
  const fav = isFavorite(item.inn);

  const starBtn = h('button', {
    class: `favorite-btn ${fav ? 'is-active' : ''}`,
    type: 'button',
    'aria-label': fav ? 'Убрать из избранного' : 'Добавить в избранное',
    onClick: (e) => {
      e.stopPropagation();
      const added = toggleFavorite(item.inn);
      starBtn.classList.toggle('is-active', added);
      starBtn.setAttribute('aria-label',
        added ? 'Убрать из избранного' : 'Добавить в избранное');
      toast(added ? 'Добавлено в избранное' : 'Удалено из избранного',
        added ? 'success' : 'info');
    },
  }, icon('star'));

  return h('article', {
    class: 'supplier-card',
    role: 'button',
    tabindex: '0',
    'aria-label': `Открыть профиль ${item.name}`,
    dataset: { inn: item.inn },
    onClick: () => onOpen(item.inn),
    onKeydown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(item.inn); }
    },
  },
    h('div', { class: 'supplier-card__top' },
      h('span', { class: 'badge badge--score' },
        item.score, ' ', item.relevance_label),
      h('div', { class: 'supplier-card__top-right' },
        h('span', { class: 'badge badge--type' }, item.company_type),
        starBtn,
      ),
    ),

    h('div', { class: 'supplier-card__body' },
      h('div', { class: 'supplier-card__logo' }, initial),
      h('div', {},
        h('div', { class: 'supplier-card__title' },
          item.name,
          item.is_verified ? icon('check-circle') : null,
        ),
        h('div', { class: 'supplier-card__specialty' }, `Тип: ${item.company_type}`),
        h('div', { class: 'supplier-card__meta' },
          metaItem('file-alt', `ИНН ${item.inn}`),
          metaItem('map-marker-alt', item.region),
          metaItem('clock', `${item.years_on_market} лет на рынке`),
        ),
      ),
    ),

    h('div', { class: 'supplier-card__tags' },
      ...item.tags.map((t) => h('span', { class: 'badge badge--tag' }, t)),
    ),

    h('div', { class: 'supplier-card__footer' },
      h('div', { class: 'supplier-card__metrics' },
        metric('Контракты', String(item.contracts_count)),
        metric('Сумма', formatMln(item.contracts_sum_mln)),
        metric('Выручка', formatMrd(item.revenue_mrd)),
      ),
      h('button', {
        class: 'btn btn--primary',
        type: 'button',
        onClick: (e) => { e.stopPropagation(); onOpen(item.inn); },
      }, 'Открыть профиль'),
    ),
  );
}

const metaItem = (iconName, text) =>
  h('span', { class: 'supplier-card__meta-item' }, icon(iconName), h('span', {}, text));

const metric = (label, value) =>
  h('div', { class: 'supplier-card__metric' },
    h('span', { class: 'supplier-card__metric-label' }, label),
    h('span', { class: 'supplier-card__metric-value' }, value),
  );